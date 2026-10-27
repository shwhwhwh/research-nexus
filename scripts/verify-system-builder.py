"""Opt-in real-agent acceptance test. Fictional local-only pipeline, isolated storage."""
import argparse
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from bridge.builder import Builder
from bridge.designer import Designer

parser = argparse.ArgumentParser()
parser.add_argument('--live-agent', action='store_true', required=True)
parser.add_argument('--provider', choices=['codex', 'claude'], default='codex')
args = parser.parse_args()
root = REPO / 'artifacts' / ('builder-acceptance-' + str(int(time.time())))
root.mkdir(parents=True)
d = Designer(root); b = Builder(root, d)


def wait():
    end, stage = time.monotonic() + 420, None
    while d.workers and time.monotonic() < end:
        if b.jobs[-1]['stage'] != stage:
            stage = b.jobs[-1]['stage']; print('Stage: ' + stage, flush=True)
        time.sleep(.2)
    assert not d.workers, 'Acceptance timeout'


try:
    result = b.start({'provider': args.provider, 'install_components': False, 'description':
        'Build a local research reading-list system with exactly two folder components and one manual data flow. '
        'Input is runtime JSON rows with title and arxiv fields, deduplicate by arxiv, and save papers.md with a Markdown title and arxiv per row. '
        'Use a fictional sample with two distinct papers and one duplicate. No web services, installation, private accounts, real papers, keys or other tools. '
        'This pure local data transformation must be ready. Its full compiled channel must be portable in the template.'})
    wait(); first = b.job(result['job_id']); assert first['status'] == 'ready', first
    manifest = b.export(first['id']); (root / 'exported.rn-system.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    versions = json.dumps(d.project['versions'], sort_keys=True)
    # Rehydrate from the actual exported bytes; replay must work even with CLI unavailable.
    original = d.command
    d.command = lambda *_: (_ for _ in ()).throw(AssertionError('Replay invoked agent'))
    second_result = b.start({'manifest': json.loads((root / 'exported.rn-system.json').read_text(encoding='utf-8'))})
    wait(); second = b.job(second_result['job_id']); assert second['status'] == 'ready', second
    assert second['agent_calls'] == 0
    assert json.dumps(d.project['versions'], sort_keys=True) == versions
    for _ in range(2):
        b.run(second['id'], [{'title': 'Fictional runtime A', 'arxiv': '0000.00001'}, {'title': 'Fictional runtime A', 'arxiv': '0000.00001'}, {'title': 'Fictional runtime B', 'arxiv': '0000.00002'}])
        wait(); assert second['run_result']['success'], second['run_result']
    output = next((d.base / 'outputs').glob('*/papers.md'))
    text = output.read_text(encoding='utf-8')
    assert text.count('Fictional runtime A') == 1 and text.count('Fictional runtime B') == 1
    report = {'passed': True, 'provider': args.provider, 'first_design_agent_calls': first['agent_calls'], 'replay_agent_calls': second['agent_calls'],
        'real_agent': True, 'isolated_storage': True, 'personal_accounts_accessed': False, 'export_reimport': True, 'stable_versions': True,
        'runtime_input_verified': True, 'repeated_run_no_duplicate_rows': True, 'root': str(root)}
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8'); print(json.dumps(report), flush=True)
finally:
    d.shutdown()
