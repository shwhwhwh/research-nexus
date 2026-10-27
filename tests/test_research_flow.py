import copy
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from bridge.domain import BridgeError, Paper
from bridge.research_flow import ResearchFlow, extract_citations, active_messages, validate_options, DEFAULT_CATEGORIES
from bridge.designer import Designer


PROJECT = {"id": "project-one", "name": "Example Research"}
SESSION = {"id": "session-one", "title": "Review", "busy": False}
SCOPE = {"project_ids": [PROJECT["id"]], "max_papers": 2, "categories": DEFAULT_CATEGORIES}


def message(mid, text, parent=None, role="assistant", completed=1):
    return {"id": mid, "role": role, "parts": [{"id": "part-" + mid, "type": "text", "text": text}],
            "parentId": parent, "createdAt": 1, "completedAt": completed}


def records():
    text = "Optimizer training reference: https://arxiv.org/abs/1706.03762"
    return extract_citations(PROJECT, SESSION, {"messages": [message("m1", text)]}, SCOPE, "http://127.0.0.1:4792")


class MemoryZotero:
    def __init__(self):
        self.items, self.collections, self.creates = {}, {}, 0
        self.lose_note_response = False

    def all(self, path):
        if path == "/items/top":
            return [copy.deepcopy(i) for i in self.items.values() if not i["data"].get("parentItem")]
        return []

    def collection(self, name, parent=None):
        token = (name, parent)
        if token not in self.collections:
            self.collections[token] = "C" + str(len(self.collections))
        return self.collections[token]

    def get(self, key):
        return copy.deepcopy(self.items.get(key))

    def template(self, item_type, **kwargs):
        if item_type == "preprint":
            return dict.fromkeys(["title", "creators", "url", "extra", "date", "abstractNote"], "") | {"itemType": "preprint"}
        return {"itemType": item_type}

    def create(self, data):
        if data["key"] in self.items:
            raise BridgeError("create-only key collision")
        self.creates += 1
        self.items[data["key"]] = {"key": data["key"], "version": 1, "data": copy.deepcopy(data)}
        if data["itemType"] == "note" and self.lose_note_response:
            self.lose_note_response = False
            raise BridgeError("network response lost after remote commit")
        return self.get(data["key"])

    def add_collection(self, item, collection):
        values = self.items[item["key"]]["data"].setdefault("collections", [])
        if collection not in values:
            values.append(collection)

    def add_tags(self, item, tags):
        values = self.items[item["key"]]["data"].setdefault("tags", [])
        for tag in tags:
            if {"tag": tag} not in values:
                values.append({"tag": tag})

    def append_note_metadata(self, key, marker, revision, text):
        body = self.items[key]['data']['note']
        if marker not in body:
            raise BridgeError('Source marker missing')
        if revision not in body:
            self.items[key]['data']['note'] += '<p>' + revision + ' ' + text + '</p>'


class MemoryAlpha:
    def __init__(self):
        self.folders = []

    def call(self, name, args):
        if name == "create_folder":
            fid = "folder-" + str(len(self.folders))
            self.folders.append({"folder_id": fid, "name": args["name"], "parent_id": args.get("parent_folder_id"), "papers": []})
            return {"structuredContent": {"folder_id": fid}}
        if name == "save_papers_to_folder":
            f = next(f for f in self.folders if f["folder_id"] == args["folder_id"])
            for aid in args["paper_ids_or_urls"]:
                paper = {"id": aid, "title": "Fixture paper"}
                if paper not in f["papers"]:
                    f["papers"].append(paper)
            return {"structuredContent": {"ok": True}}
        return {"structuredContent": {"folders": copy.deepcopy(self.folders)}}


class ResearchFlowTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / "data" / "research-test-temp"
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.zotero, self.alpha = MemoryZotero(), MemoryAlpha()
        self.config = {"openresearch_url": "http://127.0.0.1:4792", "zotero_user_id": "123"}
        self.engine = SimpleNamespace(config=SimpleNamespace(snapshot=lambda: copy.deepcopy(self.config), secret=lambda k: "fixture-key"),
            alpha_factory=lambda k: self.alpha, zotero_factory=lambda u, k: self.zotero,
            local_reader=lambda: [], paper_write_lock=threading.RLock())
        self.flow = ResearchFlow(self.root, self.engine)
        self.flow.metadata = lambda p: {"title": "Authority-verified fixture paper", "authors": ["Example Author"]}

    def test_selected_branch_ignores_abandoned_text_reasoning_and_tool_inputs(self):
        root = message("root", "Question", role="user")
        wrong = message("abandoned", "https://arxiv.org/abs/2203.15556", "root")
        right = message("selected", "https://arxiv.org/pdf/1706.03762v2.pdf", "root")
        right["parts"] += [{"type": "reasoning", "text": "https://arxiv.org/abs/2305.11206"},
                            {"type": "tool", "tool": "bash", "state": {"status": "completed", "input": "https://arxiv.org/abs/2305.07759"}}]
        rows = extract_citations(PROJECT, SESSION, {"messages": [root, wrong, right], "activeLeafId": "selected"}, SCOPE, "http://127.0.0.1:4792")
        self.assertEqual([r["arxiv"] for r in rows], ["1706.03762"])
        self.assertEqual(rows[0]["version"], "v2")

    def test_explicit_ids_only_exact_context_and_legacy_completion(self):
        text = "Before paragraph\n\nTraining https://arxiv.org/abs/1706.03762 and 2401.999999999\n\nAfter paragraph"
        rows = extract_citations(PROJECT, SESSION, {"messages": [message("m", text, completed=None)]}, SCOPE, "http://127.0.0.1:4792")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["context"], text.split("\n\n")[1])
        self.assertEqual(rows[0]["completion_state"], "legacy_or_unknown")
        self.assertEqual(rows[0]["category"], "训练与优化")

    def test_busy_incomplete_messages_and_missing_branch_are_not_exported(self):
        m = message("m", "https://arxiv.org/abs/1706.03762", completed=None)
        rows = extract_citations(PROJECT, SESSION | {"busy": True}, {"messages": [m]}, SCOPE, "http://127.0.0.1:4792")
        self.assertEqual(rows, [])
        with self.assertRaises(BridgeError):
            active_messages({"messages": [message("m", "x", "root")], "activeLeafId": "missing"})

    def test_doi_stops_at_cjk_punctuation_and_adjacent_markdown(self):
        text = ('[First](https://doi.org/10.1000/example)、[Next](https://doi.org/10.1000/second)，'
                '[Third](https://doi.org/10.1000/third)。正文 doi:10.1000/fourth；后文')
        rows = extract_citations(PROJECT, SESSION, {"messages": [message("m", text)]}, SCOPE, "http://127.0.0.1:4792")
        self.assertEqual([row['doi'] for row in rows], ['10.1000/example', '10.1000/second', '10.1000/third', '10.1000/fourth'])
        self.assertTrue(all(row['context'] == text for row in rows))
        plain = 'doi:10.1000/example[another link]'
        rows = extract_citations(PROJECT, SESSION, {"messages": [message("m", plain)]}, SCOPE, "http://127.0.0.1:4792")
        self.assertEqual([row['doi'] for row in rows], ['10.1000/example'])

    def test_doi_parentheses_and_completed_tool_discovery_are_preserved(self):
        m = message("m", "[Paper](https://doi.org/10.1000/example(2020))")
        m["parts"].append({"id": "tool", "type": "tool", "state": {"status": "completed", "output": "https://arxiv.org/abs/1706.03762"}})
        rows = extract_citations(PROJECT, SESSION, {"messages": [m]}, SCOPE | {"include_tools": True}, "http://127.0.0.1:4792")
        self.assertEqual(rows[0]["doi"], "10.1000/example(2020)")
        self.assertEqual(rows[1]["source_kind"], "tool_discovery")

    def test_alpha_project_subfolders_and_memberships_are_idempotent(self):
        for _ in range(2):
            result = self.flow.alpha_sync(records())
            self.assertEqual(result["verified_memberships"], 2)
        self.assertEqual(len(self.alpha.folders), 2)
        self.assertEqual([len(f["papers"]) for f in self.alpha.folders], [1, 1])
        self.assertEqual(self.alpha.folders[1]["parent_id"], self.alpha.folders[0]["folder_id"])
        self.assertFalse(result["note_write_supported"])

    def test_structured_search_output_ids_are_supported_without_parsing_inputs(self):
        m = message("m", "A literature search")
        m["parts"].append({"id": "tool", "type": "tool", "state": {"status": "completed",
            "input": {"arxiv_id": "2203.15556"}, "output": {"papers": [{"arxiv_id": "1706.03762", "title": "A result"}]}}})
        rows = extract_citations(PROJECT, SESSION, {"messages": [m]}, SCOPE | {"include_tools": True}, "http://127.0.0.1:4792")
        self.assertEqual([r["arxiv"] for r in rows], ["1706.03762"])

    def test_readonly_preview_does_not_create_remote_objects(self):
        self.flow.alpha_sync(records(), dry_run=True)
        self.flow.zotero_sync(records(), SCOPE, dry_run=True)
        self.assertEqual(self.alpha.folders, [])
        self.assertEqual(self.zotero.creates, 0)

    def test_repeat_keeps_one_paper_one_provenance_note_and_human_content(self):
        result = self.flow.zotero_sync(records(), SCOPE)
        note_key = result["papers"][0]["note_key"]
        self.zotero.items[note_key]["data"]["note"] += "<p>Human addition</p>"
        result = self.flow.zotero_sync(records(), SCOPE)
        self.assertEqual(self.zotero.creates, 2)
        self.assertEqual(result["existing_notes"], 1)
        self.assertIn("Human addition", self.zotero.items[note_key]["data"]["note"])
        self.assertEqual(len(self.zotero.collections), 2)

    def test_lost_note_create_response_reconciles_after_restart(self):
        self.zotero.lose_note_response = True
        with self.assertRaises(BridgeError):
            self.flow.zotero_sync(records(), SCOPE)
        reopened = ResearchFlow(self.root, self.engine)
        reopened.metadata = self.flow.metadata
        result = reopened.zotero_sync(records(), SCOPE)
        self.assertEqual(result["existing_notes"], 1)
        self.assertEqual(self.zotero.creates, 2)

    def test_unsynced_local_paper_blocks_cloud_duplicate(self):
        self.engine.local_reader = lambda: [{"key": "LOCALONE", "data": {"url": "https://arxiv.org/abs/1706.03762", "itemType": "preprint"}}]
        result = self.flow.zotero_sync(records(), SCOPE)
        self.assertEqual(self.zotero.creates, 0)
        self.assertEqual(len(result["review"]), 1)

    def test_new_citation_adds_note_without_duplicating_paper(self):
        self.flow.zotero_sync(records(), SCOPE)
        row = records()[0] | {"message_id": "message-two", "citation_id": "new-citation"}
        self.flow.zotero_sync([row], SCOPE)
        self.assertEqual(self.zotero.creates, 3)

    def test_scope_requires_projects_and_is_bound_to_plan_contract(self):
        with self.assertRaises(BridgeError):
            validate_options({"project_ids": []})
        designer = Designer(self.root, self.engine)
        self.addCleanup(designer.shutdown)
        graph = copy.deepcopy(designer.project)
        graph["edges"].append({"id": "research", "source": "openresearch", "target": "alphaxiv", "purpose": "Project papers", "research_scope": SCOPE})
        designer.save_graph(graph)
        spec = designer.specification("research")
        plan = {"summary": "Research", "steps": [{"op": "orx_citations", "settings": "{}"}, {"op": "alpha_project_library", "settings": "{}"}]}
        self.assertTrue(designer.validate_plan(plan, spec))
        plan["steps"][0]["settings"] = '{"project_ids":["other"]}'
        with self.assertRaises(BridgeError):
            designer.validate_plan(plan, spec)

    def test_semantic_consent_is_project_and_provider_specific(self):
        options = SCOPE | {"classifier": "codex"}
        self.assertFalse(self.flow.authorized(options))
        with self.assertRaises(BridgeError):
            self.flow.collect(options)
        self.flow.authorize(options)
        self.assertTrue(self.flow.authorized(options))
        self.assertFalse(self.flow.authorized(options | {"project_ids": ["other-project"]}))
        self.assertFalse(self.flow.authorized(options | {"classifier": "claude"}))
        reopened = ResearchFlow(self.root, self.engine)
        self.assertTrue(reopened.authorized(options))

    def test_semantic_classification_cache_reuses_results_across_edges_and_restart(self):
        options = SCOPE | {"classifier": "codex"}
        self.flow.authorize(options)
        payload = {"messages": [message("m1", "Training https://arxiv.org/abs/1706.03762")]}
        def get(path, params=None):
            return {"/api/projects": {"projects": [PROJECT]}, "/api/chat/sessions": {"sessions": [SESSION | {"projectId": PROJECT["id"]}]},
                    "/api/chat/sessions/session-one/messages": payload}[path]
        calls = []
        def classify(rows, scope):
            calls.append(1)
            return {r["citation_id"]: {"category": "模型与方法", "reason": "Used as an architecture reference"} for r in rows}
        self.flow.get, self.flow.classifier = get, classify
        for _ in range(2):
            result = self.flow.collect(options)
            self.assertEqual(result["records"][0]["classifier"], "codex")
        reopened = ResearchFlow(self.root, self.engine, classifier=classify)
        reopened.get = get
        reopened.collect(options)
        self.assertEqual(len(calls), 1)

    def test_pdf_quotes_not_in_document_never_create_annotation(self):
        path = self.root / "fixture.pdf"
        text = b"BT /F1 12 Tf 50 700 Td (This is an actual sentence on the page for a verified quotation.) Tj ET"
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        content, offsets = b"%PDF-1.4\n", [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(content)); content += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
        xref = len(content)
        content += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets[1:])
        content += b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF"
        path.write_bytes(content)
        row = records()[0] | {"context": 'A summary: "This invented claim does not appear anywhere in the source PDF."'}
        created, pending = self.flow.highlights(self.zotero, {"key": "PDFONE"}, path, row, "test:")
        self.assertEqual((created, pending), (0, 1))
        self.assertEqual(self.zotero.creates, 0)
        row["context"] = 'Quote: "This is an actual sentence on the page for a verified quotation."'
        self.assertEqual(self.flow.highlights(self.zotero, {"key": "PDFONE"}, path, row, "test:")[0], 1)
        self.assertEqual(self.flow.highlights(self.zotero, {"key": "PDFONE"}, path, row, "test:")[0], 0)
        annotation = next(i for i in self.zotero.items.values() if i["data"]["itemType"] == "annotation")
        position = json.loads(annotation["data"]["annotationPosition"])
        self.assertGreater(position["rects"][0][1], 680)  # PDF bottom-left origin, not screen coordinates.


if __name__ == "__main__":
    unittest.main()
