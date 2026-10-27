from __future__ import annotations

from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse

import requests

from .clients import AlphaClient, ArxivClient, ZoteroClient, local_zotero, local_items
from .domain import BridgeError, Paper, find_match
from .storage import Config, Store, now
from .files import place_linked_pdf


class Engine:
    def __init__(self, root, alpha_factory=AlphaClient, zotero_factory=ZoteroClient, arxiv=None, local_reader=local_items):
        self.root = Path(root)
        self.config = Config(self.root / "data")
        self.store = Store(self.root / "data")
        self.alpha_factory, self.zotero_factory = alpha_factory, zotero_factory
        self.arxiv = arxiv or ArxivClient()
        self.local_reader = local_reader
        self.lock = threading.Lock()
        self.paper_write_lock = threading.RLock()
        self.busy = False
        self.operation = ""
        self.stop = threading.Event()
        self.orx_process = None
        self.orx_log = None
        self.next_auto = time.monotonic() + 15

    def scope(self):
        return "web:user:" + self.config.snapshot()["zotero_user_id"]

    def missing(self):
        out = []
        if not self.config.secret("alphaxiv_key"):
            out.append("alphaXiv API Key")
        if not self.config.secret("zotero_key"):
            out.append("Zotero API Key（个人文献库读写及文件权限）")
        if not self.config.snapshot()["zotero_user_id"]:
            out.append("Zotero 数字 User ID")
        return out

    def event(self, level, text):
        self.store.event(level, self.config.redact(text))

    def status(self):
        jobs = self.store.jobs(self.scope())
        counts = Counter(j["status"] for j in jobs)
        return {"name": "Research Nexus", "version": "0.5.0", "busy": self.busy,
                "operation": self.operation, "config": self.config.public(), "missing": self.missing(),
                "counts": dict(counts), "jobs": jobs, "folders": self.store.meta("folders") or [],
                "warnings": self.store.meta("warnings") or [], "last_sync": self.store.meta("last_sync"),
                "last_error": self.store.meta("last_error"), "events": self.store.events(),
                "openresearch_installed": Path(self.config.snapshot()["openresearch_exe"]).is_file(),
                "root": str(self.root), "auto_sync_running": self.config.snapshot()["auto_sync"] and not self.missing(),
                "limitations": ["公开 arXiv 论文自动归档；私有上传和非 arXiv 记录进入待处理。",
                                "alphaXiv 文件夹列表可能被接口截断，若发现会明确提示。",
                                "归档前会读取本地和云端两份文献索引；本地条目尚未同步时会等待，不另建重复条目。"]}

    def launch(self, operation):
        if not self.lock.acquire(blocking=False):
            raise BridgeError("已有操作正在进行，请等待完成。")
        self.busy, self.operation = True, operation
        def work():
            try:
                if operation == "sync":
                    self.sync()
                elif operation == "preview":
                    self.preview()
                elif operation == "connections":
                    self.connections()
            except Exception as exc:
                msg = self.config.redact(exc if isinstance(exc, BridgeError) else f"操作失败（{type(exc).__name__}）。")
                self.store.meta("last_error", {"time": now(), "message": msg})
                self.event("error", msg)
            finally:
                self.busy, self.operation = False, ""
                self.next_auto = time.monotonic() + self.config.snapshot()["sync_interval_seconds"]
                self.lock.release()
        threading.Thread(target=work, daemon=True).start()

    def save(self, payload):
        if not self.lock.acquire(blocking=False):
            raise BridgeError("同步或连接检查中，请完成后再修改配置。")
        try:
            before = self.config.snapshot()
            changed_account = ("zotero_user_id" in payload and str(payload["zotero_user_id"]) != before["zotero_user_id"]) or any(payload.get(k) and payload[k] != self.config.secret(k) for k in ("alphaxiv_key", "zotero_key"))
            self.config.save(payload)
            if changed_account:
                self.store.meta("checks", {})
            self.event("info", "连接和归档设置已保存，密钥不会出现在界面读回数据中。")
            self.next_auto = time.monotonic() + 5
        finally:
            self.lock.release()

    def preview(self):
        self.event("info", "正在读取 alphaXiv 收藏文件夹。")
        folders, papers, warnings, raw = self.alpha_factory(self.config.secret("alphaxiv_key")).library()
        self.store.meta("folders", folders)
        self.store.meta("warnings", warnings)
        # Retain the actual adapter input privately for troubleshooting after authorization.
        Config._atomic(self.root / "data" / "last-alpha-library.json", raw)
        self.event("info", f"已读取 {len(folders)} 个文件夹、{len(papers)} 个不同论文；尚未写入 Zotero。")
        return folders, papers, warnings

    def connections(self):
        checks = {"time": now(), "zotero_local": local_zotero()}
        if self.config.secret("alphaxiv_key"):
            try:
                folders, _, _ = self.preview()
                checks["alpha"] = {"ok": True, "message": f"可读取 {len(folders)} 个文件夹"}
            except Exception as exc:
                checks["alpha"] = {"ok": False, "message": self.config.redact(exc)}
        else:
            checks["alpha"] = {"ok": False, "message": "尚未配置 API Key"}
        cfg = self.config.snapshot()
        if cfg["zotero_user_id"] and self.config.secret("zotero_key"):
            try:
                client = self.zotero_factory(cfg["zotero_user_id"], self.config.secret("zotero_key"))
                client.req("GET", "/items", params={"limit": 1})
                checks["zotero_web"] = {"ok": True, "message": "个人文献库可读；写入及文件权限将在真实归档时验证"}
            except Exception as exc:
                checks["zotero_web"] = {"ok": False, "message": self.config.redact(exc)}
        else:
            checks["zotero_web"] = {"ok": False, "message": "尚未配置 User ID / API Key"}
        self.store.meta("checks", checks)
        self.event("info", "连接检查完成；未向 Zotero 写入测试文献。")

    def sync(self, only_canonical=None, recheck=False):
        with self.paper_write_lock:
            return self._sync(only_canonical, recheck)

    def _sync(self, only_canonical=None, recheck=False):
        if self.missing():
            raise BridgeError("开始归档前还需要：" + "、".join(self.missing()))
        cfg = self.config.snapshot()
        self.event("info", "开始检查收藏与已有文献。")
        folders, papers, warnings = self.preview()
        selected = set(cfg["alpha_folder_ids"])
        if selected:
            available = {f["id"] for f in folders}
            if not selected <= available:
                raise BridgeError("所选 alphaXiv 文件夹已变化，请重新选择。")
            papers = [p for p in papers if selected.intersection(p.folders)]
        if only_canonical:
            papers = [p for p in papers if p.canonical == only_canonical]
            if len(papers) != 1:
                raise BridgeError("指定论文不在当前返回的收藏范围内；未归档其他论文。")
        scope = self.scope()
        self.store.ingest(scope, papers)
        # Resume jobs even if an item was removed from its source folder after a timeout.
        jobs = [j for j in reversed(self.store.jobs(scope, limit=1000000))
                if (not only_canonical or j["canonical"] == only_canonical)
                and (j["status"] in ("queued", "error", "pdf_pending", "archiving", "local_pending")
                     or recheck and only_canonical and j["status"] in ("archived", "linked_archived", "metadata_archived", "existing"))]
        for job in jobs:
            if not job["paper"]["arxiv"]:
                self.store.update(job["id"], status="unsupported", error="当前自动归档仅支持公开 arXiv 论文；此记录未被忽略，可在列表中查看。")
        jobs = sorted([j for j in jobs if j["paper"]["arxiv"]], key=lambda j: (j["status"] != "queued", j["updated"], j["id"]))[:cfg["max_papers_per_sync"]]
        if not jobs:
            self.store.meta("last_sync", {"time": now(), "processed": 0, "warnings": warnings})
            self.store.meta("last_error", {})
            self.event("info", "收藏已检查，没有需要归档的新任务。")
            return
        metadata = self.arxiv.metadata([Paper(**j["paper"]) for j in jobs])
        zotero = self.zotero_factory(cfg["zotero_user_id"], self.config.secret("zotero_key"))
        items = zotero.all("/items/top")
        local_index = self.local_reader()
        collection = zotero.collection(cfg["zotero_collection"])
        processed, errors = 0, 0
        for job in jobs:
            try:
                p = Paper(**job["paper"])
                meta = metadata.get(p.arxiv)
                if not meta or not meta.get("title") or not meta.get("authors"):
                    raise BridgeError(getattr(self.arxiv, "last_errors", {}).get(p.arxiv) or "arXiv 尚未返回完整元数据，暂缓归档。")
                for field in ("title", "authors", "abstract", "published", "version", "pdf_url"):
                    setattr(p, field, meta[field])
                local_match, local_matches = find_match(p, local_index)
                cloud_keys = {x["key"] for x in items}
                unsynced = [x for x in local_matches if x["key"] not in cloud_keys]
                if unsynced and not job["allow_title_duplicate"]:
                    self.store.update(job["id"], paper=p.json(), status="local_pending",
                                      error="Zotero 本地已有匹配文献，但尚未同步到云端；请在 Zotero 完成同步后重试。")
                    continue
                self.store.update(job["id"], paper=p.json(), status="archiving", error="")
                self.archive(job, p, zotero, items, collection, cfg, meta)
                processed += 1
            except Exception as exc:
                errors += 1
                current = self.store.job(job["id"])
                message = self.config.redact(exc if isinstance(exc, BridgeError) else f"归档失败（{type(exc).__name__}），可重试。")
                self.store.update(job["id"], status="pdf_pending" if current["item_key"] else "error", error=message)
                self.event("error", f"{job['canonical']}：{message}")
        self.store.meta("last_sync", {"time": now(), "processed": processed, "errors": errors, "warnings": warnings})
        self.store.meta("last_error", {})
        self.event("info", f"本轮完成：处理 {processed} 篇，{errors} 篇待重试。")

    def archive(self, job, p, zotero, items, collection, cfg, meta):
        # Recovery always checks the persisted key before issuing a new create request.
        item = zotero.get(job["item_key"]) if job["item_key"] else None
        is_existing = bool(item) and f"Research Bridge ID: {p.canonical}" not in item.get("data", {}).get("extra", "")
        if not item:
            status, matches = find_match(p, items)
            if status == "review" and not job["allow_title_duplicate"]:
                self.store.update(job["id"], status="review", candidates=[{"key": x["key"], "title": x["data"].get("title", "")} for x in matches],
                                  error="疑似重复或已有多份同标识记录，请选择关联已有条目或独立归档。")
                return
            if status == "existing":
                item, is_existing = matches[0], True
                self.store.update(job["id"], item_key=item["key"])
            else:
                key = self.store.key(job["id"], "item_key")
                data = zotero.template("preprint")
                proposed = {"key": key, "title": p.title, "creators": [{"creatorType": "author", "name": a} for a in p.authors],
                            "abstractNote": p.abstract, "date": p.published, "url": f"https://arxiv.org/abs/{p.arxiv}{p.version}",
                            "repository": "arXiv", "archiveID": p.arxiv,
                            "extra": f"arXiv: {p.arxiv}{p.version}\nResearch Bridge ID: {p.canonical}" + (f"\nPublished DOI: {meta['published_doi']}" if meta.get("published_doi") else ""),
                            "tags": [{"tag": "source:alphaxiv"}], "collections": [collection]}
                data.update({k: v for k, v in proposed.items() if k in data or k == "key"})
                item = zotero.create(data)
                items.append(item)
        self.store.update(job["id"], item_key=item["key"])
        zotero.add_collection(item, collection)
        # Existing source metadata / user notes / attachments remain authoritative.
        if is_existing:
            self.store.update(job["id"], status="existing", error="", candidates=[])
            self.event("info", f"已关联已有文献：{p.title}")
            return
        note_key = self.store.key(job["id"], "note_key")
        if not zotero.get(note_key):
            note = zotero.template("note")
            note.update({"key": note_key, "parentItem": item["key"],
                         "note": "<h2>Research Nexus · 收藏来源</h2><p>" + html.escape(p.title) + "</p><p>" +
                         '<a href="' + html.escape(p.source_url, quote=True) + '">alphaXiv 原页面</a></p><p>来源文件夹：' +
                         html.escape(" / ".join(p.folder_names)) + "</p><p>归档时间：" + now() + "</p>"})
            zotero.create(note)
        if cfg["download_pdf"]:
            path = self.arxiv.pdf(p, self.root / "data" / "pdfs")
            if cfg.get("pdf_storage") == "linked_folder":
                path = place_linked_pdf(path, Path(cfg["linked_pdf_dir"]), job.get("pdf_path"))
            self.store.update(job["id"], pdf_path=str(path), pdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            if cfg.get("pdf_storage") == "linked_folder":
                self.link_pdf(job, item, zotero, path)
                self.store.update(job["id"], status="linked_archived", error="", candidates=[])
                self.event("info", f"已关联同步文件夹 PDF：{p.title}；云同步进度由 Google Drive 管理。")
                return
            elif cfg["upload_pdf"]:
                attachment_key = self.store.key(job["id"], "attachment_key")
                if not zotero.get(attachment_key):
                    attachment = zotero.template("attachment", linkMode="imported_file")
                    attachment.update({"key": attachment_key, "parentItem": item["key"], "title": "Full Text PDF",
                                       "filename": path.name, "contentType": "application/pdf"})
                    zotero.create(attachment)
                zotero.upload(attachment_key, path)
        self.store.update(job["id"], status="archived" if cfg["download_pdf"] and cfg["upload_pdf"] else "metadata_archived", error="", candidates=[])
        self.event("info", f"已归档：{p.title}")

    def link_pdf(self, job, item, zotero, path):
        journal_key = f"linked-attachment-migration:{job['id']}"
        migration = self.store.meta(journal_key)
        if migration:
            attachment_key = migration["new_key"]
            self.store.update(job["id"], attachment_key=attachment_key)
        else:
            attachment_key = self.store.key(job["id"], "attachment_key")
            existing = zotero.get(attachment_key)
            if existing and existing["data"].get("linkMode") != "linked_file":
                d = existing["data"]
                if (d.get("linkMode") != "imported_file" or d.get("parentItem") != item["key"] or
                        d.get("md5") or d.get("note")):
                    raise BridgeError("已记录的附件包含文件或人工内容，未自动替换。")
                migration = {"old_key":attachment_key, "new_key":self.store.new_key(), "old_trashed":False}
                # Persist both identities before either cloud mutation; retries
                # reconcile the same new key and never create another link.
                self.store.meta(journal_key, migration)
                attachment_key = migration["new_key"]
                self.store.update(job["id"], attachment_key=attachment_key)
        zotero.link_file(attachment_key, item["key"], path)
        if migration and not migration.get("old_trashed"):
            zotero.trash_empty_attachment(migration["old_key"], item["key"])
            migration["old_trashed"] = True
            self.store.meta(journal_key, migration)

    def resolve(self, job_id, action, item_key=None):
        if not self.lock.acquire(blocking=False):
            raise BridgeError("请等待当前归档完成。")
        try:
            job = self.store.job(job_id)
            if job["scope"] != self.scope() or job["status"] != "review":
                raise BridgeError("该任务不在当前文献库的待确认列表。")
            if action == "separate":
                self.store.update(job_id, allow_title_duplicate=1, status="queued", error="", candidates=[])
            elif action == "link" and item_key in [c["key"] for c in job["candidates"]]:
                self.store.update(job_id, item_key=item_key, status="queued", error="", candidates=[])
            else:
                raise BridgeError("请选择有效的重复处理方式。")
            self.event("info", "重复处理决定已保存，将在下一轮归档时应用。")
        finally:
            self.lock.release()

    def scheduler(self):
        while not self.stop.wait(2):
            if self.config.snapshot()["auto_sync"] and not self.missing() and time.monotonic() >= self.next_auto and not self.busy:
                try:
                    self.launch("sync")
                except BridgeError:
                    pass

    def openresearch_online(self):
        url = self.config.snapshot()["openresearch_url"]
        session = requests.Session()
        session.trust_env = False
        try:
            r = session.get(url, timeout=2)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def start_openresearch(self):
        native_host = self.root / "desktop" / "NativeDockHost.exe"
        if not native_host.is_file():
            raise BridgeError("本地窗口组件尚未编译，请运行 desktop/build-native-host.ps1。")
        subprocess.Popen([str(native_host), "--open-openresearch"], cwd=self.root,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {"ready": True, "native": True}

    def local_library(self, query=""):
        session = requests.Session()
        session.trust_env = False
        try:
            r = session.get("http://127.0.0.1:23119/api/users/0/items/top", params={"limit": 100, "q": query}, timeout=5)
            if r.status_code != 200:
                raise BridgeError(f"Zotero 本地接口返回 {r.status_code}；请在设置中允许其他应用与 Zotero 通信。")
            return [{"key": i["key"], "title": i["data"].get("title", ""), "authors": i.get("meta", {}).get("creatorSummary", ""),
                     "date": i["data"].get("date", ""), "url": i["data"].get("url", ""), "type": i["data"].get("itemType", "")}
                    for i in r.json() if i["data"].get("itemType") not in ("note", "attachment")]
        except requests.RequestException:
            raise BridgeError("Zotero 尚未运行，或本地接口不可用。可启动 Zotero 后重试，或使用工作台里的 Zotero 网页库。") from None

    def shutdown(self):
        self.stop.set()
        if self.orx_process and self.orx_process.poll() is None:
            self.orx_process.terminate()
        if self.orx_log:
            self.orx_log.close()
