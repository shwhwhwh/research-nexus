import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from bridge.clients import AlphaClient, ArxivClient, Http, ZoteroClient
from bridge.domain import BridgeError, Paper, arxiv_id, doi_id, find_match, parse_library, parse_arxiv_atom, parse_arxiv_html
from bridge.engine import Engine
from bridge.storage import Config, Store, protect
from bridge.files import place_linked_pdf

TEST_ROOT = (Path(__file__).resolve().parents[1] / "data" / "test-temp").resolve()
assert TEST_ROOT.is_relative_to(Path(__file__).resolve().parents[1])
TEST_ROOT.mkdir(parents=True, exist_ok=True)


def temp_directory():
    # Every automatically cleaned test directory is confined to this checkout.
    return tempfile.TemporaryDirectory(dir=TEST_ROOT)


PAPER = {"universal_paper_id": "2301.12345v2", "title": "A Paper"}
LIBRARY = {"structuredContent": {"folders": [{"folder_id": "f1", "name": "SNN", "paper_count": 1, "papers": [PAPER]}]}}


def item(key="ABCDEFGH", **fields):
    return {"key": key, "version": 1, "data": {"key": key, "itemType": "preprint", "title": "A Paper", "extra": "", "collections": [], **fields}}


class DomainTests(unittest.TestCase):
    def test_ids(self):
        for text in ["2301.12345v2", "https://arxiv.org/pdf/2301.12345v2.pdf", "https://www.alphaxiv.org/abs/2301.12345v2"]:
            self.assertEqual(arxiv_id(text), ("2301.12345", "v2"))
        self.assertEqual(arxiv_id("hep-th/9901001v3"), ("hep-th/9901001", "v3"))
        self.assertEqual(arxiv_id("private-paper-uuid"), ("", ""))
        self.assertEqual(doi_id("https://doi.org/10.1000/ABC"), "10.1000/abc")

    def test_library_dedup_and_versions(self):
        value = copy.deepcopy(LIBRARY)
        value["structuredContent"]["folders"].append({"id": "f2", "name": "Reading", "papers": [{"id": "2301.12345v1"}]})
        folders, papers, warnings = parse_library(value)
        self.assertEqual(len(folders), 2)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].version, "v2")
        self.assertEqual(papers[0].folders, ["f1", "f2"])
        self.assertFalse(warnings)

    def test_empty_library_is_not_unknown(self):
        self.assertEqual(parse_library({"content": [{"type": "text", "text": '{"folders": []}'}]}), ([], [], []))
        with self.assertRaises(BridgeError):
            parse_library({"content": [{"type": "text", "text": "Something unexpected, arxiv 2301.12345"}]})

    def test_xml_and_truncation(self):
        response = {"content": [{"type": "text", "text": '<library><folder folder_id="x" name="SNN" paper_count="3"><paper id="2301.12345"><title>A</title></paper></folder></library>'}]}
        folders, papers, warnings = parse_library(response)
        self.assertEqual(papers[0].arxiv, "2301.12345")
        self.assertTrue(folders[0]["partial"])
        self.assertEqual(len(warnings), 1)

    def test_exact_id_and_ambiguous_title(self):
        p = Paper("x", arxiv="2301.12345", title="A Paper")
        status, matches = find_match(p, [item(extra="arXiv: 2301.12345v1")])
        self.assertEqual(status, "existing")
        self.assertEqual(find_match(p, [item(title="A—Paper")])[0], "review")
        self.assertEqual(find_match(p, [item(extra="arXiv: 2301.12345"), item("QRSTUVWX", extra="arXiv: 2301.12345")])[0], "review")

    def test_distinct_preprints_same_published_doi_not_collapsed(self):
        p = Paper("x", arxiv="2301.12345", doi="10.1000/test", title="New")
        self.assertEqual(find_match(p, [item(DOI="10.1000/test", extra="arXiv: 2302.12345")])[0], "new")

    def test_arxiv_atom(self):
        text = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2301.12345v2</id><title>A\n Paper</title><summary>Abstract</summary><published>2023-01-01T00:00:00Z</published><author><name>Ray Researcher</name></author></entry></feed>'''
        data = parse_arxiv_atom(text)["2301.12345"]
        self.assertEqual(data["title"], "A Paper")
        self.assertEqual(data["version"], "v2")

    def test_arxiv_html_fallback_checks_exact_version(self):
        text='''<meta name="citation_title" content="A &amp; B"><meta name="citation_author" content="Smith, Jane"><meta name="description" content="Abstract page for arXiv paper 2301.12345v2: A"><meta name="citation_date" content="2023/01/01">'''
        data=parse_arxiv_html(text, "2301.12345v2")
        self.assertEqual(data["title"], "A & B")
        self.assertEqual(data["authors"], ["Jane Smith"])
        with self.assertRaises(BridgeError):
            parse_arxiv_html(text, "2301.12345v1")


class FakeAlpha:
    def __init__(self, key):
        pass
    def library(self):
        return (*parse_library(LIBRARY), LIBRARY)


class FakeArxiv:
    def metadata(self, papers):
        return {p.arxiv: {"title": "A Paper", "authors": ["Ray Researcher"], "abstract": "Abstract", "published": "2023-01-01", "version": p.version or "v2", "pdf_url": "https://arxiv.org/pdf/2301.12345v2"} for p in papers}
    def pdf(self, paper, root):
        root.mkdir(parents=True, exist_ok=True)
        file = root / "paper.pdf"
        file.write_bytes(b"%PDF-1.4\n" + b"test" * 50)
        return file


class FakeZotero:
    def __init__(self):
        self.items, self.creates, self.uploads = {}, [], []
        self.fail_upload = False
        self.lose_create = False
    def all(self, suffix):
        return [copy.deepcopy(v) for v in self.items.values() if v["data"].get("itemType") not in ("note", "attachment")]
    def collection(self, name):
        return "COLLECT1"
    def get(self, key):
        return copy.deepcopy(self.items.get(key))
    def template(self, kind, **kwargs):
        fields = {k: "" for k in ["title", "creators", "abstractNote", "date", "url", "repository", "archiveID", "extra", "tags", "collections"]}
        return {**fields, "itemType": kind, **kwargs}
    def create(self, data):
        self.assert_unique(data["key"])
        self.creates.append(data["key"])
        self.items[data["key"]] = {"key": data["key"], "version": 1, "data": copy.deepcopy(data)}
        if self.lose_create and data["itemType"] == "preprint":
            self.lose_create = False
            raise BridgeError("Network interrupted after create")
        return self.get(data["key"])
    def assert_unique(self, key):
        if key in self.items:
            raise AssertionError("duplicate create")
    def add_collection(self, data, collection):
        target = self.items[data["key"]]["data"]
        target["collections"] = list(dict.fromkeys(target.get("collections", []) + [collection]))
        return self.get(data["key"])
    def upload(self, key, path):
        if self.fail_upload:
            raise BridgeError("Quota exceeded")
        self.uploads.append(key)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_directory()
        self.z = FakeZotero()
        self.e = Engine(Path(self.tmp.name), alpha_factory=FakeAlpha, zotero_factory=lambda *_: self.z,
                        arxiv=FakeArxiv(), local_reader=lambda: [])
        self.e.config.values["zotero_user_id"] = "123"
        self.e.config._secrets = {"alphaxiv_key": "alpha-test-secret", "zotero_key": "zotero-test-secret"}
    def tearDown(self):
        self.tmp.cleanup()
    def job(self):
        return self.e.store.jobs(self.e.scope())[0]
    def test_archive_and_second_sync_create_no_duplicates(self):
        self.e.sync()
        self.assertEqual(self.job()["status"], "archived")
        self.assertEqual(len(self.z.creates), 3) # parent, provenance note, PDF attachment
        self.e.sync()
        self.assertEqual(len(self.z.creates), 3)
        self.assertEqual(len(self.z.uploads), 1)

    def test_synced_folder_archive_and_repeat_use_one_attachment(self):
        folder = Path(self.tmp.name) / "drive"
        folder.mkdir()
        self.e.config.values.update({"pdf_storage":"linked_folder", "linked_pdf_dir":str(folder)})
        def link(key, parent, path):
            return self.z.get(key) or self.z.create({"key":key, "itemType":"attachment", "parentItem":parent,
                                                   "linkMode":"linked_file", "path":str(path)})
        self.z.link_file = Mock(side_effect=link)
        self.e.sync(only_canonical="arxiv:2301.12345")
        first = self.job()
        self.assertEqual(first["status"], "linked_archived")
        self.assertEqual(Path(first["pdf_path"]).parent, folder)
        self.e.sync(only_canonical="arxiv:2301.12345", recheck=True)
        self.assertEqual(self.job()["attachment_key"], first["attachment_key"])
        self.assertEqual(len(self.z.creates), 3)
        self.assertFalse(self.z.uploads)
    def test_pdf_failure_recovers_with_same_keys(self):
        self.z.fail_upload = True
        self.e.sync()
        before = self.job()
        self.assertEqual(before["status"], "pdf_pending")
        self.z.fail_upload = False
        self.e.sync()
        after = self.job()
        self.assertEqual(after["status"], "archived")
        self.assertEqual(after["attachment_key"], before["attachment_key"])
        self.assertEqual(len(self.z.creates), 3)
        self.assertEqual(len(self.z.uploads), 1)

    def test_quota_to_linked_migration_recovers_unknown_create_outcome(self):
        self.z.fail_upload = True
        self.e.sync()
        original = self.job()
        folder = Path(self.tmp.name) / "drive"
        folder.mkdir()
        self.e.config.values.update({"pdf_storage":"linked_folder", "linked_pdf_dir":str(folder)})
        lose_reply = [True]
        def link(key, parent, path):
            result = self.z.get(key) or self.z.create({"key":key, "itemType":"attachment", "parentItem":parent,
                                                     "linkMode":"linked_file", "path":str(path)})
            if lose_reply[0]:
                lose_reply[0] = False
                raise BridgeError("Lost linked creation response")
            return result
        self.z.link_file = Mock(side_effect=link)
        self.z.trash_empty_attachment = Mock(side_effect=lambda key, parent: self.z.items[key]["data"].update(deleted=1))
        self.e.sync()
        pending_key = self.job()["attachment_key"]
        self.assertNotEqual(pending_key, original["attachment_key"])
        self.assertEqual(self.job()["status"], "pdf_pending")
        self.e.sync()
        self.assertEqual(self.job()["status"], "linked_archived")
        self.assertEqual(self.job()["item_key"], original["item_key"])
        self.assertEqual(self.job()["note_key"], original["note_key"])
        self.assertEqual(self.job()["attachment_key"], pending_key)
        self.assertEqual(len(self.z.creates), 4)
        self.assertEqual(self.z.items[original["attachment_key"]]["data"]["deleted"], 1)
        self.e.sync(only_canonical="arxiv:2301.12345", recheck=True)
        self.assertEqual(len(self.z.creates), 4)
        self.z.trash_empty_attachment.assert_called_once()
    def test_unknown_create_outcome_reconciles_before_retry(self):
        self.z.lose_create = True
        self.e.sync()
        self.assertEqual(self.job()["status"], "pdf_pending")
        self.e.sync()
        self.assertEqual(self.job()["status"], "archived")
        self.assertEqual(len(self.z.creates), 3)
    def test_existing_human_fields_preserved(self):
        self.z.items["EXISTING"] = item("EXISTING", title="Human title", extra="arXiv: 2301.12345", collections=["HUMANCOL"], tags=[{"tag": "human"}])
        self.e.sync()
        self.assertEqual(self.job()["status"], "existing")
        d = self.z.items["EXISTING"]["data"]
        self.assertEqual(d["title"], "Human title")
        self.assertEqual(d["tags"], [{"tag": "human"}])
        self.assertEqual(d["collections"], ["HUMANCOL", "COLLECT1"])
        self.assertFalse(self.z.creates)
    def test_title_collision_requires_decision(self):
        self.z.items["EXISTING"] = item("EXISTING")
        self.e.sync()
        self.assertEqual(self.job()["status"], "review")
        self.assertFalse(self.z.creates)
        self.e.resolve(self.job()["id"], "link", "EXISTING")
        self.e.sync()
        self.assertEqual(self.job()["status"], "existing")
        self.assertFalse(self.z.creates)
    def test_user_can_keep_distinct_same_title_paper(self):
        self.z.items["EXISTING"] = item("EXISTING")
        self.e.sync()
        self.e.resolve(self.job()["id"], "separate")
        self.e.sync()
        self.assertEqual(self.job()["status"], "archived")
        self.assertEqual(len(self.z.creates), 3)
    def test_unsynced_local_paper_blocks_duplicate_cloud_create(self):
        self.e.local_reader = lambda: [item("LOCALKEY", extra="arXiv: 2301.12345")]
        self.e.sync()
        self.assertEqual(self.job()["status"], "local_pending")
        self.assertFalse(self.z.creates)
        self.z.items["LOCALKEY"] = item("LOCALKEY", extra="arXiv: 2301.12345")
        self.e.sync()
        self.assertEqual(self.job()["status"], "existing")
    def test_missing_auth_writes_nothing(self):
        self.e.config._secrets = {}
        with self.assertRaises(BridgeError):
            self.e.sync()
        self.assertFalse(self.z.creates)
        self.assertFalse(self.e.store.jobs())
    def test_public_status_does_not_return_secrets(self):
        text = json.dumps(self.e.status())
        self.assertNotIn("alpha-test-secret", text)
        self.assertNotIn("zotero-test-secret", text)
        self.assertEqual(self.e.config.redact("alpha-test-secret"), "[redacted]")
    def test_target_library_change_keeps_separate_jobs(self):
        self.e.sync()
        self.e.config.values["zotero_user_id"] = "456"
        self.assertEqual(len(self.e.status()["jobs"]), 0)
    def test_original_version_pinned_after_parent_created(self):
        self.z.fail_upload = True
        self.e.sync()
        p = Paper("2301.12345v9", arxiv="2301.12345", version="v9")
        self.e.store.ingest(self.e.scope(), [p])
        self.assertEqual(self.job()["paper"]["version"], "v2")


    def test_single_paper_scope_does_not_archive_other_bookmarks(self):
        class TwoAlpha(FakeAlpha):
            def library(self):
                value = copy.deepcopy(LIBRARY)
                value["structuredContent"]["folders"][0]["papers"].append({"id": "2302.54321", "title": "Other paper"})
                return (*parse_library(value), value)
        self.e.alpha_factory = TwoAlpha
        self.e.sync(only_canonical="arxiv:2301.12345")
        self.assertEqual(len(self.e.store.jobs()), 1)
        self.assertEqual(self.job()["status"], "archived")
        self.e.sync(only_canonical="arxiv:2301.12345", recheck=True)
        self.assertEqual(len(self.z.creates), 3)

    def test_single_paper_not_bookmarked_does_not_write(self):
        with self.assertRaises(BridgeError):
            self.e.sync(only_canonical="arxiv:2302.54321")
        self.assertFalse(self.z.creates)
        self.assertFalse(self.e.store.jobs())


class ClientTests(unittest.TestCase):
    def test_existing_attachment_type_cannot_be_changed(self):
        z = ZoteroClient("123", "test")
        z.get = Mock(return_value=item("PDFKEY23", itemType="attachment", parentItem="PARENT23", linkMode="imported_file", md5=None))
        z.req = Mock()
        with self.assertRaises(BridgeError):
            z.link_file("PDFKEY23", "PARENT23", "D:\\Papers\\a.pdf")
        z.req.assert_not_called()

    def test_linking_cannot_replace_uploaded_pdf_or_another_parent(self):
        for overrides in ({"md5":"already-uploaded"}, {"parentItem":"OTHER234"}):
            z = ZoteroClient("123", "test")
            fields = {"itemType":"attachment", "parentItem":"PARENT23", "linkMode":"imported_file", **overrides}
            z.get = Mock(return_value=item("PDFKEY23", **fields))
            z.req = Mock()
            with self.assertRaises(BridgeError):
                z.link_file("PDFKEY23", "PARENT23", "D:\\Papers\\a.pdf")
            z.req.assert_not_called()

    def test_linked_pdf_recheck_writes_nothing(self):
        z = ZoteroClient("123", "test")
        z.get = Mock(return_value=item("PDFKEY23", itemType="attachment", parentItem="PARENT23", linkMode="linked_file", path="D:\\Papers\\a.pdf"))
        z.req = Mock()
        z.link_file("PDFKEY23", "PARENT23", "D:\\Papers\\a.pdf")
        z.req.assert_not_called()

    def test_client_keyed_creation_is_create_only(self):
        z = ZoteroClient("123", "test")
        z.req = Mock(return_value=Mock(json=lambda: {"successful": {"0": item()}}))
        z.get = Mock(return_value=item())
        source = {"key": "ABCDEFGH", "itemType": "preprint", "title": "A Paper"}
        self.assertEqual(z.create(source)["key"], "ABCDEFGH")
        self.assertEqual(z.req.call_args.kwargs["json"][0]["version"], 0)
        self.assertNotIn("version", source)

    def test_creation_conflict_does_not_treat_existing_key_as_success(self):
        z = ZoteroClient("123", "test")
        z.req = Mock(return_value=Mock(json=lambda: {"failed": {"0": {"code": 412, "message": "Object already exists"}}}))
        z.get = Mock()
        with self.assertRaises(BridgeError):
            z.create({"key": "ABCDEFGH", "itemType": "preprint"})
        z.get.assert_not_called()

    def test_non_ascii_api_key_reports_safe_actionable_error(self):
        with self.assertRaises(BridgeError):
            AlphaClient("密钥名称")
        with self.assertRaises(BridgeError):
            ZoteroClient("123", "wrong key with spaces")
    def test_mcp_sse_protocol_and_session(self):
        http = Mock()
        response = Mock()
        response.headers = {"Content-Type": "text/event-stream", "Mcp-Session-Id": "session"}
        response.text = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        response.content = response.text.encode('utf-8')
        http.request.return_value = response
        alpha = AlphaClient("secret", http)
        self.assertEqual(alpha._rpc("x"), {"ok": True})
        self.assertEqual(alpha.session_id, "session")

    def test_mcp_sse_uses_utf8_and_only_protocol_newlines(self):
        http = Mock()
        response = Mock()
        response.headers = {"Content-Type": "text/event-stream"}
        response.content = ('event: message\ndata: ' + json.dumps({"id": 1, "result": {"title": "中文…\u2028继续"}}, ensure_ascii=False) + '\n\n').encode('utf-8')
        http.request.return_value = response
        self.assertEqual(AlphaClient("secret", http)._rpc("tools/list")["title"], "中文…\u2028继续")
    def test_zotero_patch_preserves_arrays_and_retries_conflict(self):
        z = ZoteroClient("123", "test")
        z.get = Mock(side_effect=[item(collections=["ONE"]), item(collections=["ONE","TWO"]), item(collections=["ONE","TWO","THREE"])])
        z.req = Mock(side_effect=[Mock(status_code=412),Mock(status_code=204)])
        z.add_collection(item(), "THREE")
        self.assertEqual(z.req.call_args_list[-1].kwargs["json"], {"collections": ["ONE","TWO","THREE"]})
    def test_pdf_rejects_html_even_if_http_200(self):
        http = Mock()
        r = Mock()
        r.headers = {"Content-Type": "text/html"}
        http.request.return_value = r
        with temp_directory() as tmp, self.assertRaises(BridgeError):
            ArxivClient(http).pdf(Paper("x", arxiv="2301.12345", version="v2"), Path(tmp))
    def test_pdf_rejects_fake_pdf_content(self):
        http = Mock()
        r = Mock()
        r.headers = {"Content-Type": "application/pdf"}
        r.iter_content.return_value = [b"<html>wrong</html>"]
        http.request.return_value = r
        with temp_directory() as tmp:
            with self.assertRaises(BridgeError):
                ArxivClient(http).pdf(Paper("x", arxiv="2301.12345", version="v2"), Path(tmp))
            self.assertFalse(list(Path(tmp).glob("*.pdf")))
    @unittest.skipUnless(os.name == 'nt', 'Windows only')
    def test_dpapi_roundtrip_and_vault_has_no_plaintext(self):
        encrypted = protect("test-secret-123")
        self.assertEqual(protect(encrypted, decrypt=True), "test-secret-123")
        with temp_directory() as tmp:
            cfg = Config(Path(tmp))
            cfg.save({"alphaxiv_key": "test-secret-123"})
            self.assertNotIn("test-secret-123", cfg.vault.read_text())
            self.assertEqual(Config(Path(tmp)).secret("alphaxiv_key"), "test-secret-123")


class ExternalFolderTests(unittest.TestCase):
    def test_copy_verifies_bytes_and_retains_edits_on_repeat(self):
        with temp_directory() as tmp:
            folder = Path(tmp)
            source = folder / "source" / "a.pdf"
            source.parent.mkdir()
            source.write_bytes(b"%PDF-original")
            target_dir = folder / "drive"
            target_dir.mkdir()
            target = place_linked_pdf(source, target_dir)
            self.assertEqual(target.read_bytes(), source.read_bytes())
            target.write_bytes(b"%PDF-user-annotation")
            with self.assertRaises(BridgeError):
                place_linked_pdf(source, target_dir)
            self.assertEqual(place_linked_pdf(source, target_dir, previous_path=target).read_bytes(), b"%PDF-user-annotation")
            self.assertEqual(len(list(target_dir.iterdir())), 1)

    def test_bad_existing_file_and_missing_folder_are_not_overwritten(self):
        with temp_directory() as tmp:
            source = Path(tmp) / "a.pdf"
            source.write_bytes(b"%PDF-original")
            target_dir = Path(tmp) / "drive"
            with self.assertRaises(BridgeError):
                place_linked_pdf(source, target_dir)
            target_dir.mkdir()
            (target_dir / source.name).write_bytes(b"human text")
            with self.assertRaises(BridgeError):
                place_linked_pdf(source, target_dir)
            self.assertEqual((target_dir / source.name).read_bytes(), b"human text")


if __name__ == "__main__":
    unittest.main()
