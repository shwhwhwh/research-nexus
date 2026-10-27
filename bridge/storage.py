from __future__ import annotations

import base64
import copy
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
from datetime import datetime, timezone

from .domain import BridgeError


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


DEFAULTS = {
    "alpha_folder_ids": [], "zotero_user_id": "", "zotero_collection": "alphaXiv Inbox",
    "sync_interval_seconds": 600, "auto_sync": False, "download_pdf": True,
    "upload_pdf": True, "openresearch_url": "http://127.0.0.1:4792",
    "zotero_exe": r"C:\Program Files\Zotero\zotero.exe",
    "openresearch_exe": "", "max_papers_per_sync": 25,
    "pdf_storage": "zotero", "linked_pdf_dir": "",
}


def protect(value: str, decrypt=False):
    if os.name != "nt":
        raise BridgeError("凭据持久化当前仅支持 Windows DPAPI；其他系统请使用环境变量。")
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value) if decrypt else value.encode("utf-8")
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    src, dst = Blob(len(raw), buf), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(src), "Research Bridge", None, None, None, 1, ctypes.byref(dst))
    if not ok:
        raise BridgeError("Windows 无法解密或保存凭据；请在当前 Windows 用户下重新输入。")
    try:
        out = ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel.LocalFree(dst.pbData)
    return out.decode("utf-8") if decrypt else base64.b64encode(out).decode("ascii")


class Config:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "config.json"
        self.vault = root / "credentials.dpapi.json"
        self.lock = threading.RLock()
        self.values = copy.deepcopy(DEFAULTS)
        if self.path.exists():
            self.values.update(json.loads(self.path.read_text(encoding="utf-8")))
        if not self.values["openresearch_exe"]:
            exe = root.parent / "vendor" / "openresearch" / "orx.exe"
            if not exe.exists():
                exe = next((root.parent / "vendor" / "openresearch").glob("**/orx.exe"), exe)
            if exe.exists():
                self.values["openresearch_exe"] = str(exe)
        self._secrets = {}
        if self.vault.exists():
            for key, value in json.loads(self.vault.read_text(encoding="utf-8")).items():
                try:
                    self._secrets[key] = protect(value, decrypt=True)
                except BridgeError:
                    pass
        for name, env in (("alphaxiv_key", "ALPHAXIV_API_KEY"), ("zotero_key", "ZOTERO_API_KEY")):
            if os.environ.get(env):
                self._secrets[name] = os.environ[env]
        if os.environ.get("ZOTERO_USER_ID"):
            self.values["zotero_user_id"] = os.environ["ZOTERO_USER_ID"]

    def secret(self, key):
        with self.lock:
            return self._secrets.get(key, "")

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.values)

    def public(self):
        return {**self.snapshot(), "alphaxiv_key_configured": bool(self.secret("alphaxiv_key")),
                "zotero_key_configured": bool(self.secret("zotero_key"))}

    def redact(self, value):
        text = str(value)
        for s in self._secrets.values():
            if s:
                text = text.replace(s, "[redacted]")
        return text[:1500]

    def save(self, payload):
        with self.lock:
            values = self.snapshot()
            for k in DEFAULTS:
                if k in payload:
                    values[k] = payload[k]
            if not str(values["zotero_user_id"]).isdigit() and values["zotero_user_id"]:
                raise BridgeError("Zotero User ID 必须是数字。")
            values["zotero_user_id"] = str(values["zotero_user_id"])
            for k in ("auto_sync", "download_pdf", "upload_pdf"):
                if not isinstance(values[k], bool):
                    raise BridgeError("无效的开关设置。")
            if values["pdf_storage"] not in ("zotero", "linked_folder"):
                raise BridgeError("请选择有效的 PDF 保存方式。")
            values["linked_pdf_dir"] = str(values["linked_pdf_dir"]).strip()
            if values["pdf_storage"] == "linked_folder":
                folder = Path(values["linked_pdf_dir"])
                if not folder.is_absolute() or not folder.is_dir():
                    raise BridgeError("请选择已存在的 Google Drive 或其他同步文件夹。")
            values["sync_interval_seconds"] = max(60, min(86400, int(values["sync_interval_seconds"])))
            values["max_papers_per_sync"] = max(1, min(200, int(values["max_papers_per_sync"])))
            if not isinstance(values["alpha_folder_ids"], list) or any(not isinstance(x, str) for x in values["alpha_folder_ids"]):
                raise BridgeError("文件夹设置格式不正确。")
            if not str(values["zotero_collection"]).strip():
                raise BridgeError("请填写目标分类名称。")
            import urllib.parse
            url = urllib.parse.urlparse(values["openresearch_url"])
            if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost") or url.username or url.password:
                raise BridgeError("OpenResearch 地址必须是本机 http://127.0.0.1 或 localhost 地址。")
            secrets_copy = dict(self._secrets)
            for name in ("alphaxiv_key", "zotero_key"):
                if payload.get(name):
                    candidate = str(payload[name]).strip()
                    if not candidate.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in candidate):
                        raise BridgeError("API Key 包含空白或非 ASCII 字符；请复制实际密钥值，不要填写名称或说明。")
                    secrets_copy[name] = candidate
            if secrets_copy != self._secrets:
                encrypted = {k: protect(v) for k, v in secrets_copy.items()}
                self._atomic(self.vault, encrypted)
                self._secrets = secrets_copy
            self._atomic(self.path, values)
            self.values = values

    @staticmethod
    def _atomic(path, obj):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "bridge.sqlite"
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
              id INTEGER PRIMARY KEY, scope TEXT NOT NULL, canonical TEXT NOT NULL,
              paper TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
              item_key TEXT, attachment_key TEXT, note_key TEXT, pdf_path TEXT,
              pdf_sha256 TEXT, error TEXT NOT NULL DEFAULT '', candidates TEXT NOT NULL DEFAULT '[]',
              allow_title_duplicate INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL,
              UNIQUE(scope, canonical));
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, time TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def meta(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))
                return value
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def ingest(self, scope, papers):
        with self.connect() as db:
            for paper in papers:
                old = db.execute("SELECT paper,item_key FROM jobs WHERE scope=? AND canonical=?", (scope, paper.canonical)).fetchone()
                if old:
                    prev = json.loads(old[0])
                    paper.folders = sorted(set(prev.get("folders", []) + paper.folders))
                    paper.folder_names = sorted(set(prev.get("folder_names", []) + paper.folder_names))
                    for k in ("title", "authors", "abstract", "published", "pdf_url", "doi"):
                        if not getattr(paper, k):
                            setattr(paper, k, prev.get(k, getattr(paper, k)))
                    if old["item_key"] and prev.get("version"):
                        paper.version = prev["version"]
                db.execute("""INSERT INTO jobs(scope,canonical,paper,created,updated) VALUES(?,?,?,?,?)
                ON CONFLICT(scope,canonical) DO UPDATE SET paper=excluded.paper""",
                           (scope, paper.canonical, json.dumps(paper.json(), ensure_ascii=False), now(), now()))

    def jobs(self, scope=None, limit=500):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs" + (" WHERE scope=?" if scope else "") + " ORDER BY id DESC LIMIT ?",
                              (scope, limit) if scope else (limit,)).fetchall()
            return [self._job(r) for r in rows]

    def job(self, job_id):
        with self.connect() as db:
            r = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not r:
                raise BridgeError("未找到该归档任务。")
            return self._job(r)

    @staticmethod
    def _job(row):
        d = dict(row)
        d["paper"] = json.loads(d["paper"])
        d["candidates"] = json.loads(d["candidates"])
        return d

    def update(self, job_id, **fields):
        allowed = {"paper", "status", "item_key", "attachment_key", "note_key", "pdf_path", "pdf_sha256", "error", "candidates", "allow_title_duplicate"}
        if not fields.keys() <= allowed:
            raise ValueError("Unknown job field")
        for key in ("paper", "candidates"):
            if key in fields:
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        fields["updated"] = now()
        with self.connect() as db:
            db.execute("UPDATE jobs SET " + ",".join(f"{k}=?" for k in fields) + " WHERE id=?", [*fields.values(), job_id])

    def key(self, job_id, field):
        row = self.job(job_id)
        if row[field]:
            return row[field]
        key = self.new_key()
        self.update(job_id, **{field: key})
        return key

    @staticmethod
    def new_key():
        return "".join(secrets.choice("23456789ABCDEFGHIJKLMNPQRSTUVWXYZ") for _ in range(8))

    def event(self, level, message):
        with self.connect() as db:
            db.execute("INSERT INTO events(time,level,message) VALUES(?,?,?)", (now(), level, message))
            db.execute("DELETE FROM events WHERE id < (SELECT COALESCE(MAX(id),0)-1000 FROM events)")

    def events(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")]
