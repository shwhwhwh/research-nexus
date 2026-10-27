import base64
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from bridge.builder import Builder
from bridge.components import Components
from bridge.designer import Designer
from bridge.domain import BridgeError


def component(cid, recipe='folder', url='', credential_env=''):
    return {'id': cid, 'name': cid, 'recipe': recipe, 'url': url, 'api_url': '', 'credential_env': credential_env, 'description': 'Fictional test component'}


def blueprint():
    return {'format': 'research-nexus-blueprint', 'schema_version': 2, 'id': 'fictional-reading', 'name': 'Fictional reading system',
        'version': '1.0.0', 'description': 'Fictional portable data pipeline', 'requirements': [],
        'components': [component('input'), component('output')],
        'flows': [{'id': 'papers', 'source': 'input', 'target': 'output', 'purpose': 'Deduplicate arxiv and save papers.json', 'data_type': 'JSON',
            'schedule': 'manual', 'sample_json': json.dumps([{'arxiv': 'a', 'title': 'A'}, {'arxiv': 'a', 'title': 'A'}, {'arxiv': 'b', 'title': 'B'}]),
            'research_scope_json': '', 'plan': {'summary': 'Deduplicate and save', 'notes': 'Fictional fixture', 'readiness': 'ready', 'requirements': [],
                'steps': [{'op': 'dedupe', 'settings': '{"key":"arxiv"}'}, {'op': 'write_json', 'settings': '{"filename":"papers.json"}'}]}}]}


class BuilderTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[1] / 'data/builder-test-temp'; folder.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=folder); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.d = Designer(self.root); self.addCleanup(self.d.shutdown)
        self.b = Builder(self.root, self.d)

    def wait(self):
        end = time.monotonic() + 5
        while self.d.workers and time.monotonic() < end: time.sleep(.01)
        self.assertFalse(self.d.workers)

    def imported(self, value=None):
        result = self.b.start({'manifest': value or blueprint()}); self.wait(); return self.b.job(result['job_id'])

    def test_design_export_replay_skips_agent_and_keeps_stable_versions(self):
        with patch.object(self.d, 'command', return_value=['fixture']), patch.object(self.b, 'compile', return_value=blueprint()) as agent:
            result = self.b.start({'description': 'Fictional deduplicated reading list system', 'provider': 'codex'}); self.wait()
            job = self.b.job(result['job_id']); self.assertEqual(job['status'], 'ready', job.get('error'))
            self.assertEqual(job['agent_calls'], 1); agent.assert_called_once()
            exported = self.b.export(job['id']); versions = copy.deepcopy(self.d.project['versions']); active = copy.deepcopy(self.d.project['active'])
            with patch.object(self.d, 'command', side_effect=AssertionError('Replay must not invoke CLI')):
                again = self.imported(exported)
            self.assertEqual(again['status'], 'ready', again.get('error')); self.assertEqual(again['agent_calls'], 0)
            self.assertEqual(self.d.project['versions'], versions); self.assertEqual(self.d.project['active'], active)
            self.assertNotIn('input', exported); self.assertNotIn('components', self.b.public()['jobs'][0].get('input', {}))

    def test_system_executes_repeatedly_and_accepts_runtime_input(self):
        job = self.imported()
        for _ in range(2):
            self.b.run(job['id'], [{'arxiv': 'new', 'title': 'Runtime'}, {'arxiv': 'new', 'title': 'Runtime'}]); self.wait()
            self.assertTrue(job['run_result']['success'], job['run_result'])
        self.assertTrue(all(self.d.project['last_run'].get(eid,0)>0 for eid in job['edge_ids']))
        files = list((self.d.base / 'outputs').glob('*/papers.json'))
        self.assertEqual(len(files), 1); self.assertEqual(json.loads(files[0].read_text()), [{'arxiv': 'new', 'title': 'Runtime'}])

    def test_missing_components_resume_without_redesign_and_existing_graph_preserved(self):
        active_before = copy.deepcopy(self.d.project['active']); nodes_before = copy.deepcopy(self.d.project['nodes'])
        with patch.object(self.b.components, 'prepare', return_value={'status': 'needs_setup', 'requirement': 'Install fixture app'}):
            job = self.imported()
        self.assertEqual(job['status'], 'needs_setup'); self.assertEqual(self.d.project['nodes'], nodes_before)
        self.b.resume(job['id'], {'install_components': True}); self.wait()
        self.assertEqual(job['status'], 'ready', job.get('error')); self.assertEqual(job['agent_calls'], 0)
        self.assertTrue(all(n in self.d.project['nodes'] for n in nodes_before)); self.assertTrue(all(k in self.d.project['active'] for k in active_before))

    def test_unsupported_plan_is_saved_but_never_activated(self):
        m = blueprint(); m['flows'][0]['plan'].update(readiness='needs_setup', requirements=['Implement missing adapter'])
        job = self.imported(m)
        self.assertEqual(job['status'], 'needs_setup'); self.assertIn('Implement missing adapter', job['requirements'])
        self.assertFalse(self.d.project['active']); self.assertEqual(self.b.export(job['id']), m)

    def test_templates_cannot_import_commands_credentials_paths_or_other_environment(self):
        for field, value in [('command', 'run-shell'), ('executable', 'C:/private.exe'), ('token', 'private')]:
            m = blueprint(); m['components'][0][field] = value
            with self.assertRaises(BridgeError): self.b.validate(m)
        for name in ('AWS_SECRET_ACCESS_KEY', 'RN_ALPHAXIV_API_KEY', 'RN_ZOTERO_API_KEY'):
            m = blueprint(); m['components'][0]['credential_env'] = name
            with self.assertRaises(BridgeError): self.b.validate(m)
        self.d.integration_credentials['NEXUS_FIXTURE_KEY'] = 'private-fixture-key'
        m = blueprint(); m['description'] = 'private-fixture-key'
        with self.assertRaises(BridgeError): self.b.validate(m)

    def test_bound_credentials_need_setup_and_are_not_exported(self):
        m = blueprint(); m['components'][0] = component('input', 'http-api', 'https://example.org/', 'NEXUS_EXAMPLE_KEY')
        m['flows'][0]['plan']['steps'].insert(0, {'op': 'http_get', 'settings': '{"url":"https://example.org/papers","headers":{"Authorization":"Bearer ${ENV:NEXUS_EXAMPLE_KEY}"}}'})
        job = self.imported(m); self.assertEqual(job['status'], 'needs_setup')
        self.b.save_bindings(job['id'], {'NEXUS_EXAMPLE_KEY': 'fixture-password-value'})
        self.assertNotIn('fixture-password-value', self.b.vault_path.read_text())
        self.b.resume(job['id'], {}); self.wait(); self.assertEqual(job['status'], 'ready', job.get('error'))
        self.assertNotIn('fixture-password-value', json.dumps(self.b.export(job['id'])))
        other = copy.deepcopy(m); other['components'][0]['url'] = 'https://other.example.org/'; other['flows'][0]['plan']['steps'][0]['settings'] = other['flows'][0]['plan']['steps'][0]['settings'].replace('https://example.org', 'https://other.example.org')
        second = self.imported(other); self.assertEqual(second['status'], 'needs_setup')

    def test_private_source_is_not_in_public_status_or_export_and_private_urls_blocked(self):
        with patch.object(self.d, 'command', return_value=['fixture']), patch.object(self.b, 'compile', return_value=blueprint()):
            result = self.b.start({'description': 'Private paper source text for fixture only'}); self.wait()
        self.assertNotIn('Private paper source', json.dumps(self.b.public()))
        with self.assertRaises(BridgeError): self.b.public_url('https://127.0.0.1/private')
        with self.assertRaises(BridgeError): self.b.public_url('http://example.org')
        self.assertIn('Fictional text paper', self.b.source({'description': 'Build a system', 'paper_name': 'test.txt', 'paper_base64': base64.b64encode(b'Fictional text paper').decode()}))

    def test_uploaded_pdf_is_extracted_as_source_text(self):
        from types import SimpleNamespace
        from bridge.demo_system import SampleArxiv
        pdf = SampleArxiv().pdf(SimpleNamespace(arxiv='0000.00001'), self.root / 'paper-fixture')
        text = self.b.source({'paper_name': 'fixture.pdf', 'paper_base64': base64.b64encode(pdf.read_bytes()).decode()})
        self.assertIn('Fictional Research Nexus demo PDF', text)

    def test_live_http_channel_reads_actual_data_instead_of_preview(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                data = b'[{"arxiv":"actual","title":"Actual HTTP input"}]'
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            m = blueprint(); m['components'][0] = component('input', 'http-api', url)
            m['flows'][0]['plan']['steps'].insert(0, {'op':'http_get','settings':json.dumps({'url':url+'/papers'})})
            job = self.imported(m); self.assertEqual(job['status'], 'ready', job.get('error'))
            self.b.run(job['id']); self.wait(); self.assertTrue(job['run_result']['success'])
            output = next((self.d.base/'outputs').glob('*/papers.json'))
            self.assertEqual(json.loads(output.read_text())[0]['arxiv'], 'actual')
        finally: server.shutdown(); server.server_close()

    def test_busy_launch_remains_resumable_and_restart_marks_interrupted(self):
        self.d.workers.add('fixture')
        with self.assertRaises(BridgeError): self.b.start({'manifest': blueprint()})
        self.assertEqual(self.b.jobs[-1]['status'], 'error')
        self.d.workers.clear(); self.b.resume(self.b.jobs[-1]['id'], {}); self.wait()
        self.assertEqual(self.b.jobs[-1]['status'], 'ready')
        self.b.jobs[-1]['status'] = 'running'; self.b._save()
        self.assertEqual(Builder(self.root, self.d).jobs[-1]['status'], 'interrupted')

    def test_failed_channel_test_leaves_graph_untouched(self):
        m = blueprint(); m['flows'][0]['sample_json'] = '{"wrong":"shape"}'
        graph = copy.deepcopy(self.d.project); job = self.imported(m)
        self.assertEqual(job['status'], 'error'); self.assertEqual(self.d.project, graph)

    def test_layout_or_graph_changes_during_preparation_do_not_get_overwritten(self):
        def prepare(*args):
            graph = copy.deepcopy(self.d.project); graph['name'] = 'Changed while building'; self.d.save_graph(graph)
            return {'status': 'ready'}
        with patch.object(self.b.components, 'prepare', side_effect=prepare): job = self.imported()
        self.assertEqual(job['status'], 'error'); self.assertIn('画布', job['error'])
        self.assertEqual(self.d.project['name'], 'Changed while building')

    def test_component_downloads_are_cached_and_install_uses_locked_version(self):
        c = Components(self.root, self.d); calls = []
        def command(args, job_id):
            calls.append(args)
            if args[1] == 'download':
                folder = Path(args[args.index('--download-directory') + 1]); (folder / 'installer.exe').write_bytes(b'fictional')
                (folder / 'package.yaml').write_text('PackageVersion: 1.2.3\n')
        with patch('bridge.components.shutil.which', return_value='winget.exe'), patch.object(c, 'command', side_effect=command), patch.object(c, 'detect', side_effect=[{'ready': False}, {'ready': False}, {'ready': True, 'executable': 'fixture.exe'}]):
            first = c.prepare(component('app', 'obsidian'), False, 'fixture', lambda _: None)
            second = c.prepare(component('app', 'obsidian'), True, 'fixture', lambda _: None)
        self.assertEqual(first['status'], 'needs_setup'); self.assertEqual(second['status'], 'ready')
        self.assertEqual(sum(x[1] == 'download' for x in calls), 1)
        self.assertIn('--version', calls[-1]); self.assertIn('1.2.3', calls[-1])

    def test_reviewed_project_template_and_schema_validate(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root/'system-templates/project-literature.rn-system.json').read_text(encoding='utf-8'))
        self.assertEqual(self.b.validate(manifest), manifest)
        self.assertEqual(len(manifest['flows']), 2)
        self.assertTrue(all(json.loads(f['research_scope_json'])['classifier']=='keywords' for f in manifest['flows']))

    def test_managed_openresearch_bundle_reuses_verified_download_without_launching_app(self):
        import hashlib
        from zipfile import ZipFile
        c = self.b.components; folder = c.cache/'OpenResearch'; folder.mkdir()
        archive = folder/'openresearch.zip'
        with ZipFile(archive, 'w') as z:
            z.writestr('orx.exe', b'fictional binary never executed')
            z.writestr('LICENSE', 'fictional license'); z.writestr('README.md', 'fictional readme')
            z.writestr('../escape.txt', 'must not extract')
        (folder/'download.json').write_text(json.dumps({'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'version':'fixture'}))
        def compile_launcher(args, job):
            self.assertIn('/target:winexe', args)
            (folder/'OpenResearch.exe').write_bytes(b'fictional launcher never executed')
        with patch.object(c, 'detect', return_value={'ready':False}), patch.object(c, 'command', side_effect=compile_launcher) as command, patch('bridge.components.requests.Session', side_effect=AssertionError('Cached bundle must not redownload')):
            result = c.prepare(component('orx','openresearch'), True, 'fixture', lambda _: None)
        self.assertEqual(result['status'], 'ready'); command.assert_called_once()
        self.assertFalse((c.cache/'escape.txt').exists())

    def test_builtin_services_are_checked_and_existing_services_are_reused(self):
        from types import SimpleNamespace
        root = Path(__file__).resolve().parents[1]
        m = json.loads((root/'system-templates/project-literature.rn-system.json').read_text(encoding='utf-8'))
        engine = SimpleNamespace(openresearch_online=lambda:True, start_openresearch=lambda:(_ for _ in ()).throw(AssertionError('Must reuse running service')),
            config=SimpleNamespace(secret=lambda _:''))
        self.d.engine = engine
        job = {'manifest':m,'components':{},'logs':[]}
        with patch('bridge.builder.requests.Session') as session:
            session.return_value.__enter__.return_value.get.return_value.status_code=200
            self.assertEqual(self.b.local_services(job), [])
        engine.openresearch_online=lambda:False
        engine.start_openresearch=lambda:(_ for _ in ()).throw(BridgeError('Fixture service unavailable'))
        with patch('bridge.builder.requests.Session') as session:
            session.return_value.__enter__.return_value.get.return_value.status_code=503
            missing=self.b.local_services(job)
        self.assertTrue(any('OpenResearch' in x for x in missing));self.assertTrue(any('Zotero' in x for x in missing))

    def test_cancelled_design_does_not_deploy_graph(self):
        import threading
        gate, entered = threading.Event(), threading.Event()
        def compile(*args):
            entered.set();gate.wait(3);return blueprint()
        graph=copy.deepcopy(self.d.project)
        with patch.object(self.d,'command',return_value=['fixture']),patch.object(self.b,'compile',side_effect=compile):
            result=self.b.start({'description':'Fictional cancellable local workflow'})
            self.assertTrue(entered.wait(2));self.b.cancel(result['job_id']);gate.set();self.wait()
        self.assertEqual(self.b.job(result['job_id'])['status'],'cancelled')
        self.assertEqual(self.d.project,graph)

    def test_existing_keys_are_redacted_before_design_agent_input(self):
        self.d.integration_credentials['NEXUS_FIXTURE_KEY']='private-known-fixture-key'
        with patch.object(self.d,'command',return_value=['fixture']),patch.object(self.b,'compile',return_value=blueprint()) as agent:
            result=self.b.start({'description':'A fictional workflow containing private-known-fixture-key accidentally.'});self.wait()
        self.assertEqual(self.b.job(result['job_id'])['status'],'ready')
        self.assertNotIn('private-known-fixture-key',agent.call_args.args[1])
        self.assertIn('[redacted]',agent.call_args.args[1])
