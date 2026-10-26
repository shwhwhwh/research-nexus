"""Install a reviewed system preset without importing accounts or executable code."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import threading

from .domain import BridgeError
from .storage import Config, now


class Systems:
    def __init__(self, root, engine):
        self.engine = engine
        self.path = Path(root) / "data" / "systems" / "installed.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        source = Path(__file__).resolve().parents[1] / "system-templates" / "literature-workspace.rn-system.json"
        self.manifest = json.loads(source.read_text(encoding="utf-8"))
        self.state = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def _save(self):
        Config._atomic(self.path, self.state)

    @staticmethod
    def _digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _program(value):
        path = Path(str(value))
        return path.is_absolute() and path.suffix.lower() == ".exe" and path.is_file()

    def public(self):
        with self.lock:
            cfg = self.engine.config.public()
            checks = self.engine.store.meta("checks") or {}
            ack = self.state.get("acknowledgements", {})
            requirements = [
                {"id": "accounts", "label": "alphaXiv / Zotero API Key 与 Zotero User ID", "ok": not self.engine.missing()},
                {"id": "apps", "label": "已安装 Zotero 与 OpenResearch，本机路径有效", "ok": all(self._program(cfg.get(k, "")) for k in ("zotero_exe", "openresearch_exe"))},
                {"id": "drive", "label": "Google Drive 已登录并选定 PDF 同步文件夹（用户确认）", "ok": bool(ack.get("drive_signed_in")) and cfg["pdf_storage"] == "linked_folder" and Path(cfg["linked_pdf_dir"]).is_absolute() and Path(cfg["linked_pdf_dir"]).is_dir()},
                {"id": "zotero_sync", "label": "Zotero 已登录同一账号并开启自动同步（用户确认）", "ok": bool(ack.get("zotero_sync_enabled"))},
                {"id": "orx_agent", "label": "已在 OpenResearch 完成 Agent 登录（用户确认）", "ok": bool(ack.get("orx_agent_ready"))},
                {"id": "api_check", "label": "已检查 alphaXiv 收藏读取与 Zotero 个人库读取", "ok": bool(checks.get("alpha", {}).get("ok") and checks.get("zotero_web", {}).get("ok"))}
            ]
            installed = self.state.get("id") == self.manifest["id"]
            return {"catalog": [copy.deepcopy(self.manifest)], "installed": installed, "system": copy.deepcopy(self.state),
                    "requirements": requirements, "ready": installed and all(r["ok"] for r in requirements),
                    "enabled": installed and cfg["auto_sync"], "diy_status": "unfinished"}

    def install(self, manifest):
        # Templates cannot choose keys, local paths, schedules, commands, or API origins.
        if not isinstance(manifest, dict) or self._digest(manifest) != self._digest(self.manifest):
            raise BridgeError("该模板不是当前 RN 支持的文献科研系统版本，或内容已被修改。请下载官方模板。")
        with self.lock:
            if self.state.get("id") != manifest["id"]:
                self.state = {"id": manifest["id"], "version": manifest["version"], "installed_at": now(), "acknowledgements": {}}
                self._save()
            return self.public()

    def configure(self, payload):
        with self.lock:
            if not self.public()["installed"]:
                raise BridgeError("请先安装 System Template。")
            permitted = {"alphaxiv_key", "zotero_key", "zotero_user_id", "zotero_exe", "openresearch_exe", "linked_pdf_dir", "zotero_collection", "acknowledgements"}
            if not isinstance(payload, dict) or set(payload) - permitted:
                raise BridgeError("模板配置包含不支持的字段。")
            ack = payload.get("acknowledgements", {})
            if not isinstance(ack, dict) or set(ack) - {"drive_signed_in", "zotero_sync_enabled", "orx_agent_ready"} or any(type(v) is not bool for v in ack.values()):
                raise BridgeError("请确认软件登录与同步步骤。")
            cfg = self.engine.config.snapshot()
            values = {k: v for k, v in payload.items() if k != "acknowledgements"}
            for key in ("zotero_exe", "openresearch_exe"):
                if key in values:
                    values[key] = str(values[key]).strip()
                    if values[key] and not self._program(values[key]):
                        raise BridgeError("请选择已安装的 Zotero / OpenResearch .exe 文件。")
            # Allow saving account setup before the folder is selected.
            if str(values.get("linked_pdf_dir", cfg["linked_pdf_dir"])).strip():
                values.update(pdf_storage="linked_folder", upload_pdf=False, download_pdf=True)
            values.update(sync_interval_seconds=86400, auto_sync=False)
            if "zotero_collection" not in values:
                values["zotero_collection"] = (cfg.get("zotero_collection") if self.engine.config.path.exists() else None) or self.manifest["defaults"]["zotero_collection"]
            self.engine.save(values)
            self.engine.store.meta("checks", {})
            self.state.setdefault("acknowledgements", {}).update(ack)
            self._save()
            return self.public()

    def enable(self):
        with self.lock:
            status = self.public()
            if not status["ready"]:
                missing = [r["label"] for r in status["requirements"] if not r["ok"]]
                raise BridgeError("完成配置后再运行系统：" + "；".join(missing))
            self.engine.save({"auto_sync": True, "sync_interval_seconds": 86400})
            self.state["enabled_at"] = now()
            self._save()
            return self.public()
