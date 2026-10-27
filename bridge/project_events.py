"""Read-only OpenResearch SSE subscription; no periodic project-list polling."""
from __future__ import annotations

import json

import requests

from .domain import BridgeError


class ProjectEvents:
    def __init__(self, source, enabled, notify, stop):
        self.source, self.enabled, self.notify, self.stop = source, enabled, notify, stop
        self.status = {"transport": "sse", "connected": False, "state": "waiting"}
        self.response = None

    def handle(self, event, data):
        if event == 'resync.required':
            self.notify('resync')
        elif event == 'project.updated':
            try:
                project = json.loads(data).get('project', {})
                if isinstance(project.get('id'), str) and project['id']:
                    self.notify('project', project['id'])
            except (ValueError, AttributeError, TypeError):
                pass

    def close(self):
        if self.response is not None:
            self.response.close()

    def run(self):
        retry = 1
        while not self.stop.is_set():
            if not self.enabled():
                self.status.update(connected=False, state='paused')
                self.stop.wait(1)
                continue
            try:
                base = self.source()
                self.status.update(connected=False, state='connecting')
                with requests.Session() as session:
                    session.trust_env = False
                    with session.get(base + '/api/events', headers={'Accept': 'text/event-stream'},
                                     stream=True, timeout=(4, 30), allow_redirects=False) as response:
                        self.response = response
                        if response.status_code != 200 or 'text/event-stream' not in response.headers.get('Content-Type', ''):
                            raise ValueError('OpenResearch SSE unavailable')
                        self.status.update(connected=True, state='connected')
                        retry = 1
                        # Subscribe before reconciliation so creations during the snapshot are queued.
                        self.notify('connected')
                        event, data = '', []
                        for raw in response.iter_lines(chunk_size=1):
                            if self.stop.is_set() or not self.enabled() or self.source() != base:
                                break
                            # Do not retain chat payloads, tool output or run logs.
                            if not raw:
                                if event in ('project.updated', 'resync.required'):
                                    self.handle(event, '\n'.join(data))
                                event, data = '', []
                            elif raw.startswith(b'event:'):
                                event = raw[6:].decode('utf-8', errors='replace').strip()
                            elif raw.startswith(b'data:') and event in ('project.updated', 'resync.required'):
                                if sum(map(len, data)) < 65536:
                                    data.append(raw[5:].decode('utf-8', errors='replace').lstrip(' '))
            except (requests.RequestException, ValueError, OSError, BridgeError):
                self.status.update(connected=False, state='reconnecting')
            finally:
                self.response = None
                self.status['connected'] = False
            if self.stop.wait(retry):
                break
            retry = min(30, retry * 2)
        self.status.update(connected=False, state='stopped')
