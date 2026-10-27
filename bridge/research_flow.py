"""Read ORX citations; project libraries in alphaXiv, provenance notes in Zotero.

No browser/session-token scraping and no direct writes to application databases.
Research context is evidence from the conversation, never an asserted PDF quote.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import html
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import quote, unquote, urlparse
import xml.etree.ElementTree as ET

import requests

from .clients import AlphaClient
from .domain import BridgeError, Paper, arxiv_id, doi_id, find_match, parse_library
from .files import place_linked_pdf
from .storage import Config, Store

PDFIUM_LOCK = threading.Lock()

DEFAULT_CATEGORIES = [
    {"name": "模型与方法", "keywords": ["architecture", "model", "transformer", "attention", "模型", "方法"]},
    {"name": "训练与优化", "keywords": ["training", "optimizer", "scaling", "训练", "优化", "loss"]},
    {"name": "数据与评测", "keywords": ["dataset", "benchmark", "evaluation", "数据", "评测", "accuracy"]},
]
ARXIV_LINK = re.compile(r'(?:https?://(?:www\.)?(?:arxiv\.org|alphaxiv\.org)/(?:abs|pdf|html)/|\barxiv\s*:\s*|"(?:arxiv_id|arxiv|universal_paper_id)"\s*:\s*")((?:\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7})(?:v\d+)?)(?:\.pdf)?(?![\w.])', re.I)
# Stop at Markdown brackets and CJK prose punctuation. Parentheses inside a
# DOI remain valid; unmatched ASCII link-closing parentheses are trimmed below.
DOI_LINK = re.compile(r'(?:https?://(?:dx\.)?doi\.org/|\bdoi\s*:\s*|"doi"\s*:\s*")(10\.\d{4,9}/[^\s<>"\[\]，。；：、（）【】《》]+)', re.I)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def active_messages(payload):
    """Follow only the selected branch. Never copy abandoned branch citations."""
    messages = payload.get("messages", [])
    leaf = payload.get("activeLeafId")
    if not leaf or not any(m.get("parentId") for m in messages):
        return messages
    by_id = {m["id"]: m for m in messages}
    if leaf not in by_id:
        raise BridgeError("对话分支仍在更新，本次跳过，稍后重试。")
    result, seen = [], set()
    while leaf:
        if leaf in seen or leaf not in by_id:
            raise BridgeError("对话分支不完整，本次未导出。")
        seen.add(leaf)
        message = by_id[leaf]
        result.append(message)
        leaf = message.get("parentId")
    return result[::-1]


def text_parts(message, include_tools=False):
    if message.get("role") not in ("assistant", "user"):
        return
    for index, part in enumerate(message.get("parts", [])):
        if part.get("type") in ("text", "steer") and isinstance(part.get("text"), str):
            yield part.get("id", str(index)), part["text"], message["role"] + "_text"
        elif include_tools and part.get("type") == "tool":
            state = part.get("state", {})
            if state.get("status") not in ("completed", "success", "done") or not state.get("output"):
                continue
            # Tool inputs and reasoning are not research evidence. Only completed
            # outputs can be stored, explicitly labelled as discovery results.
            output = state["output"]
            yield part.get("id", str(index)), output if isinstance(output, str) else json.dumps(output, ensure_ascii=False), "tool_discovery"


def category_for(text, categories):
    text = text.casefold()
    scores = [sum(text.count(k.casefold()) for k in c["keywords"] if k) for c in categories]
    return categories[max(range(len(scores)), key=scores.__getitem__)]["name"] if scores and max(scores) else "待分类"


def extract_citations(project, session, payload, options, base):
    rows = []
    for message in active_messages(payload):
        # Historical imported ORX messages may have no completedAt. They remain
        # usable in an idle session, labelled unknown; busy sessions are skipped.
        if message.get("role") == "assistant" and not message.get("completedAt") and session.get("busy"):
            continue
        if message.get("role") == "user" and not options.get("include_user", True):
            continue
        for part_id, text, kind in text_parts(message, options.get("include_tools", False)):
            # Match explicit identifiers, not bare numbers, titles or command input.
            matches = sorted([(m.start(), m.end(), "arxiv", m[1]) for m in ARXIV_LINK.finditer(text)] +
                             [(m.start(), m.end(), "doi", m[1]) for m in DOI_LINK.finditer(text)])
            for start, end, scheme, value in matches:
                aid, version = arxiv_id(value) if scheme == "arxiv" else ("", "")
                value = unquote(value).rstrip(".,;}")
                while value.endswith(")") and value.count(")") > value.count("("):
                    value = value[:-1]
                doi = doi_id(value) if scheme == "doi" else ""
                if not aid and not doi:
                    continue
                # Store the exact containing paragraph. Long paragraphs have an
                # explicit excerpt boundary; surrounding papers are not fabricated.
                left = max(text.rfind("\n\n", 0, start) + 2, 0)
                if left == 1:
                    left = 0
                right = text.find("\n\n", end)
                right = len(text) if right < 0 else right
                left, right = max(left, start - 2500), min(right, end + 2500)
                context = text[left:right]
                key = "arxiv:" + aid if aid else "doi:" + doi
                row = {"paper_id": key, "arxiv": aid, "version": version, "doi": doi,
                       "source_url": "https://arxiv.org/abs/" + aid + version if aid else "https://doi.org/" + doi,
                       "project_id": project["id"], "project_name": project["name"], "session_id": session["id"],
                       "session_title": session.get("title", "研究对话"), "message_id": message["id"],
                       "part_id": part_id, "created_at": message.get("createdAt"), "source_kind": kind,
                       "context": context, "excerpted": left > 0 or right < len(text),
                       "completion_state": "recorded" if message.get("completedAt") else "legacy_or_unknown",
                       "source_chat_url": base + "/projects/" + quote(project["id"], safe="") + "?session=" + quote(session["id"], safe=""),
                       "category": category_for(context, options.get("categories", DEFAULT_CATEGORIES))}
                row["citation_id"] = fingerprint([project["id"], session["id"], message["id"], part_id, key, context])
                if not any(r["citation_id"] == row["citation_id"] for r in rows):
                    rows.append(row)
    return rows


def validate_options(options):
    if not isinstance(options, dict):
        raise BridgeError("研究同步配置必须是对象。")
    if set(options) - {"project_ids", "max_papers", "include_tools", "include_user", "categories", "download_pdf", "highlight_quotes", "classifier", "auto_discover"}:
        raise BridgeError("研究同步包含未知配置。")
    ids = options.get("project_ids", [])
    if type(options.get("auto_discover", False)) is not bool:
        raise BridgeError("自动发现开关须为布尔值。")
    if options.get("auto_discover") and ids != []:
        raise BridgeError("自动发现模式不使用固定项目名单。")
    if not isinstance(ids, list) or (not ids and not options.get("auto_discover")) or len(ids) > 60 or any(not isinstance(i, str) or not re.fullmatch(r"[\w-]{1,100}", i) for i in ids):
        raise BridgeError("请选择明确的 OpenResearch 项目；不默认导出所有项目。")
    if type(options.get("max_papers", 25)) is not int or not 1 <= options.get("max_papers", 25) <= 200:
        raise BridgeError("单次论文数量须为 1–200。")
    for key in ("include_tools", "include_user", "download_pdf", "highlight_quotes"):
        if key in options and type(options[key]) is not bool:
            raise BridgeError("研究同步开关须为布尔值。")
    categories = options.get("categories", DEFAULT_CATEGORIES)
    if not isinstance(categories, list) or len(categories) > 20:
        raise BridgeError("最多配置 20 个研究分类。")
    names = set()
    if options.get("classifier", "keywords") not in ("keywords", "codex", "claude"):
        raise BridgeError("请选择关键词规则、Codex 或 Claude Code 分类。")
    for c in categories:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not 1 <= len(c["name"]) <= 80 or c["name"] in names:
            raise BridgeError("分类名称须唯一且不超过 80 字。")
        names.add(c["name"])
        if not isinstance(c.get("keywords"), list) or len(c["keywords"]) > 40 or any(not isinstance(k, str) or not 1 <= len(k) <= 100 for k in c["keywords"]):
            raise BridgeError("每个分类最多 40 个关键词。")
    return options


class ResearchFlow:
    def __init__(self, root, engine, redact=str, classifier=None):
        self.root, self.engine, self.redact = Path(root), engine, redact
        self.path = self.root / "data" / "designer" / "research-receipts.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.classifier = classifier
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"keys": {}}

    def consent_id(self, options):
        if options.get("auto_discover"):
            return fingerprint({"provider": options.get("classifier", "keywords"), "source": self.base(),
                                "project_scope": "all-current-and-future", "data": "citation_context"})
        return fingerprint({"provider": options.get("classifier", "keywords"), "project_ids": sorted(set(options["project_ids"])), "data": "citation_context"})

    def authorized(self, options):
        return options.get("classifier", "keywords") == "keywords" or self.consent_id(options) in self.state.get("model_consents", [])

    def authorize(self, options):
        validate_options(options)
        with self.lock:
            consents = self.state.setdefault("model_consents", [])
            token = self.consent_id(options)
            if token not in consents:
                consents.append(token)
                Config._atomic(self.path, self.state)

    def base(self):
        if not self.engine:
            raise BridgeError("本地研究引擎不可用。")
        value = self.engine.config.snapshot()["openresearch_url"].rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise BridgeError("OpenResearch 必须使用本机 HTTP 服务基础地址。")
        return value

    def get(self, path, params=None):
        try:
            with requests.Session() as s:
                s.trust_env = False
                r = s.get(self.base() + path, params=params, timeout=(3, 45), allow_redirects=False)
                if r.status_code != 200:
                    raise BridgeError(f"OpenResearch 读取失败（HTTP {r.status_code}）。")
                if len(r.content) > 20_000_000:
                    raise BridgeError("OpenResearch 对话过大，请拆分项目。")
                return r.json()
        except (requests.RequestException, ValueError):
            raise BridgeError("无法读取 OpenResearch；请确认本地应用运行、API 地址正确，然后重试。") from None

    def projects(self):
        result = [{"id": p["id"], "name": p["name"]} for p in self.get("/api/projects")["projects"]]
        if any(not isinstance(p['id'], str) or not re.fullmatch(r'[\w-]{1,100}', p['id']) or
               not isinstance(p['name'], str) or not p['name'] for p in result) or len({p['id'] for p in result}) != len(result):
            raise BridgeError("OpenResearch 项目列表格式不正确，未扩大同步范围。")
        return result

    def project_label(self, project):
        """Keep the original folder name when a project is renamed."""
        with self.lock:
            labels = self.state.setdefault('project_labels', {}).setdefault(fingerprint(self.base()), {})
            pid = project['project_id'] if 'project_id' in project else project['id']
            name = project.get('project_name', project.get('name', ''))
            if pid not in labels:
                label = (name[:65] + ' · ' + pid[:8] + ' · ORX')[:100]
                if label in labels.values():
                    label = name[:65] + ' · ' + fingerprint(pid)[:16] + ' · ORX'
                labels[pid] = label
                Config._atomic(self.path, self.state)
            return labels[pid]

    def delivery_scope(self, options, destination):
        cfg = self.engine.config.snapshot()
        key_name = 'alphaxiv_key' if destination == 'alpha' else 'zotero_key'
        return fingerprint([self.base(), destination, cfg.get('zotero_user_id') if destination == 'zotero' else '',
                            fingerprint(self.engine.config.secret(key_name)),
                            {k: v for k, v in options.items() if k not in ('project_ids', 'max_papers')}])

    def acknowledge(self, records, options, destination, result, *, failed=False):
        if not options.get('auto_discover'):
            return
        completed = (set() if failed else {r['citation_id'] for r in records} if destination == 'alpha'
                     else set(result.get('completed_citations', [])))
        with self.lock:
            state = self.state.setdefault('deliveries', {}).setdefault(self.delivery_scope(options, destination), {})
            for row in records:
                state[row['citation_id']] = {'done': row['citation_id'] in completed, 'attempted': time.time()}
            Config._atomic(self.path, self.state)

    def ensure_project_roots(self, projects, destination):
        """Create empty project roots too; cache discoveries, not citation writes."""
        cfg = self.engine.config.snapshot()
        scope = fingerprint([self.base(), destination, cfg.get('zotero_user_id', ''),
                             fingerprint(self.engine.config.secret('alphaxiv_key' if destination == 'alpha' else 'zotero_key'))])
        with self.lock:
            roots = self.state.setdefault('project_roots', {}).setdefault(scope, {})
            pending = [p for p in projects if p['id'] not in roots]
            if not pending:
                return 0
            if destination == 'alpha':
                client = self.engine.alpha_factory(self.engine.config.secret('alphaxiv_key'))
                folders, _, _ = parse_library(client.call('list_library', {'include_papers': False}))
            else:
                client = self.engine.zotero_factory(cfg['zotero_user_id'], self.engine.config.secret('zotero_key'))
            created = 0
            for project in pending:
                name = self.project_label(project)
                if destination == 'alpha':
                    matches = [f for f in folders if f['name'] == name and not f.get('parent_id')]
                    if len(matches) > 1:
                        raise BridgeError('项目文件夹存在多个同名目录，请先核对。')
                    if matches:
                        key = matches[0]['id']
                    else:
                        value = self._payload(client.call('create_folder', {'name': name}))
                        key = value.get('folder_id') or value.get('id')
                        if not key:
                            raise BridgeError('未取得新项目文件夹编号，请重新核对。')
                        created += 1
                    # A lost create response is reconciled by name on the next scan.
                else:
                    key = client.collection(name)
                roots[project['id']] = key
                Config._atomic(self.path, self.state)
            return created

    def discover(self, scopes):
        """Scopes and destinations come only from active, validated RN edges."""
        source = self.base()
        with self.lock:
            old = dict(self.state.get('discovery', {}).get(fingerprint(source), {}))
        status = {**old, 'source': source, 'last_checked': time.time(), 'error': ''}
        try:
            for options, _ in scopes:
                validate_options(options)
                if not options.get('auto_discover') or not self.authorized(options):
                    raise BridgeError('自动发现尚未获得当前来源和模型提供商的授权。')
            projects = self.projects()
            status['new_projects'] = [p for p in projects if p['id'] not in old.get('known_ids', [])]
            status['projects'] = projects
            status['known_ids'] = sorted(set(old.get('known_ids', [])) | {p['id'] for p in projects})
            status['targets'] = sorted({destination for _, destination in scopes})
            for destination in status['targets']:
                self.ensure_project_roots(projects, destination)
        except Exception as error:
            status['error'] = self.redact(str(error) if isinstance(error, BridgeError) else '自动发现暂未完成，请稍后重试。')
        with self.lock:
            self.state.setdefault('discovery', {})[fingerprint(source)] = status
            Config._atomic(self.path, self.state)
        return status

    def discovery_status(self):
        # Do not wait on the remote folder-creation lock to render the dashboard.
        try:
            return dict(self.state.get('discovery', {}).get(fingerprint(self.base()), {})) if self.engine else {}
        except BridgeError as error:
            return {'error': self.redact(error)}

    def collect(self, options, destination=None):
        validate_options(options)
        if not self.authorized(options):
            raise BridgeError("尚未授权将所选项目的引用上下文交给此模型服务。请在项目文献向导中明确勾选授权，或选择关键词规则。")
        projects = {p["id"]: p for p in self.projects()}
        project_ids = list(projects) if options.get('auto_discover') else options['project_ids']
        records, warnings = [], []
        for pid in project_ids:
            if pid not in projects:
                raise BridgeError("所选 OpenResearch 项目已不存在，请重新选择。")
            sessions = self.get("/api/chat/sessions", {"projectId": pid})["sessions"]
            for session in sessions:
                if session.get("projectId") != pid:
                    warnings.append("已拒绝不属于所选项目的对话。")
                    continue
                if session.get("busy"):
                    warnings.append("已跳过正在生成中的对话，下次继续读取。")
                    continue
                try:
                    payload = self.get("/api/chat/sessions/" + quote(session["id"], safe="") + "/messages")
                    records.extend(extract_citations(projects[pid], session, payload, options, self.base()))
                except BridgeError as e:
                    warnings.append(str(e))
        # Cap by paper, keeping all exact citation occurrences of selected papers.
        total_papers = len({r['paper_id'] for r in records})
        if options.get('auto_discover') and destination:
            delivery = self.state.get('deliveries', {}).get(self.delivery_scope(options, destination), {})
            pending = [r for r in records if not delivery.get(r['citation_id'], {}).get('done')]
            # Never let completed papers or persistent failures starve new citations.
            attempts = {}
            for row in pending:
                attempts[row['paper_id']] = min(attempts.get(row['paper_id'], float('inf')),
                                                delivery.get(row['citation_id'], {}).get('attempted', 0))
            identities = sorted(dict.fromkeys(r['paper_id'] for r in pending), key=lambda pid: attempts[pid])
        else:
            identities = list(dict.fromkeys(r["paper_id"] for r in records))
        selected = set(identities[:options.get("max_papers", 25)])
        records = [r for r in records if r["paper_id"] in selected and
                   (not options.get('auto_discover') or not destination or not delivery.get(r['citation_id'], {}).get('done'))]
        records = json.loads(self.redact(json.dumps(records, ensure_ascii=False)))
        classifier = options.get("classifier", "keywords")
        if classifier != "keywords" and records:
            if not self.classifier:
                raise BridgeError("语义分类 Agent 不可用。")
            cache = self.state.setdefault("classifications", {})
            def token(row):
                return fingerprint([row["citation_id"], options.get("categories", DEFAULT_CATEGORIES), classifier])
            missing = [r for r in records if token(r) not in cache]
            if missing:
                decisions = self.classifier(missing, options)
                if set(decisions) != {r["citation_id"] for r in missing}:
                    raise BridgeError("Agent 未逐条返回分类，未继续写入。")
                with self.lock:
                    for row in missing:
                        cache[token(row)] = decisions[row["citation_id"]]
                    Config._atomic(self.path, self.state)
            for row in records:
                row.update(category=cache[token(row)]["category"], category_reason=cache[token(row)]["reason"], classifier=classifier)
        return {"records": records, "papers": len(selected), "citations": len(records),
                "remaining_papers": max(0, len(identities) - len(selected)), "warnings": warnings,
                "projects": [projects[pid] for pid in project_ids], "total_papers": total_papers,
                "auto_discover": options.get('auto_discover', False),
                "classification": classifier + " · 无法判断时归入待分类", "read_only": True}

    def capabilities(self):
        if not self.engine:
            return {"alpha_folders": False, "alpha_note_write": False, "alpha_highlight_write": False, "fallback": "zotero"}
        tools = AlphaClient(self.engine.config.secret("alphaxiv_key")).tools()
        return {"alpha_folders": all(t in tools for t in ("create_folder", "list_library", "save_papers_to_folder")),
                "alpha_note_write": False, "alpha_highlight_write": False,
                "alpha_note_read": "get_paper_notes" in tools, "tools": sorted(tools), "fallback": "zotero",
                "reason": "官方 MCP 当前未公开笔记/高亮写入接口。分类收藏写到 alphaXiv，引用笔记写到 Zotero。"}

    def key(self, token):
        if token not in self.state["keys"]:
            self.state["keys"][token] = Store.new_key()
            Config._atomic(self.path, self.state)
        return self.state["keys"][token]

    @staticmethod
    def _payload(result):
        if isinstance(result.get("structuredContent"), dict):
            return result["structuredContent"]
        for b in result.get("content", []):
            if b.get("type") == "text":
                try:
                    return json.loads(b["text"])
                except ValueError:
                    try:
                        root = ET.fromstring(b["text"])
                        out = dict(root.attrib)
                        out.update({e.tag: e.text for e in root if e.text})
                        return out
                    except ET.ParseError:
                        pass
        raise BridgeError("alphaXiv 写入响应未识别，须读回确认后重试。")

    def alpha_sync(self, records, *, dry_run=False):
        if dry_run:
            return {"destination": "alphaXiv", "papers": len({r['paper_id'] for r in records}), "preview": records,
                    "notes": "alphaXiv 无官方笔记/高亮写入接口；请启用配套 Zotero 引用笔记连线。"}
        if not records:
            return {'destination': 'alphaXiv', 'verified_memberships': 0, 'created_folders': 0, 'skipped': [],
                    'note_write_supported': False, 'highlight_write_supported': False}
        with self.lock:
            client = self.engine.alpha_factory(self.engine.config.secret("alphaxiv_key"))
            folders, _, _ = parse_library(client.call("list_library", {"include_papers": False}))
            created, saved, skipped = [], 0, []
            def folder(name, parent=None):
                matches = [f for f in folders if f["name"] == name and (f.get("parent_id") or None) == parent]
                if len(matches) > 1:
                    raise BridgeError("alphaXiv 同一父目录有重复分类，请先核对。")
                if matches:
                    return matches[0]["id"]
                result = self._payload(client.call("create_folder", {"name": name, **({"parent_folder_id": parent} if parent else {})}))
                fid = result.get("folder_id") or result.get("id")
                if not fid:
                    raise BridgeError("alphaXiv 未返回新文件夹 ID，请重新读取后重试。")
                folders.append({"id": fid, "name": name, "parent_id": parent})
                created.append(fid)
                return fid
            seen = set()
            for row in records:
                if not row.get("arxiv"):
                    skipped.append({"paper_id": row["paper_id"], "reason": "alphaXiv 收藏接口仅接受支持的论文标识；DOI 论文交给 Zotero。"})
                    continue
                root = folder(self.project_label(row))
                child = folder(row["category"], root)
                for fid in (root, child):
                    token = (fid, row["arxiv"])
                    if token in seen:
                        continue
                    # Official save operation is additive and idempotent. Read
                    # back exact membership; never trust a successful HTTP alone.
                    client.call("save_papers_to_folder", {"folder_id": fid, "paper_ids_or_urls": [row["arxiv"] + row.get("version", "")]})
                    _, papers, _ = parse_library(client.call("list_library", {"include_papers": True, "paper_ids_or_urls": [row["arxiv"]]}))
                    if not any(p.arxiv == row["arxiv"] and fid in p.folders for p in papers):
                        raise BridgeError("alphaXiv 未能读回目标收藏；保留已有成果，下次幂等重试。")
                    seen.add(token); saved += 1
            return {"destination": "alphaXiv", "verified_memberships": saved, "created_folders": len(created), "skipped": skipped,
                    "note_write_supported": False, "highlight_write_supported": False}

    def zotero_sync(self, records, options, *, dry_run=False):
        if dry_run:
            return {"destination": "Zotero", "papers": len({r['paper_id'] for r in records}), "citation_notes": len(records),
                    "preview": records, "highlight_policy": "仅对 PDF 中逐字核实的引文创建高亮；摘要/上下文只保存为笔记。"}
        if not records:
            return {'destination': 'Zotero', 'created_papers': 0, 'created_notes': 0, 'existing_notes': 0,
                    'created_annotations': 0, 'unlocated_quotes': 0, 'review': [], 'papers': [], 'completed_citations': []}
        with self.lock, self.engine.paper_write_lock:
            cfg = self.engine.config.snapshot()
            client = self.engine.zotero_factory(cfg["zotero_user_id"], self.engine.config.secret("zotero_key"))
            scope = "zotero:" + cfg["zotero_user_id"] + ":"
            items = client.all("/items/top")
            local = self.engine.local_reader()
            if not isinstance(local, list):
                raise BridgeError("无法核对 Zotero 本地文献，未执行写入。")
            report = {"destination": "Zotero", "created_papers": 0, "created_notes": 0, "existing_notes": 0,
                      "created_annotations": 0, "unlocated_quotes": 0, "review": [], "papers": []}
            report['completed_citations'] = []
            parents, collections = {}, {}
            for row in records:
                paper = Paper(row["paper_id"], arxiv=row.get("arxiv", ""), version=row.get("version", ""), doi=row.get("doi", ""))
                if row["paper_id"] not in parents:
                    identity = row["paper_id"]
                    if identity in parents:
                        item = parents[identity]
                    else:
                        status, matches = find_match(paper, items)
                        _, local_matches = find_match(paper, local)
                        if status == "review" or any(i["key"] not in {v["key"] for v in items} for i in local_matches):
                            report["review"].append({"paper_id": identity, "reason": "存在多份/未同步的本地文献，请先核对并同步。"})
                            continue
                        if status == "existing":
                            item = matches[0]
                        else:
                            key = self.key(scope + "paper:" + identity)
                            item = client.get(key)
                            if item:
                                if find_match(paper, [item])[0] != "existing":
                                    raise BridgeError("已记录条目编号发生冲突，未覆盖。")
                            else:
                                metadata = self.metadata(paper)
                                if not metadata:
                                    report["review"].append({"paper_id": identity, "reason": "未取得权威元数据，暂缓创建。"})
                                    continue
                                data = client.template("preprint" if paper.arxiv else "journalArticle")
                                values = {"key": key, "title": metadata["title"], "creators": [{"creatorType": "author", "name": a} for a in metadata.get("authors", [])],
                                          "url": row["source_url"], "extra": ("arXiv: " + paper.arxiv + paper.version + "\n" if paper.arxiv else "") + "Research Nexus source: OpenResearch",
                                          "DOI": paper.doi, "date": metadata.get("published", ""), "abstractNote": metadata.get("abstract", "")}
                                data.update({k: v for k, v in values.items() if k in data or k == "key"})
                                item = client.create(data); items.append(item); report["created_papers"] += 1
                        parents[identity] = item
                else:
                    item = parents[row["paper_id"]]
                root_name = self.project_label(row)
                ckey = (row["project_id"], row["category"])
                if ckey not in collections:
                    parent = client.collection(root_name)
                    collections[ckey] = (parent, client.collection(row["category"], parent))
                for collection in collections[ckey]:
                    client.add_collection(item, collection)
                client.add_tags(item, ["source:openresearch", "RN: cited in " + row["project_name"][:100]])
                note_key = self.key(scope + "citation:" + row["citation_id"])
                marker = "RN citation " + row["citation_id"]
                existing = client.get(note_key)
                if existing:
                    if existing["data"].get("parentItem") != item["key"] or marker not in existing["data"].get("note", ""):
                        raise BridgeError("引用笔记编号冲突或已被人工改动，未覆盖。")
                    report["existing_notes"] += 1
                else:
                    note = client.template("note")
                    note.update(key=note_key, parentItem=item["key"], note=self.note(row, marker),
                                tags=[{"tag": "source:openresearch"}, {"tag": row["category"]}])
                    client.create(note); report["created_notes"] += 1
                if row.get("classifier"):
                    revision = "RN classification " + fingerprint([row["citation_id"], row["category"], row["classifier"]])
                    client.append_note_metadata(note_key, marker, revision, "当前分类：" + row["category"] + "（" + row["classifier"] + "） · " + row.get("category_reason", ""))
                    client.add_tags({"key": note_key}, [row["category"], "classified:" + row["classifier"]])
                delivered = True
                if options.get("download_pdf", False) and paper.arxiv:
                    try:
                        attachment, pdf = self.pdf(client, item, paper, cfg, scope)
                        if options.get("highlight_quotes", False):
                            result = self.highlights(client, attachment, pdf, row, scope)
                            report["created_annotations"] += result[0]; report["unlocated_quotes"] += result[1]
                    except BridgeError as e:
                        report["review"].append({"paper_id": row["paper_id"], "reason": str(e)})
                        delivered = str(e).startswith('论文已有 PDF 附件')
                report["papers"].append({"paper_id": row["paper_id"], "item_key": item["key"], "note_key": note_key,
                                          "category": row["category"], "citation_id": row["citation_id"]})
                if delivered:
                    report['completed_citations'].append(row['citation_id'])
            return report

    def metadata(self, paper):
        if paper.arxiv:
            return self.engine.arxiv.metadata([paper]).get(paper.arxiv)
        try:
            r = requests.get("https://api.crossref.org/works/" + quote(paper.doi, safe=""), timeout=20)
            r.raise_for_status(); data = r.json()["message"]
            if doi_id(data.get("DOI", "")) != paper.doi or not data.get("title"):
                return None
            return {"title": data["title"][0], "authors": [" ".join([a.get("given", ""), a.get("family", "")]).strip() for a in data.get("author", [])]}
        except (requests.RequestException, ValueError, KeyError):
            return None

    @staticmethod
    def note(row, marker):
        esc = html.escape
        return ("<h2>OpenResearch · 项目引用</h2><p>项目：" + esc(row["project_name"]) + " · 分类：" + esc(row["category"]) +
                "</p><p>以下为研究对话的引用上下文，不代表已核实的论文逐字引文。</p><blockquote>" +
                esc(row["context"]).replace("\n", "<br/>") + "</blockquote><p>来源类型：" + esc(row["source_kind"]) +
                '</p><p><a href="' + esc(row["source_chat_url"], quote=True) + '">' + esc(row["session_title"]) +
                "</a></p><p>对话 ID：" + esc(row["session_id"]) + "<br/>消息 ID：" + esc(row["message_id"]) +
                '<br/>时间：' + esc(str(row.get("created_at", ""))) + '</p><p><a href="' + esc(row["source_url"], quote=True) +
                '">论文原页面</a></p><p>' + marker + "</p>")

    def pdf(self, client, item, paper, cfg, scope):
        children = client.all("/items/" + item["key"] + "/children")
        attachments = [x for x in children if x["data"].get("itemType") == "attachment" and x["data"].get("contentType") == "application/pdf"]
        for a in attachments:
            path = a["data"].get("path", "")
            if path and Path(path).is_file() and a["data"].get("linkMode") == "linked_file":
                return a, Path(path)
        if attachments:
            raise BridgeError("论文已有 PDF 附件，未重复添加；此附件原文定位需要可用的本地链接文件。")
        if cfg.get("pdf_storage") != "linked_folder" or not Path(cfg.get("linked_pdf_dir", "")).is_dir():
            raise BridgeError("引用笔记已保存；PDF 需要可用的 Google Drive 同步目录。")
        pdf = self.engine.arxiv.pdf(paper, self.root / "data" / "pdfs")
        path = place_linked_pdf(pdf, Path(cfg["linked_pdf_dir"]))
        key = self.key(scope + "pdf:" + row_id(paper))
        attachment = client.link_file(key, item["key"], path)
        return attachment, path

    def highlights(self, client, attachment, path, row, scope):
        quotes = re.findall(r'[“"]([^“”"\n]{40,1000})[”"]', row["context"])
        if not quotes:
            return 0, 0
        try:
            import pypdfium2 as pdfium
        except ImportError:
            raise BridgeError("引用笔记已保存；逐字高亮需安装 pypdfium2 组件。") from None
        created, missing, verified = 0, 0, []
        # PDFium is process-global and not thread-safe. Rectangles are returned
        # in native PDF coordinates (origin at bottom-left), as Zotero expects.
        with PDFIUM_LOCK, pdfium.PdfDocument(path) as pdf:
            for text in dict.fromkeys(quotes):
                found = []
                for index in range(len(pdf)):
                    with closing(pdf[index]) as page, closing(page.get_textpage()) as textpage, closing(textpage.search(text, match_case=True)) as search:
                        while (hit := search.get_next()) is not None:
                            offset, count = hit
                            rects = [list(textpage.get_rect(i)) for i in range(textpage.count_rects(offset, count))]
                            if rects:
                                found.append((index, rects, pdf.get_page_label(index) or str(index + 1), offset,
                                              int(page.get_height() - max(r[3] for r in rects))))
                if len(found) != 1:
                    missing += 1
                else:
                    verified.append((text, found[0]))
        for text, (page_index, rects, label, offset, top) in verified:
            token = scope + "highlight:" + fingerprint([row["citation_id"], text, attachment["key"]])
            key = self.key(token)
            existing = client.get(key)
            if existing:
                if existing["data"].get("parentItem") != attachment["key"]:
                    raise BridgeError("高亮编号冲突，未覆盖。")
                continue
            data = client.template("annotation", annotationType="highlight")
            data.update(key=key, parentItem=attachment["key"], annotationType="highlight", annotationText=text,
                        annotationComment="OpenResearch · " + row["project_name"] + " · message " + row["message_id"],
                        annotationColor="#ffd400", annotationPageLabel=label,
                        annotationSortIndex=f"{page_index:05d}|{offset:06d}|{max(0, top):05d}",
                        annotationPosition=json.dumps({"pageIndex": page_index, "rects": rects}))
            client.create(data)
            created += 1
        return created, missing


def row_id(paper):
    return "arxiv:" + paper.arxiv if paper.arxiv else "doi:" + paper.doi
