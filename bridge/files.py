"""PDF-only external-folder storage; never move Zotero databases or overwrite edits."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .domain import BridgeError


def place_linked_pdf(source: Path, folder: Path, previous_path=None) -> Path:
    folder = folder.resolve()
    if not folder.is_dir():
        raise BridgeError("PDF 同步文件夹不可用；请启动 Google Drive 并确认文件夹已挂载。")
    target = folder / source.name
    if target.exists():
        if not target.is_file() or target.is_symlink() or target.read_bytes()[:5] != b"%PDF-":
            raise BridgeError("同步文件夹中存在同名的异常文件，未覆盖。")
        known_file = bool(previous_path) and Path(previous_path).resolve() == target
        if not known_file and hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise BridgeError("同步文件夹中已有内容不同的同名 PDF；未覆盖或自动关联，请先核对。")
        # A reader may have edited a PDF already tracked by this job.
        return target
    descriptor, temporary = tempfile.mkstemp(prefix=".research-bridge-", suffix=".part", dir=folder)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream, source.open("rb") as incoming:
            shutil.copyfileobj(incoming, stream)
        if hashlib.sha256(temporary.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise BridgeError("同步文件夹中的 PDF 校验失败，未关联到 Zotero。")
        # On Windows rename fails if another writer created the target meanwhile.
        temporary.rename(target)
    except FileExistsError:
        return place_linked_pdf(source, folder, previous_path)
    finally:
        temporary.unlink(missing_ok=True)
    return target
