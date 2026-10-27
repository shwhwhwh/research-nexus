import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge.designer import Designer
from bridge.domain import BridgeError
from bridge.research_flow import ResearchFlow, validate_options, DEFAULT_CATEGORIES
from test_research_flow import MemoryAlpha, MemoryZotero, message


class ProjectDiscoveryTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / 'data/discovery-test-temp'
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.alpha, self.zotero = MemoryAlpha(), MemoryZotero()
        self.cfg = {'openresearch_url': 'http://127.0.0.1:4792', 'zotero_user_id': '123'}
        self.engine = SimpleNamespace(config=SimpleNamespace(snapshot=lambda: dict(self.cfg), secret=lambda k: 'fixture-key'),
            alpha_factory=lambda key: self.alpha, zotero_factory=lambda uid, key: self.zotero,
            local_reader=lambda: [], paper_write_lock=threading.RLock())
        self.flow = ResearchFlow(self.root, self.engine)
        self.projects = [{'id': 'one', 'name': 'Example One'}]
        self.texts = {'one': 'Training reference https://arxiv.org/abs/1706.03762'}
        self.scope = {'project_ids': [], 'auto_discover': True, 'max_papers': 1, 'classifier': 'keywords', 'categories': DEFAULT_CATEGORIES}
        self.flow.get = self.get
        self.flow.metadata = lambda paper: {'title': 'Fixture ' + paper.source_id, 'authors': ['Example Author']}

    def get(self, path, params=None):
        if path == '/api/projects':
            return {'projects': copy.deepcopy(self.projects)}
        if path == '/api/chat/sessions':
            pid = params['projectId']
            return {'sessions': [{'id': 'session-' + pid, 'projectId': pid}] if pid in self.texts else []}
        pid = path.split('/')[-2].removeprefix('session-')
        return {'messages': [message('message-' + pid, self.texts[pid])]}

    def designer(self):
        d = Designer(self.root, self.engine)
        self.addCleanup(d.shutdown)
        d.research.get = self.get
        d.research.metadata = self.flow.metadata
        return d

    def activate(self, d):
        for edge in d.project['edges']:
            if 'research_scope' not in edge:
                continue
            eid = edge['id']
            plan = {'readiness': 'ready', 'summary': 'Fixture research flow', 'steps': [
                {'op': 'orx_citations', 'settings': '{}'},
                {'op': 'alpha_project_library' if edge['target'] == 'alphaxiv' else 'zotero_project_notes', 'settings': '{}'}]}
            d.validate_plan(plan, d.specification(eid))
            version = {'id': 'version-' + eid, 'edge_id': eid, 'kind': 'build', 'status': 'candidate', 'logs': [],
                       'contract': d.contract(eid), 'plan': plan, 'tested': True}
            d.runs.append(version)
            d.project['versions'].setdefault(eid, []).append(version['id'])
            d.activate(eid, version['id'])

    def wait(self, d):
        deadline = time.monotonic() + 4
        while d.workers and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(d.workers)

    def test_future_grant_cannot_be_inferred_from_fixed_grant_or_other_provider_source(self):
        fixed = {'project_ids': ['one'], 'classifier': 'codex'}
        self.flow.authorize(fixed)
        auto = self.scope | {'classifier': 'codex'}
        self.assertFalse(self.flow.authorized(auto))
        self.flow.authorize(auto)
        reopened = ResearchFlow(self.root, self.engine)
        self.assertTrue(reopened.authorized(auto))
        self.assertFalse(reopened.authorized(auto | {'classifier': 'claude'}))
        self.cfg['openresearch_url'] = 'http://127.0.0.1:4793'
        self.assertFalse(reopened.authorized(auto))

    def test_auto_mode_requires_explicit_mode_and_no_fixed_list(self):
        validate_options(self.scope)
        for options in ({'project_ids': []}, self.scope | {'project_ids': ['one']}, self.scope | {'auto_discover': 'true'}):
            with self.assertRaises(BridgeError):
                validate_options(options)

    def test_wizard_requires_future_consent_and_rejects_raw_scope_expansion(self):
        d = self.designer()
        auto = self.scope | {'classifier': 'codex'}
        with self.assertRaises(BridgeError):
            d.research_setup({'research_scope': auto, 'allow_model_context': True})
        graph = copy.deepcopy(d.project)
        graph['edges'].append({'id': 'unsafe', 'source': 'openresearch', 'target': 'zotero', 'purpose': 'Fixture', 'research_scope': auto})
        with self.assertRaises(BridgeError):
            d.save_graph(graph)
        d.research_setup({'research_scope': auto, 'allow_future_model_context': True})
        self.assertTrue(d.research.authorized(auto))

    def test_empty_projects_and_renames_keep_one_root_after_restart(self):
        self.texts.clear()
        status = self.flow.discover([(self.scope, 'alpha'), (self.scope, 'zotero')])
        self.assertFalse(status['error'])
        self.assertEqual((len(self.alpha.folders), len(self.zotero.collections)), (1, 1))
        self.projects[0]['name'] = 'Renamed Example'
        reopened = ResearchFlow(self.root, self.engine)
        reopened.get = self.get
        reopened.discover([(self.scope, 'alpha'), (self.scope, 'zotero')])
        self.assertEqual((len(self.alpha.folders), len(self.zotero.collections)), (1, 1))
        self.assertEqual(reopened.project_label(self.projects[0]), 'Example One · one · ORX')

    def test_failed_folder_creation_retries_without_duplicate_roots(self):
        original = self.zotero.collection
        self.zotero.collection = lambda *args: (_ for _ in ()).throw(BridgeError('temporary failure'))
        failed = self.flow.discover([(self.scope, 'alpha'), (self.scope, 'zotero')])
        self.assertTrue(failed['error'])
        self.zotero.collection = original
        recovered = self.flow.discover([(self.scope, 'alpha'), (self.scope, 'zotero')])
        self.assertFalse(recovered['error'])
        self.assertEqual((len(self.alpha.folders), len(self.zotero.collections)), (1, 1))

    def test_incremental_caps_do_not_starve_new_papers_or_late_citations(self):
        first = self.flow.collect(self.scope, destination='zotero')['records']
        self.flow.acknowledge(first, self.scope, 'zotero', {'completed_citations': [r['citation_id'] for r in first]})
        self.projects.append({'id': 'two', 'name': 'Example Two'})
        self.texts['two'] = 'Reference https://arxiv.org/abs/2203.15556'
        second = self.flow.collect(self.scope, destination='zotero')['records']
        self.assertEqual([r['project_id'] for r in second], ['two'])
        self.flow.acknowledge(second, self.scope, 'zotero', {'completed_citations': []})
        self.texts['one'] += '\n\nA later citation to https://arxiv.org/abs/1706.03762'
        third = self.flow.collect(self.scope, destination='zotero')['records']
        self.assertEqual([r['project_id'] for r in third], ['one'])
        # Other destinations have their own durable receipts.
        self.assertEqual(self.flow.collect(self.scope, destination='alpha')['papers'], 1)
        self.assertEqual(len(self.flow.collect(self.scope)['records']), 2)

    def test_daily_new_project_is_discovered_without_rebuilding_and_semantics_are_cached(self):
        d = self.designer()
        options = self.scope | {'max_papers': 200, 'classifier': 'codex'}
        calls = []
        def classify(rows, scope):
            calls.extend(r['citation_id'] for r in rows)
            return {r['citation_id']: {'category': '模型与方法', 'reason': 'Fixture research role'} for r in rows}
        d.research.classifier = classify
        d.research_setup({'research_scope': options, 'allow_future_model_context': True, 'schedule': 'daily'})
        self.activate(d)
        contracts = copy.deepcopy(d.project['active'])
        d.discover_projects(); self.wait(d)
        for edge in ('orx-project-alpha', 'orx-project-zotero'):
            d.run(edge, dry_run=False); self.wait(d)
            self.assertEqual(d.runs[-1]['status'], 'success')
        self.projects.append({'id': 'two', 'name': 'New Empty Research'})
        d.discover_projects(); self.wait(d)
        self.assertEqual(d.project['active'], contracts)
        self.assertEqual(len([f for f in self.alpha.folders if not f.get('parent_id')]), 2)
        self.assertIn(('New Empty Research · two · ORX', None), self.zotero.collections)
        self.texts['two'] = 'New reference https://arxiv.org/abs/2203.15556'
        for edge in ('orx-project-alpha', 'orx-project-zotero'):
            d.project['last_run'][edge] = time.time() - 86401
        for _ in range(2):
            d.tick(); self.wait(d)
            self.assertEqual(d.runs[-1]['status'], 'success')
        self.assertEqual(len(calls), 2)
        self.assertEqual(len([i for i in self.zotero.items.values() if i['data']['itemType'] == 'note']), 2)
        for edge in ('orx-project-alpha', 'orx-project-zotero'):
            d.run(edge, dry_run=False); self.wait(d)
            self.assertEqual(d.runs[-1]['result']['source']['citations'], 0)
        self.assertEqual(len(calls), 2)

    def test_paused_destinations_are_not_written_and_idle_has_no_project_polling(self):
        d = self.designer()
        d.research_setup({'research_scope': self.scope})
        self.activate(d)
        d.disable('orx-project-zotero')
        d.project_event('connected'); self.wait(d)
        self.assertEqual(len(self.alpha.folders), 1)
        self.assertEqual(len(self.zotero.collections), 0)
        with patch.object(d.research, 'discover') as discover:
            d.tick(); self.wait(d)
            discover.assert_not_called()
        d.disable('orx-project-alpha')
        self.projects.append({'id': 'two', 'name': 'No Auto Writes'})
        d.project_event('connected'); self.wait(d)
        self.assertEqual(len(self.alpha.folders), 1)

    def test_project_event_queues_while_busy_then_onboards_without_new_plan(self):
        d = self.designer()
        d.research_setup({'research_scope': self.scope})
        self.activate(d)
        d.project_event('connected'); self.wait(d)
        before = copy.deepcopy(d.project['active'])
        self.projects.append({'id': 'instant', 'name': 'Instant Project'})
        d.workers.add('fixture-busy')
        d.project_events.handle('project.updated', json.dumps({'project': self.projects[-1]}))
        self.assertTrue(d.discovery_pending)
        self.assertEqual(len(self.alpha.folders), 1)
        d.workers.clear()
        d.tick(); self.wait(d)
        self.assertEqual(len(self.alpha.folders), 2)
        self.assertEqual(d.project['active'], before)
        with patch.object(d.research, 'discover') as discover:
            d.project_events.handle('project.updated', json.dumps({'project': self.projects[-1]}))
            d.tick()
            discover.assert_not_called()

    def test_reconnect_catches_missed_projects_and_retries_failed_folder_creation(self):
        d = self.designer()
        d.research_setup({'research_scope': self.scope})
        self.activate(d)
        d.project_event('connected'); self.wait(d)
        self.projects.append({'id': 'offline', 'name': 'Created Offline'})
        original = d.research.ensure_project_roots
        with patch.object(d.research, 'ensure_project_roots', side_effect=BridgeError('Temporary outage')):
            d.project_event('connected'); self.wait(d)
        self.assertTrue(d.discovery_pending)
        self.assertGreater(d.discovery_retry_at, time.monotonic())
        d.discovery_retry_at = 0
        d.tick(); self.wait(d)
        self.assertFalse(d.discovery_pending)
        self.assertEqual(len(self.alpha.folders), 2)

    def test_layout_change_retains_active_contracts(self):
        d = self.designer()
        d.research_setup({'research_scope': self.scope})
        self.activate(d)
        active = copy.deepcopy(d.project['active'])
        for layout in ('orbital', 'structured'):
            graph = copy.deepcopy(d.project)
            graph['layout'] = layout
            for n in graph['nodes']:
                n['x'] += 100
            d.save_graph(graph)
            self.assertEqual(d.project['active'], active)
            self.assertEqual(d.project['layout'], layout)
        self.assertEqual(Designer(self.root, self.engine).project['layout'], 'structured')

    def test_failed_destination_batch_stays_pending_without_starving_new_projects(self):
        d = self.designer()
        d.research_setup({'research_scope': self.scope})
        self.activate(d)
        self.projects.append({'id': 'two', 'name': 'Example Two'})
        self.texts['two'] = 'https://arxiv.org/abs/2203.15556'
        with patch.object(d.research, 'alpha_sync', side_effect=BridgeError('Temporary service failure')):
            d.run('orx-project-alpha', dry_run=False); self.wait(d)
        self.assertEqual(d.runs[-1]['status'], 'error')
        delivery = next(iter(d.research.state['deliveries'].values()))
        self.assertTrue(delivery)
        self.assertFalse(any(row['done'] for row in delivery.values()))
        pending = d.research.collect(self.scope, destination='alpha')
        self.assertEqual([r['project_id'] for r in pending['records']], ['two'])

    def test_source_outage_and_deleted_projects_never_remove_archives(self):
        self.flow.discover([(self.scope, 'alpha'), (self.scope, 'zotero')])
        before = copy.deepcopy((self.alpha.folders, self.zotero.collections))
        self.flow.get = lambda *args: (_ for _ in ()).throw(BridgeError('Source unavailable'))
        self.assertTrue(self.flow.discover([(self.scope, 'alpha'), (self.scope, 'zotero')])['error'])
        self.assertEqual((self.alpha.folders, self.zotero.collections), before)
        self.flow.get = self.get
        self.projects.clear()
        status = self.flow.discover([(self.scope, 'alpha'), (self.scope, 'zotero')])
        self.assertFalse(status['error'])
        self.assertEqual(status['projects'], [])
        self.assertEqual(self.flow.collect(self.scope, destination='zotero')['records'], [])
        self.assertEqual((self.alpha.folders, self.zotero.collections), before)


if __name__ == '__main__':
    unittest.main()
