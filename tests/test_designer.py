import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge.designer import Designer, digest
from bridge.domain import BridgeError


class DesignerTests(unittest.TestCase):
    def setUp(self):
        test_base=Path(__file__).resolve().parents[1]/'data'/'designer-test-temp'
        test_base.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_base)
        assert Path(self.temp.name).resolve().is_relative_to(test_base.resolve())
        self.addCleanup(self.temp.cleanup)
        self.designer = Designer(Path(self.temp.name))
        self.addCleanup(self.designer.shutdown)
        project = copy.deepcopy(self.designer.project)
        project['nodes'] += [
            {'id':'input','name':'Input','kind':'folder','description':'sample rows','x':1,'y':1},
            {'id':'output','name':'Output','kind':'folder','description':'local JSON','x':300,'y':1}]
        project['edges'].append({'id':'example','source':'input','target':'output','purpose':'Deduplicate arxiv and save JSON','schedule':'manual','sample':[{'arxiv':'a','title':'A'},{'arxiv':'a','title':'A'},{'arxiv':'b','title':'B'}]})
        self.designer.save_graph(project)
        self.plan = {'summary':'去重归档样例','notes':'本地输出','steps':[{'op':'dedupe','settings':'{"key":"arxiv"}'},{'op':'write_json','settings':'{"filename":"papers.json"}'}]}

    def candidate(self, version='version-1'):
        run = {'id':version,'edge_id':'example','kind':'build','status':'candidate','time':'2026-10-26','logs':[],'plan':copy.deepcopy(self.plan),'contract':self.designer.contract('example')}
        self.designer.runs.append(run)
        self.designer.project['versions'].setdefault('example',[]).append(version)
        return run

    def wait(self):
        start = time.monotonic()
        while self.designer.workers and time.monotonic()-start < 4:
            time.sleep(.02)
        self.assertFalse(self.designer.workers)

    def test_dry_run_deduplicates_without_writing(self):
        spec = self.designer.specification('example')
        result = self.designer.execute_plan(self.plan,spec,'example',spec['sample'])
        self.assertEqual(len(result['data']),2)
        self.assertFalse(Path(result['artifacts'][0]['path']).exists())
        self.assertFalse(result['artifacts'][0]['written'])

    def test_test_activate_and_repeat_have_stable_output(self):
        candidate=self.candidate()
        with self.assertRaises(BridgeError):self.designer.activate('example',candidate['id'])
        self.designer.run('example',candidate['id'],dry_run=True);self.wait()
        self.designer.activate('example',candidate['id'])
        for _ in range(2):self.designer.run('example',dry_run=False);self.wait()
        output=self.designer.base/'outputs'/'output'/'papers.json'
        self.assertEqual(json.loads(output.read_text('utf-8')),[{'arxiv':'a','title':'A'},{'arxiv':'b','title':'B'}])
        self.assertEqual(len(list(output.parent.glob('*.json'))),1)

    def test_contract_changes_invalidate_activation_but_moving_does_not(self):
        candidate=self.candidate();candidate['tested']=True;self.designer.activate('example',candidate['id'])
        graph=copy.deepcopy(self.designer.project);graph['nodes'][-1]['x']=555
        self.designer.save_graph(graph);self.assertIn('example',self.designer.project['active'])
        graph['edges'][-1]['purpose']='Different purpose';self.designer.save_graph(graph)
        self.assertNotIn('example',self.designer.project['active'])
        with self.assertRaises(BridgeError):self.designer.activate('example',candidate['id'])

    def test_cannot_run_unactivated_plan(self):
        candidate=self.candidate()
        with self.assertRaises(BridgeError):self.designer.run('example',candidate['id'],dry_run=False)

    def test_cannot_inject_activation_via_canvas_save(self):
        graph=copy.deepcopy(self.designer.project);graph['active']={'example':{'version':'fake'}}
        self.designer.save_graph(graph);self.assertEqual(self.designer.project['active'],{})

    def test_output_traversal_and_code_execution_are_rejected(self):
        for op, settings in [('write_json','{"filename":"../../escape.json"}'),('shell','{"command":"echo unsafe"}')]:
            plan={'summary':'x','steps':[{'op':op,'settings':settings}]}
            with self.assertRaises(BridgeError):self.designer.validate_plan(plan,self.designer.specification('example'))

    def test_http_destinations_and_literal_credentials_are_rejected(self):
        spec=self.designer.specification('example');spec['source']['url']='https://source.example';spec['target']['url']='https://target.example'
        for options in [{'url':'https://unregistered.example/data'},{'url':'https://target.example/data','headers':{'Authorization':'secret-inline'}}]:
            with self.assertRaises(BridgeError):self.designer.validate_plan({'summary':'x','steps':[{'op':'http_get','settings':json.dumps(options)}]},spec)
        with self.assertRaises(BridgeError):self.designer.validate_plan({'summary':'x','steps':[{'op':'http_post','settings':'{"url":"https://source.example/write"}'}]},spec)

    def test_http_preview_never_sends_a_request(self):
        spec=self.designer.specification('example');spec['source']['url']='https://source.example'
        plan={'summary':'x','steps':[{'op':'http_get','settings':'{"url":"https://source.example/items"}'}]}
        with patch('requests.Session') as session:
            result=self.designer.execute_plan(plan,spec,'example',spec['sample'],dry_run=True)
            session.assert_not_called();self.assertEqual(result['data'],spec['sample'])

    def test_http_post_receipts_prevent_duplicate_writes(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                received.append(self.rfile.read(int(self.headers['Content-Length'])))
                body=b'{"saved":true}';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        spec=self.designer.specification('example');spec['target']['url']=f'http://127.0.0.1:{server.server_port}/'
        url=spec['target']['url']+'items';plan={'summary':'x','steps':[{'op':'http_post','settings':json.dumps({'url':url})}]}
        for _ in range(2):self.designer.execute_plan(plan,spec,'example',[{'title':'one'}],dry_run=False)
        self.assertEqual(len(received),1)
        restarted=Designer(Path(self.temp.name))
        restarted.execute_plan(plan,spec,'example',[{'title':'one'}],dry_run=False)
        self.assertEqual(len(received),1)

    def test_uncertain_write_is_not_retried(self):
        spec=self.designer.specification('example');spec['target']['url']='https://target.example'
        url='https://target.example/items';options={'url':url};data=[{'id':1}]
        receipt=digest({'edge':'example','url':url,'body':'${data}','data':data})
        self.designer.receipts[receipt]={'status':'pending'}
        with patch('requests.Session') as session:
            with self.assertRaises(BridgeError):self.designer.execute_plan({'summary':'x','steps':[{'op':'http_post','settings':json.dumps(options)}]},spec,'example',data,dry_run=False)
            session.assert_not_called()

    def test_large_results_remain_valid_json(self):
        candidate=self.candidate();candidate['plan']={'summary':'x','steps':[{'op':'input','settings':'{}'}]}
        self.designer.run('example',candidate['id'],input_data=[{'title':'x'*4000}],dry_run=True);self.wait()
        self.assertEqual(self.designer.runs[-1]['status'],'tested')
        self.assertEqual(len(self.designer.runs[-1]['result']['data'][0]['title']),4000)

    def test_cycle_is_rejected_before_running(self):
        candidate=self.candidate();candidate['tested']=True;self.designer.activate('example',candidate['id'])
        self.designer.project['edges'].append({'id':'reverse','source':'output','target':'input','purpose':'reverse','sample':[]})
        reverse={'id':'version-2','edge_id':'reverse','kind':'build','status':'candidate','plan':copy.deepcopy(self.plan),'tested':True,'contract':self.designer.contract('reverse')}
        self.designer.runs.append(reverse);self.designer.activate('reverse',reverse['id'])
        with self.assertRaises(BridgeError):self.designer.run_graph()
        self.assertFalse(self.designer.workers)

    def test_version_survives_many_execution_records(self):
        candidate=self.candidate();candidate['tested']=True;self.designer.activate('example',candidate['id'])
        for i in range(160):self.designer.runs.append({'id':str(i),'edge_id':'example','kind':'execute','status':'success'})
        self.designer._save();restarted=Designer(Path(self.temp.name))
        self.assertEqual(restarted.version('example',candidate['id'])['id'],candidate['id'])

    def test_restarting_marks_inflight_task_interrupted(self):
        self.designer.runs.append({'id':'old','edge_id':'example','kind':'build','status':'generating'});self.designer._save()
        restarted=Designer(Path(self.temp.name));self.assertEqual(restarted.runs[-1]['status'],'interrupted')

    def test_builtin_archive_is_not_triggered_in_preview(self):
        engine=unittest.mock.Mock();self.designer.engine=engine
        spec=self.designer.specification('existing-archive')
        self.designer.execute_plan({'summary':'x','steps':[{'op':'builtin_archive','settings':'{}'}]},spec,'existing-archive',[],dry_run=True)
        engine.launch.assert_not_called()

    def test_missing_credentials_are_actionable(self):
        with self.assertRaisesRegex(BridgeError,'NEXUS_TEST_MISSING_KEY'):
            self.designer._expand('${ENV:NEXUS_TEST_MISSING_KEY}',{})
        self.assertEqual(self.designer._expand('${ENV:NEXUS_TEST_MISSING_KEY}',{},dry_run=True),'[credential]')

    def test_builtin_cannot_be_removed_silently(self):
        graph=copy.deepcopy(self.designer.project);graph['edges']=[e for e in graph['edges'] if not e.get('builtin')]
        with self.assertRaises(BridgeError):self.designer.save_graph(graph)

    def test_credentials_are_scoped_to_the_registered_node(self):
        spec=self.designer.specification('example');spec['source']['url']='https://source.example';spec['target']['url']='https://target.example'
        step={'op':'http_get','settings':json.dumps({'url':'https://source.example/items','headers':{'Authorization':'Bearer ${ENV:UNRELATED_SECRET}'}})}
        with self.assertRaises(BridgeError):self.designer.validate_plan({'summary':'x','steps':[step]},spec)
        spec['source']['credential_env']='UNRELATED_SECRET'
        self.assertTrue(self.designer.validate_plan({'summary':'x','steps':[step]},spec))
        spec['target']['api_url']='https://api.target.example'
        self.assertTrue(self.designer.validate_plan({'summary':'x','steps':[{'op':'http_post','settings':'{"url":"https://api.target.example/items"}'}]},spec))

    def test_missing_setup_cannot_be_activated(self):
        candidate=self.candidate();candidate['tested']=True;candidate['plan'].update(readiness='needs_setup',requirements=['API endpoint'])
        with self.assertRaises(BridgeError):self.designer.activate('example',candidate['id'])


if __name__=='__main__':unittest.main()
