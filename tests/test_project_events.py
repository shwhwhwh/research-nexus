import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bridge.project_events import ProjectEvents


class ProjectEventStreamTests(unittest.TestCase):
    def test_real_sse_project_frame_and_reconnect_without_project_polling(self):
        calls, requests_seen = [], []
        stopped = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *_): pass
            def do_GET(self):
                requests_seen.append(self.path)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(b': ready\n\nevent: chat.message\ndata: {"private":"must be ignored"}\n\n')
                self.wfile.write(b'event: project.updated\ndata: {"project":{"id":"instant"}}\n\n')
                self.wfile.flush()
                self.close_connection = True
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        listener = ProjectEvents(lambda: f'http://127.0.0.1:{server.server_port}', lambda: True,
                                 lambda *args: calls.append(args), stopped)
        thread = threading.Thread(target=listener.run, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while calls.count(('connected',)) < 2 and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertGreaterEqual(calls.count(('connected',)), 2)
            self.assertIn(('project', 'instant'), calls)
            self.assertTrue(all(p == '/api/events' for p in requests_seen))
            self.assertTrue(all(c[0] in ('connected', 'project') for c in calls))
        finally:
            stopped.set(); listener.close(); thread.join(2)
            server.shutdown(); server.server_close()
        self.assertFalse(thread.is_alive())

    def test_bad_or_unrelated_payloads_do_not_trigger_onboarding(self):
        calls = []
        listener = ProjectEvents(lambda: '', lambda: True, lambda *args: calls.append(args), threading.Event())
        for raw in ('bad json', '[]', 'null', '{"project":null}', '{"project":{"id":23}}'):
            listener.handle('project.updated', raw)
        listener.handle('chat.message', json.dumps({'project': {'id': 'no'}}))
        self.assertEqual(calls, [])
        listener.handle('resync.required', '')
        self.assertEqual(calls, [('resync',)])
