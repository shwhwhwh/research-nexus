from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from dataclasses import asdict, dataclass, field
from urllib.parse import unquote, urlparse


ARXIV = re.compile(r"(?<![\w.])((?:\d{4}\.\d{4,5}|[a-z][a-z.\-]+/\d{7}))(v\d+)?(?![\w.])", re.I)


class BridgeError(Exception):
    pass


def arxiv_id(value: str) -> tuple[str, str]:
    value = unquote(str(value or "")).strip()
    value = re.sub(r"\.pdf(?:[?#].*)?$", "", value, flags=re.I)
    match = ARXIV.search(value)
    return (match.group(1).lower(), (match.group(2) or "").lower()) if match else ("", "")


def doi_id(value: str) -> str:
    value = unquote(str(value or "")).strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    return value.lower().rstrip(" .") if re.match(r"^10\.\d{4,9}/\S+$", value, re.I) else ""


def normalized_title(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value or "").casefold() if c.isalnum())


@dataclass
class Paper:
    source_id: str
    arxiv: str = ""
    version: str = ""
    doi: str = ""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    published: str = ""
    source_url: str = ""
    pdf_url: str = ""
    folders: list[str] = field(default_factory=list)
    folder_names: list[str] = field(default_factory=list)

    @property
    def canonical(self):
        return f"arxiv:{self.arxiv}" if self.arxiv else f"unsupported:{self.source_id}"

    def json(self):
        return asdict(self)


def paper_from_record(record, folder_id="", folder_name="") -> Paper:
    if isinstance(record, str):
        record = {"id": record}
    if not isinstance(record, dict):
        raise BridgeError("alphaXiv 返回了无法识别的论文记录；已停止本次导入。")
    source = str(record.get("universal_paper_id") or record.get("arxiv_id") or record.get("paper_id") or record.get("id") or record.get("url") or "")
    if not source:
        raise BridgeError("alphaXiv 论文缺少稳定 ID，不能安全归档。")
    aid, version = arxiv_id(record.get("arxiv_id") or source)
    if not aid:
        aid, version = arxiv_id(record.get("url", ""))
    authors = record.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    authors = [a.get("name", "") if isinstance(a, dict) else str(a) for a in authors]
    return Paper(source_id=source, arxiv=aid, version=version,
                 doi=doi_id(record.get("doi", "")), title=str(record.get("title") or ""),
                 authors=authors, source_url=f"https://www.alphaxiv.org/abs/{aid}" if aid else str(record.get("url") or ""),
                 folders=[folder_id] if folder_id else [], folder_names=[folder_name] if folder_name else [])


def _folder_records(value):
    """Accept structured MCP JSON; never regex-guess paper IDs from prose."""
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_folder_records(item))
        return out
    if not isinstance(value, dict):
        return []
    fid = value.get("folder_id") or value.get("folderId") or value.get("id")
    if fid and ("name" in value or "folder_name" in value) and any(k in value for k in ("papers", "paper_count", "paperCount", "type", "parent_id")):
        return [value] + _folder_records(value.get("children", []))
    out = []
    for key in ("folders", "library", "data", "result", "bookmarks", "collections"):
        if key in value:
            out.extend(_folder_records(value[key]))
    return out


def parse_library(result: dict) -> tuple[list[dict], list[Paper], list[str]]:
    candidates = []
    if isinstance(result.get("structuredContent"), (dict, list)):
        candidates.append(result["structuredContent"])
    candidates.append(result)
    xml_folders = []
    for block in result.get("content", []):
        if block.get("type") != "text":
            continue
        text = block.get("text", "").strip()
        text = re.sub(r"^```(?:json|xml)?\s*|\s*```$", "", text)
        try:
            candidates.append(json.loads(text))
        except (ValueError, TypeError):
            try:
                root = ET.fromstring(text)
                for f in root.iter("folder"):
                    d = dict(f.attrib)
                    for k in ("name", "folder_id", "paper_count", "type"):
                        if f.find(k) is not None:
                            d[k] = f.findtext(k)
                    d["papers"] = []
                    for p in f.iter("paper"):
                        rec = dict(p.attrib)
                        for child in p:
                            if child.text:
                                rec[child.tag] = child.text
                        d["papers"].append(rec)
                    xml_folders.append(d)
            except ET.ParseError:
                pass
    records = next((v for c in candidates if (v := _folder_records(c))), xml_folders)
    # A recognized explicit empty folders array is different from an unknown format.
    explicit_empty = any(isinstance(c, dict) and c.get("folders") == [] for c in candidates)
    if not records and not explicit_empty:
        raise BridgeError("alphaXiv 文献库返回格式未识别，未将它当作空库。需要根据真实返回调整适配器。")
    folders, papers, warnings = [], {}, []
    for f in records:
        fid = str(f.get("folder_id") or f.get("folderId") or f.get("id") or "")
        name = str(f.get("name") or f.get("folder_name") or fid)
        entries = f.get("papers", [])
        if not fid or not isinstance(entries, list):
            raise BridgeError("alphaXiv 文件夹缺少 ID 或论文列表。")
        try:
            count = int(f.get("paper_count", f.get("paperCount", len(entries))))
        except (ValueError, TypeError):
            count = len(entries)
        partial = count > len(entries) or bool(f.get("has_more") or f.get("truncated"))
        if partial:
            warnings.append(f"文件夹“{name}”返回 {len(entries)}/{count} 篇，官方接口有截断；此次只处理已返回条目，不能宣称全量同步。")
        folders.append({"id": fid, "name": name, "paper_count": count, "returned": len(entries), "partial": partial})
        for record in entries:
            paper = paper_from_record(record, fid, name)
            key = paper.canonical
            if key in papers:
                old = papers[key]
                old.folders = sorted(set(old.folders + paper.folders))
                old.folder_names = sorted(set(old.folder_names + paper.folder_names))
                # Keep the highest explicitly returned version, without inventing one.
                if int((paper.version or "v0")[1:]) > int((old.version or "v0")[1:]):
                    old.version = paper.version
            else:
                papers[key] = paper
    return folders, list(papers.values()), warnings


def parse_arxiv_atom(text: str) -> dict[str, dict]:
    atom = "{http://www.w3.org/2005/Atom}"
    ax = "{http://arxiv.org/schemas/atom}"
    root = ET.fromstring(text)
    result = {}
    for e in root.findall(atom + "entry"):
        aid, version = arxiv_id(e.findtext(atom + "id", ""))
        if not aid:
            continue
        result[aid] = {"title": " ".join(e.findtext(atom + "title", "").split()),
                       "authors": [a.findtext(atom + "name", "") for a in e.findall(atom + "author")],
                       "abstract": " ".join(e.findtext(atom + "summary", "").split()),
                       "published": e.findtext(atom + "published", "")[:10],
                       "version": version, "published_doi": doi_id(e.findtext(ax + "doi", "")),
                       "pdf_url": f"https://arxiv.org/pdf/{aid}{version}"}
    return result


def parse_arxiv_html(text: str, requested: str) -> dict:
    class CitationMeta(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.values = {}
        def handle_starttag(self, tag, attrs):
            if tag == "meta":
                a = dict(attrs)
                key = a.get("name") or a.get("property")
                if key and a.get("content"):
                    self.values.setdefault(key, []).append(a["content"])
    parser = CitationMeta()
    parser.feed(text)
    m = parser.values
    one = lambda key: m.get(key, [""])[0]
    aid, requested_version = arxiv_id(requested)
    returned_id, version = arxiv_id(one("description"))
    if not version:
        returned_id, version = arxiv_id(one("og:url"))
    if not version or aid != returned_id or requested_version and requested_version != version:
        raise BridgeError("arXiv 摘要页未能验证请求的论文版本，暂缓归档。")
    authors = []
    for name in m.get("citation_author", []):
        if "," in name:
            last, first = name.split(",", 1)
            name = f"{first.strip()} {last.strip()}"
        authors.append(name)
    if not one("citation_title") or not authors:
        raise BridgeError("arXiv 摘要页缺少可验证的标题或作者。")
    return {"title": one("citation_title"), "authors": authors, "abstract": one("citation_abstract"),
            "published": one("citation_date").replace("/", "-"), "version": version,
            "published_doi": doi_id(one("citation_doi")), "pdf_url": f"https://arxiv.org/pdf/{aid}{version}"}


def identifiers(item: dict):
    d = item.get("data", item)
    aids = set()
    for value in (d.get("url", ""), d.get("extra", ""), d.get("archiveID", "")):
        for m in ARXIV.finditer(str(value)):
            aids.add(m.group(1).lower())
    return aids, doi_id(d.get("DOI", ""))


def find_match(paper: Paper, items: list[dict]):
    exact, suspect = [], []
    for item in items:
        d = item.get("data", item)
        if d.get("itemType") in ("note", "attachment", "annotation") or d.get("deleted"):
            continue
        aids, doi = identifiers(item)
        if paper.arxiv and paper.arxiv in aids:
            exact.append(item)
        elif paper.doi and doi == paper.doi and not (paper.arxiv and aids and paper.arxiv not in aids):
            exact.append(item)
        elif paper.title and normalized_title(paper.title) == normalized_title(d.get("title", "")):
            suspect.append(item)
    if len(exact) == 1:
        return "existing", exact
    if len(exact) > 1 or suspect:
        return "review", exact or suspect
    return "new", []
