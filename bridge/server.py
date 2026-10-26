from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlparse

from .domain import BridgeError
from .engine import Engine
from .designer import Designer


def serve(root: Path, port=0):
    engine = Engine(root)
    designer = Designer(root, engine)
    csrf = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        server_version = "ResearchNexus/0.2"

        def log_message(self, *args):
            pass

        def valid_host(self):
            return self.headers.get("Host", "") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def send(self, status, content, content_type="application/json; charset=utf-8", **headers):
            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False).encode()
            elif isinstance(content, str):
                content = content.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in headers.items():
                self.send_header(k.replace("_", "-"), v)
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "Invalid host"})
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/api/status":
                    status = engine.status()
                    status["checks"] = engine.store.meta("checks")
                    return self.send(200, status)
                if path == "/api/designer":
                    return self.send(200, designer.public())
                if path == "/api/local-library":
                    return self.send(200, engine.local_library(parse_qs(parsed.query).get("q", [""])[0]))
                if path == "/api/openresearch":
                    return self.send(200, {"ready": engine.openresearch_online(), "url": engine.config.snapshot()["openresearch_url"]})
                if path.startswith("/api/pdf/"):
                    job = engine.store.job(int(path.rsplit("/", 1)[-1]))
                    file = Path(job.get("pdf_path") or "")
                    approved = [(root / "data" / "pdfs").resolve()]
                    cfg = engine.config.snapshot()
                    if cfg.get("pdf_storage") == "linked_folder" and cfg.get("linked_pdf_dir"):
                        approved.append(Path(cfg["linked_pdf_dir"]).resolve())
                    if not file.is_file() or not any(file.resolve().is_relative_to(folder) for folder in approved):
                        return self.send(404, {"error": "PDF 尚未下载"})
                    return self.send(200, file.read_bytes(), "application/pdf")
                if path == "/icon.png":
                    return self.send(200, (root / "web" / "icon.png").read_bytes(), "image/png")
                files = {"/": "index.html", "/app.js": "app.js", "/appearance.js": "appearance.js", "/style.css": "style.css", "/icon.svg": "icon.svg", "/designer.js": "designer.js", "/designer.css": "designer.css"}
                if path in files:
                    file = root / "web" / files[path]
                    content = file.read_text(encoding="utf-8")
                    types = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
                    if path == "/":
                        content = content.replace("__CSRF_TOKEN__", csrf)
                    return self.send(200, content, types[file.suffix] + "; charset=utf-8",
                                     Content_Security_Policy="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
                self.send(404, {"error": "Not found"})
            except BridgeError as exc:
                self.send(400, {"error": engine.config.redact(exc)})
            except (ValueError, TypeError):
                self.send(400, {"error": "请求格式错误"})
            except Exception:
                self.send(500, {"error": "本地操作失败，请查看状态并重试。"})

        def do_POST(self):
            expected_origin = f"http://{self.headers.get('Host')}"
            if not self.valid_host() or self.headers.get("Origin") != expected_origin or not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf):
                return self.send(403, {"error": "Invalid local request"})
            try:
                size = int(self.headers.get("Content-Length", 0))
                if size < 0 or size > (524288 if self.path.startswith('/api/designer') else 65536) or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self.send(400, {"error": "Invalid body"})
                payload = json.loads(self.rfile.read(size) or b"{}")
                path = urlparse(self.path).path
                if path.startswith("/api/designer/"):
                    action = path.rsplit("/", 1)[-1]
                    if action == "save":
                        return self.send(200, designer.save_graph(payload))
                    if action == "build":
                        return self.send(202, {"run_id": designer.build(payload["edge_id"], payload.get("provider", "codex"), bool(payload.get("repair")), payload.get('feedback', ''))})
                    if action == "test":
                        return self.send(202, {"run_id": designer.run(payload["edge_id"], payload.get("version"), dry_run=True)})
                    if action == "activate":
                        return self.send(200, designer.activate(payload["edge_id"], payload["version"]))
                    if action == "disable":
                        return self.send(200, designer.disable(payload["edge_id"]))
                    if action == "run":
                        return self.send(202, {"run_id": designer.run(payload["edge_id"], dry_run=False)})
                    if action == "run-graph":
                        return self.send(202, {"run_id": designer.run_graph()})
                    if action == "cancel":
                        return self.send(200, designer.cancel(payload["run_id"]))
                    return self.send(404, {"error": "未知的设计器操作。"})
                if path == "/api/config":
                    engine.save(payload)
                    return self.send(200, {"ok": True})
                if path in ("/api/sync", "/api/preview", "/api/connections"):
                    engine.launch(path.rsplit("/", 1)[-1])
                    return self.send(202, {"ok": True})
                if path == "/api/resolve":
                    engine.resolve(int(payload["job_id"]), payload["action"], payload.get("item_key"))
                    return self.send(200, {"ok": True})
                if path == "/api/start-openresearch":
                    return self.send(200, engine.start_openresearch())
                if path == "/api/shutdown":
                    self.send(200, {"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                self.send(404, {"error": "Not found"})
            except BridgeError as exc:
                self.send(400, {"error": engine.config.redact(exc)})
            except (ValueError, KeyError, TypeError):
                self.send(400, {"error": "请求格式不正确"})
            except Exception:
                self.send(500, {"error": "操作失败，请检查配置后重试。"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}"
    ConfigInfo = {"url": url, "pid": __import__("os").getpid()}
    engine.config._atomic(root / "data" / "runtime.json", ConfigInfo)
    print(json.dumps({"ready": True, "url": url}), flush=True)
    threading.Thread(target=engine.scheduler, daemon=True).start()
    def designer_scheduler():
        while not designer.stop_event.wait(5):
            designer.tick()
    threading.Thread(target=designer_scheduler, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.3)
    finally:
        designer.shutdown()
        engine.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    serve(args.root, args.port)
