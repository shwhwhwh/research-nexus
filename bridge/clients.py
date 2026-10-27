from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import quote, urlparse

import requests

from .domain import BridgeError, Paper, parse_arxiv_atom, parse_arxiv_html, parse_library


UA = "ResearchNexus/0.5 (local personal literature archiver)"


def validate_key(key, service):
    if key and (not key.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key)):
        raise BridgeError(f"{service} 密钥包含空白或非 ASCII 字符；请复制创建后显示的实际密钥值，不要填写名称或说明。")


class Http:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA
        self.not_before = 0.0

    def request(self, method, url, *, expected=(200,), **kwargs):
        delay = self.not_before - time.monotonic()
        if delay > 0:
            raise BridgeError(f"服务要求稍后重试，剩余约 {int(delay)+1} 秒。")
        try:
            r = self.session.request(method, url, timeout=kwargs.pop("timeout", (10, 60)), **kwargs)
        except requests.RequestException as exc:
            # Do not include request URLs: upload URLs may contain signed secrets.
            raise BridgeError(f"无法连接 {urlparse(url).hostname}（{type(exc).__name__}）。") from None
        for h in ("Backoff", "Retry-After"):
            try:
                self.not_before = max(self.not_before, time.monotonic() + min(float(r.headers.get(h, 0)), 86400))
            except ValueError:
                pass
        if r.status_code not in expected:
            if r.status_code in (401, 403):
                raise BridgeError(f"{urlparse(url).hostname} 拒绝访问（{r.status_code}），请检查密钥及读写权限。")
            if r.status_code == 413:
                raise BridgeError("Zotero 文件存储空间或请求大小超限；文献条目及本地 PDF 已保留，可处理后重试。")
            if r.status_code == 412:
                raise BridgeError("Zotero 数据已变化或请求已提交；下次将先核对已有条目再重试。")
            raise BridgeError(f"{urlparse(url).hostname} 返回 HTTP {r.status_code}。")
        return r


class AlphaClient:
    ENDPOINT = "https://api.alphaxiv.org/mcp/v1"

    def __init__(self, key, http=None):
        validate_key(key, "alphaXiv")
        self.http = http or Http()
        self.key = key
        self.session_id = None
        self.protocol = "2025-03-26"
        self.counter = 0
        self._tools = None

    def tools(self):
        if self._tools is None:
            if not self.key:
                raise BridgeError("请先填写 alphaXiv API Key。")
            result = self._rpc("initialize", {"protocolVersion": self.protocol, "capabilities": {},
                              "clientInfo": {"name": "research-nexus", "version": "0.4.0"}})
            self.protocol = result.get("protocolVersion", self.protocol)
            self._rpc("notifications/initialized", notification=True)
            self._tools = {t["name"]: t for t in self._rpc("tools/list").get("tools", [])}
        return self._tools

    def call(self, name, arguments):
        tools = self.tools()
        if name not in tools:
            raise BridgeError(f"alphaXiv 官方接口未提供 {name}；未猜测或调用未公开接口。")
        schema = tools[name].get("inputSchema", {})
        if set(schema.get("required", [])) - arguments.keys():
            raise BridgeError(f"alphaXiv {name} 缺少必要参数。")
        return self._rpc("tools/call", {"name": name, "arguments": arguments})

    def _rpc(self, method, params=None, notification=False):
        self.counter += 1
        data = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            data["params"] = params
        if not notification:
            data["id"] = self.counter
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json", "MCP-Protocol-Version": self.protocol}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        r = self.http.request("POST", self.ENDPOINT, headers=headers, json=data, expected=(200, 202, 204))
        if r.headers.get("Mcp-Session-Id"):
            self.session_id = r.headers["Mcp-Session-Id"]
        if notification:
            return {}
        if "text/event-stream" in r.headers.get("Content-Type", ""):
            messages = []
            # SSE is UTF-8 even if the server omits a charset. Requests otherwise
            # defaults text/* to latin-1; splitlines then mistakes C1 bytes or
            # Unicode separators inside JSON strings for protocol newlines.
            event_text = r.content.decode("utf-8-sig")
            for block in re.split(r"\r?\n\r?\n", event_text):
                payload = "\n".join(line[5:].lstrip().rstrip("\r") for line in block.split("\n") if line.startswith("data:"))
                if payload:
                    try:
                        messages.append(json.loads(payload))
                    except ValueError:
                        pass
            response = next((x for x in messages if x.get("id") == data["id"]), None)
            if response is None:
                raise BridgeError("alphaXiv MCP 未返回对应请求结果。")
        else:
            try:
                response = r.json()
            except ValueError:
                raise BridgeError("alphaXiv MCP 返回了非 JSON 数据。") from None
        if response.get("error"):
            err = response["error"]
            raise BridgeError(f"alphaXiv MCP 请求失败（{err.get('code', 'unknown')}）：{str(err.get('message', ''))[:200]}")
        result = response.get("result", {})
        if result.get("isError"):
            msg = " ".join(b.get("text", "") for b in result.get("content", []) if b.get("type") == "text")
            raise BridgeError(f"alphaXiv 文献库读取失败：{msg[:250]}")
        return result

    def library(self):
        if not self.key:
            raise BridgeError("请先在连接设置中填写 alphaXiv API Key。")
        result = self._rpc("initialize", {"protocolVersion": self.protocol, "capabilities": {},
                                         "clientInfo": {"name": "research-nexus", "version": "0.2.0"}})
        self.protocol = result.get("protocolVersion", self.protocol)
        self._rpc("notifications/initialized", notification=True)
        tools = self._rpc("tools/list").get("tools", [])
        if not any(t.get("name") == "list_library" for t in tools):
            raise BridgeError("当前 alphaXiv MCP 未暴露 list_library；已停止同步。")
        result = self._rpc("tools/call", {"name": "list_library", "arguments": {"include_papers": True}})
        return (*parse_library(result), result)


class ArxivClient:
    def __init__(self, http=None):
        self.http = http or Http()
        self.last_request = 0.0
        self.api_backoff = 0.0
        self.last_errors = {}

    def metadata(self, papers: list[Paper]):
        result = {}
        self.last_errors = {}
        ids = list(dict.fromkeys(p.arxiv + p.version for p in papers if p.arxiv))
        for start in range(0, len(ids), 50):
            # arXiv asks for at most one request per three seconds.
            time.sleep(max(0, self.last_request + 3 - time.monotonic()))
            batch = ids[start:start+50]
            try:
                if time.monotonic() < self.api_backoff:
                    raise BridgeError("arXiv API 暂不可用")
                r = self.http.request("GET", "https://export.arxiv.org/api/query",
                                      params={"id_list": ",".join(batch), "max_results": 50}, timeout=(8, 15))
                self.last_request = time.monotonic()
                result.update(parse_arxiv_atom(r.text))
            except Exception:
                self.api_backoff = time.monotonic() + 3600
            # Official abstract pages expose citation metadata and exact version information.
            for ident in batch:
                from .domain import arxiv_id
                aid, _ = arxiv_id(ident)
                if aid in result:
                    continue
                time.sleep(max(0, self.last_request + 3 - time.monotonic()))
                try:
                    r = self.http.request("GET", f"https://arxiv.org/abs/{ident}", timeout=(8, 25))
                    result[aid] = parse_arxiv_html(r.text, ident)
                except BridgeError as exc:
                    self.last_errors[aid] = str(exc)
                finally:
                    self.last_request = time.monotonic()
        return result

    def pdf(self, paper: Paper, root: Path):
        if not paper.arxiv or not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7})", paper.arxiv):
            raise BridgeError("当前仅自动下载已验证 arXiv 标识的公开 PDF。")
        filename = (paper.arxiv + paper.version).replace("/", "_") + ".pdf"
        root.mkdir(parents=True, exist_ok=True)
        path = root / filename
        if path.exists() and path.read_bytes()[:5] == b"%PDF-":
            return path
        url = f"https://arxiv.org/pdf/{paper.arxiv}{paper.version}"
        r = self.http.request("GET", url, stream=True, timeout=(10, 90))
        content_type = r.headers.get("Content-Type", "").split(";")[0].lower()
        if content_type not in ("application/pdf", "application/octet-stream"):
            r.close()
            raise BridgeError("下载返回的内容不是 PDF（可能为登录页或限流页）。")
        tmp = path.with_suffix(".part")
        size, signature = 0, b""
        try:
            with tmp.open("wb") as f:
                for chunk in r.iter_content(65536):
                    if not chunk:
                        continue
                    if not signature:
                        signature = chunk[:5]
                        if signature != b"%PDF-":
                            raise BridgeError("下载文件缺少 PDF 签名；未保存到文献库。")
                    size += len(chunk)
                    if size > 150 * 1024 * 1024:
                        raise BridgeError("PDF 超过当前 150 MB 下载上限。")
                    f.write(chunk)
            if size < 100:
                raise BridgeError("PDF 文件为空或不完整。")
            tmp.replace(path)
        except requests.RequestException:
            raise BridgeError("PDF 下载中断；下次可重新下载。") from None
        finally:
            r.close()
            tmp.unlink(missing_ok=True)
        return path


class ZoteroClient:
    def __init__(self, user_id, key, http=None):
        validate_key(key, "Zotero")
        if not str(user_id).isdigit() or not key:
            raise BridgeError("请先填写 Zotero 数字 User ID 和具有文献库写入权限的 API Key。")
        self.http = http or Http()
        self.base = f"https://api.zotero.org/users/{user_id}"
        self.headers = {"Zotero-API-Key": key, "Zotero-API-Version": "3"}
        self.templates = {}

    def req(self, method, suffix, **kwargs):
        headers = {**self.headers, **kwargs.pop("headers", {})}
        return self.http.request(method, self.base + suffix, headers=headers, **kwargs)

    def all(self, suffix):
        items, version = [], None
        for start in range(0, 1000000, 100):
            r = self.req("GET", suffix, params={"limit": 100, "start": start, "includeTrashed": 0})
            current = r.headers.get("Last-Modified-Version")
            if version is not None and current and current != version:
                raise BridgeError("Zotero 文献库在读取期间发生变化；本次未继续写入，请重试。")
            version = current
            batch = r.json()
            if not isinstance(batch, list):
                raise BridgeError("Zotero 列表响应格式不正确。")
            items.extend(batch)
            if len(batch) < 100:
                return items
        raise BridgeError("Zotero 列表超过当前读取上限。")

    def get(self, key):
        if not re.fullmatch(r"[A-Z0-9]{8}", key):
            raise BridgeError("Zotero 条目编号无效。")
        r = self.req("GET", f"/items/{key}", expected=(200, 404))
        return r.json() if r.status_code == 200 else None

    def template(self, item_type, **params):
        cache_key = (item_type, tuple(params.items()))
        if cache_key not in self.templates:
            r = self.http.request("GET", "https://api.zotero.org/items/new", headers={"Zotero-API-Version": "3"},
                                  params={"itemType": item_type, **params})
            self.templates[cache_key] = r.json()
        return dict(self.templates[cache_key])

    def create(self, data):
        # Version 0 makes a client-keyed write create-only. It also prevents a
        # key collision or a stale retry from overwriting an existing object.
        r = self.req("POST", "/items", json=[{**data, "version": 0}])
        body = r.json()
        success = body.get("successful", {}).get("0") or body.get("success", {}).get("0")
        if not success and "0" not in body.get("unchanged", {}):
            failed = body.get("failed", {}).get("0", {})
            raise BridgeError(f"Zotero 条目未保存（{failed.get('code','unknown')}）：{str(failed.get('message',''))[:200]}")
        item = self.get(data["key"])
        if not item:
            raise BridgeError("Zotero 写入后未能读回条目；保留原编号，下次核对。")
        return item

    def collection(self, name, parent=None):
        matches = [c for c in self.all("/collections") if c.get("data", {}).get("name") == name and
                   (c.get("data", {}).get("parentCollection") or None) == (parent or None)]
        if len(matches) > 1:
            raise BridgeError("目标分类存在多个同名顶层分类，请更换为唯一名称。")
        if matches:
            return matches[0]["key"]
        # Conditional library write prevents duplicate collection creation on races.
        r = self.req("GET", "/collections", params={"limit": 1})
        version = r.headers.get("Last-Modified-Version")
        if not version:
            raise BridgeError("Zotero 未返回文献库版本，无法安全创建分类。")
        value = {"name": name}
        if parent:
            value["parentCollection"] = parent
        response = self.req("POST", "/collections", json=[value], headers={"If-Unmodified-Since-Version": version}).json()
        created = response.get("successful", {}).get("0") or response.get("success", {}).get("0")
        if isinstance(created, str):
            return created
        if isinstance(created, dict):
            return created.get("key") or created["data"]["key"]
        raise BridgeError("Zotero 目标分类创建失败。")

    def add_collection(self, item, collection):
        key = item["key"]
        for _ in range(3):
            latest = self.get(key)
            if not latest:
                raise BridgeError("已有 Zotero 条目被删除，未自动重新创建。")
            d = latest["data"]
            if collection in d.get("collections", []):
                return latest
            r = self.req("PATCH", f"/items/{key}", json={"collections": list(dict.fromkeys(d.get("collections", []) + [collection]))},
                         headers={"If-Unmodified-Since-Version": str(latest["version"])}, expected=(204, 412))
            if r.status_code == 204:
                return self.get(key)
        raise BridgeError("Zotero 条目连续发生并发修改；已保留人工内容，请稍后重试。")

    def add_tags(self, item, tags):
        for _ in range(3):
            latest = self.get(item["key"])
            if not latest:
                raise BridgeError("Zotero 文献已删除，未重新创建。")
            existing = latest["data"].get("tags", [])
            added = [{"tag": t} for t in tags if t not in {x.get("tag") for x in existing}]
            if not added:
                return latest
            r = self.req("PATCH", f"/items/{item['key']}", json={"tags": existing + added},
                         headers={"If-Unmodified-Since-Version": str(latest["version"])}, expected=(204, 412))
            if r.status_code == 204:
                return self.get(item["key"])
        raise BridgeError("Zotero 标签存在并发修改，请稍后重试。")

    def link_file(self, attachment_key, parent_key, path):
        current = self.get(attachment_key)
        if current:
            data = current["data"]
            if data.get("parentItem") != parent_key or data.get("itemType") != "attachment":
                raise BridgeError("已记录的附件与论文不匹配，未修改。")
            if data.get("linkMode") == "linked_file":
                if data.get("path") != str(path):
                    raise BridgeError("已有附件链接到其他位置；请先核对路径，未自动更改。")
                return current
            raise BridgeError("Zotero 不允许更改已有附件类型，需要先保存新的文件链接。")
        data = self.template("attachment", linkMode="linked_file")
        data.update({"key": attachment_key, "parentItem": parent_key, "path": str(path),
                     "title": "Full Text PDF", "contentType": "application/pdf"})
        return self.create(data)

    def append_note_metadata(self, key, ownership_marker, marker, text):
        import html
        for _ in range(3):
            current = self.get(key)
            if not current or current["data"].get("itemType") != "note" or ownership_marker not in current["data"].get("note", ""):
                raise BridgeError("无法确认引用笔记归属，未修改。")
            content = current["data"]["note"]
            if marker in content:
                return
            content += "<p>" + html.escape(text) + "</p><p>" + html.escape(marker) + "</p>"
            r = self.req("PATCH", "/items/" + key, json={"note": content},
                headers={"If-Unmodified-Since-Version": str(current["version"])}, expected=(204, 412))
            if r.status_code == 204:
                return
        raise BridgeError("引用笔记正在被编辑，未覆盖人工内容，请稍后重试。")

    def trash_empty_attachment(self, attachment_key, parent_key):
        current = self.get(attachment_key)
        if not current or current["data"].get("deleted"):
            return
        data = current["data"]
        if (data.get("itemType") != "attachment" or data.get("parentItem") != parent_key or
                data.get("linkMode") != "imported_file" or data.get("md5") or data.get("note")):
            raise BridgeError("原附件已包含文件或人工内容，未自动移入回收站。")
        self.req("PATCH", f"/items/{attachment_key}", json={"deleted":1},
                 headers={"If-Unmodified-Since-Version":str(current["version"])}, expected=(204,))

    def upload(self, attachment_key, path: Path):
        content = path.read_bytes()
        digest = hashlib.md5(content).hexdigest()
        item = self.get(attachment_key)
        if item and item["data"].get("md5") == digest:
            return
        r = self.req("POST", f"/items/{attachment_key}/file",
                     data={"md5": digest, "filename": path.name, "filesize": len(content), "mtime": int(path.stat().st_mtime * 1000)},
                     headers={"If-None-Match": "*"})
        auth = r.json()
        if auth.get("exists"):
            return
        url = auth.get("url", "")
        parsed = urlparse(url)
        # Only the upload destination returned by Zotero is used, without API credentials.
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise BridgeError("Zotero 返回了不安全的文件上传地址。")
        payload = auth["prefix"].encode() + content + auth["suffix"].encode()
        transport = Http()
        transport.request("POST", url, data=payload, headers={"Content-Type": auth["contentType"]}, expected=(200, 201, 204), timeout=(10, 120))
        self.req("POST", f"/items/{attachment_key}/file", data={"upload": auth["uploadKey"]},
                 headers={"If-None-Match": "*"}, expected=(204,))


def local_zotero(path="/api/"):
    session = requests.Session()
    session.trust_env = False
    try:
        r = session.get("http://127.0.0.1:23119" + path, timeout=3)
        return {"online": r.status_code == 200, "status": r.status_code,
                "version": r.headers.get("Zotero-API-Version"), "server_id": r.headers.get("Zotero-Server-ID")}
    except requests.RequestException:
        return {"online": False, "status": None}


def local_items():
    """Read only; prevent cloud writes that would duplicate unsynced local items."""
    session = requests.Session()
    session.trust_env = False
    out = []
    try:
        for start in range(0, 1000000, 100):
            r = session.get("http://127.0.0.1:23119/api/users/0/items/top",
                            params={"limit": 100, "start": start}, timeout=10)
            if r.status_code != 200:
                raise BridgeError("Zotero 本地文献无法读取；请启动 Zotero 并启用本地通信，再归档。")
            batch = r.json()
            if not isinstance(batch, list):
                raise BridgeError("Zotero 本地列表格式异常。")
            out.extend(batch)
            if len(batch) < 100:
                return out
    except requests.RequestException:
        raise BridgeError("请先启动 Zotero，使 Bridge 能检查尚未同步的本地文献，避免重复归档。") from None
    raise BridgeError("Zotero 本地文献数量超过读取上限。")
