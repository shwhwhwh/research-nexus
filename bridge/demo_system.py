"""Offline integration fixtures for the public template demo, never real accounts."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import requests

from . import engine as engine_module
from .domain import parse_library
from .engine import Engine
from .server import serve
from .storage import Config

SAMPLE = {"folders": [{"folder_id": "demo", "name": "Demo collection", "paper_count": 2, "papers": [
    {"id": "0000.00001v1", "title": "Fictional demo: Tiny robots"},
    {"id": "0000.00002v1", "title": "Fictional demo: Learning agents"}]}]}


class SampleAlpha:
    def __init__(self, _key): pass
    def library(self):
        return (*parse_library(SAMPLE), SAMPLE)


class SampleArxiv:
    def metadata(self, papers):
        return {p.arxiv: {"title": p.title, "authors": ["Demo Author"], "abstract": "Fictional sample data only.", "published": "2000-01-01", "version": "v1", "pdf_url": "https://example.invalid/demo.pdf"} for p in papers}
    def pdf(self, paper, root):
        root.mkdir(parents=True, exist_ok=True)
        file = root / (paper.arxiv + ".pdf")
        content = b"BT /F1 18 Tf 50 750 Td (Fictional Research Nexus demo PDF) Tj ET"
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"]
        data = b"%PDF-1.4\n"; offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(data)); data += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
        start = len(data); data += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
        data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode(); file.write_bytes(data)
        return file


class SampleZotero:
    def __init__(self, path): self.path, self.items, self.creates = path, {}, []
    def req(self, *_args, **_kwargs): return SimpleNamespace(status_code=200)
    def top_items(self): return [copy.deepcopy(v) for v in self.items.values() if v["data"]["itemType"] == "preprint"]
    def all(self, _path): return self.top_items()
    def collection(self, _name): return "DEMOCL01"
    def get(self, key): return copy.deepcopy(self.items.get(key))
    def template(self, kind, **kwargs): return {"itemType": kind, **{k: "" for k in ("title", "creators", "abstractNote", "date", "url", "repository", "archiveID", "extra", "tags", "collections")}, **kwargs}
    def create(self, data):
        if data["key"] in self.items: raise AssertionError("Duplicate demo write")
        self.creates.append(data["key"]); self.items[data["key"]] = {"key": data["key"], "version": 1, "data": copy.deepcopy(data)}; self.save(); return self.get(data["key"])
    def add_collection(self, item, collection):
        self.items[item["key"]]["data"]["collections"] = [collection]; self.save(); return self.get(item["key"])
    def link_file(self, key, parent, path): return self.get(key) or self.create({"key": key, "parentItem": parent, "itemType": "attachment", "linkMode": "linked_file", "path": str(path)})
    def save(self): Config._atomic(self.path, {"items": list(self.items.values()), "create_count": len(self.creates)})


def fixture_engine(root):
    root = Path(root).resolve()
    allowed = (Path(__file__).resolve().parents[1] / "artifacts").resolve()
    if not root.is_relative_to(allowed) or not root.name.startswith("system-demo-"):
        raise RuntimeError("Demo fixtures require an isolated artifacts/system-demo-* directory")
    for key in list(os.environ):
        if "ALPHAXIV" in key or "ZOTERO" in key: os.environ.pop(key, None)
    def no_network(*_args, **_kwargs):
        raise RuntimeError("External network disabled in system demo")
    requests.sessions.Session.request = no_network
    folder = root / "demo-drive" / "Research PDFs"; folder.mkdir(parents=True, exist_ok=True)
    programs = root / "demo-programs"; programs.mkdir(exist_ok=True)
    for file in ("zotero.exe", "OpenResearch.exe"):
        (programs / file).write_bytes(b"DEMO PLACEHOLDER. NEVER EXECUTE.")
    engine_module.local_zotero = lambda: {"online": True, "demo": True}
    zotero = SampleZotero(root / "data" / "demo-zotero.json")
    engine = Engine(root, alpha_factory=SampleAlpha, zotero_factory=lambda *_: zotero, arxiv=SampleArxiv(), local_reader=lambda: [])
    # No real keys or app paths are read. A wizard completion stores dummy demo values.
    engine.local_library = lambda _query="": [{"key": i["key"], "title": i["data"].get("title", ""), "authors": "Demo Author", "date": "2000", "url": "", "type": "preprint"} for i in zotero.top_items()]
    return engine


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, required=True)
    serve(parser.parse_args().root, engine_factory=fixture_engine)
