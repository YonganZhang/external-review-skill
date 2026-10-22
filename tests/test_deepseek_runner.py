"""Full offline DeepSeek path through orchestrator, tmux and official JSON shape."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
TMUX = shutil.which('tmux')
FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, re, signal, sys, time
prompt = sys.stdin.read()
report = pathlib.Path(re.search(r'^Mandatory report directory:\n([^\n]+)', prompt, re.M).group(1))
patch = json.loads(pathlib.Path(sys.argv[sys.argv.index('--patch')+1]).read_text())
home = pathlib.Path(os.environ['HOME'])
(home/'fake-record.json').write_text(json.dumps({'permission': os.environ.get('DSH_PERMISSION_MODE'), 'config': patch[0]['config'], 'has_key': os.environ.get('DEEPSEEK_API_KEY') == 'synthetic-dsh-key', 'pid': os.getpid(), 'prompt': prompt}))
if 'MODE=timeout' in prompt:
 signal.signal(signal.SIGTERM, signal.SIG_IGN)
 while True: time.sleep(.1)
text = 'JOB_ID: '+report.name+'\nPROVIDER: deepseek\nCOMPLETION_STATUS: COMPLETE\nERROR_CLASS: NONE\n'
for section in ('Summary','Work Performed','Evidence','Files Changed Or Reviewed','Errors Or Blockers','Next Steps'):
 text += '## '+section+'\nSynthetic evidence.\n'
print(json.dumps({'type':'session','sessionId':'synthetic','cwd':os.getcwd()}))
print(json.dumps({'type':'status','phase':'turn_end','turn':1,'reason':{'kind':'completed'}}))
print(json.dumps({'type':'final','text':text}), flush=True)
if 'MODE=fail' in prompt:
 (report/'result.md').write_text(text)
 sys.exit(42)
'''


@unittest.skipUnless(TMUX and shutil.which('timeout'), 'requires tmux and GNU timeout')
class DeepSeekRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dsh-e2e-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root/'home'
        self.home.mkdir()
        self.repo = self.root/"repo space's"
        self.repo.mkdir()
        self.bin = self.root/'bin'
        self.bin.mkdir()
        self.socket = self.root/'tmux'
        self.socket.mkdir(mode=0o700)
        self.env = {'PATH': str(self.bin)+os.pathsep+os.defpath, 'HOME': str(self.home),
                    'USER': os.environ.get('USER', 'tester'), 'TMUX_TMPDIR': str(self.socket),
                    'LLM_SKIP_PREFLIGHT': '1', 'LLM_HEARTBEAT_SEC': '1',
                    'LLM_OUTER_GRACE_SEC': '15', 'LLM_FAILED_SESSION_TTL_SEC': '0',
                    'DEEPSEEK_API_KEY': 'synthetic-dsh-key', 'PYTHONDONTWRITEBYTECODE': '1'}
        (self.bin/'dsh').write_text(FAKE)
        (self.bin/'dsh').chmod(0o700)
        # Record tmux's actual public argv, then delegate to a private real server.
        (self.bin/'tmux').write_text('#!'+sys.executable+'\nimport json, os, pathlib, sys\n'
            "with (pathlib.Path(os.environ['HOME'])/'tmux-argv.jsonl').open('a') as stream: stream.write(json.dumps(sys.argv[1:])+'\\n')\n"
            'os.execv('+repr(TMUX)+', ['+repr(TMUX)+', *sys.argv[1:]])\n')
        (self.bin/'tmux').chmod(0o700)
        self.addCleanup(self.stop_server)

    def stop_server(self):
        record_path = self.home/'fake-record.json'
        if record_path.exists():
            pid = json.loads(record_path.read_text())['pid']
            cmdline = Path('/proc')/str(pid)/'cmdline'
            if cmdline.exists() and str(self.bin/'dsh').encode() in cmdline.read_bytes().split(b'\0'):
                os.kill(pid, signal.SIGKILL)
        subprocess.run([TMUX, 'kill-server'], env=self.env, capture_output=True)

    def run_review(self, flags=(), mode='ok', timeout=20, overrides=None):
        packet = self.root/'review packet.md'
        packet.write_text('Synthetic scope MODE='+mode+'\n')
        proc = subprocess.run([sys.executable, str(SCRIPTS/'external-review.py'), '--repo', str(self.repo),
            '--host', 'codex', '--providers', 'deepseek', '--prompt-file', str(packet),
            '--timeout', str(timeout), '--json', *flags], env={**self.env, **(overrides or {})},
            capture_output=True, text=True, timeout=45)
        self.assertTrue(proc.stdout.strip(), proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(len(result['results']), 1)
        return proc, result, result['results'][0]

    def record(self):
        return json.loads((self.home/'fake-record.json').read_text())

    def test_full_success_native_key_isolation(self):
        proc, batch, job = self.run_review()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(batch['status'], 'COMPLETE')
        self.assertEqual(job['status'], 'COMPLETE')
        self.assertEqual(job['provider'], 'deepseek')
        record = self.record()
        self.assertEqual(record['permission'], 'workspace-write')
        self.assertEqual(record['config']['model'], 'deepseek-flash')
        self.assertEqual(record['config']['reasoningEffort'], 'low')
        self.assertTrue(record['has_key'])
        self.assertIn('Synthetic scope', record['prompt'])
        report = Path(job['report_dir'])
        self.assertIn('PROVIDER: deepseek', (report/'result.md').read_text())
        self.assertNotIn('synthetic-dsh-key', (self.home/'tmux-argv.jsonl').read_text())
        for path in report.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'synthetic-dsh-key', path.read_bytes(), str(path))

    def test_nonzero_cannot_be_masked_by_valid_report(self):
        proc, batch, job = self.run_review(mode='fail')
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotEqual(batch['status'], 'COMPLETE')
        self.assertEqual(job['status'], 'FAILED')
        self.assertNotEqual(job['exit_code'], 0)

    def test_bypass_and_explicit_model(self):
        proc, _, _ = self.run_review(('--permission-mode', 'bypass', '--model', 'deepseek=deepseek-v4-pro'))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.record()['permission'], 'danger-full-access')
        self.assertEqual(self.record()['config']['model'], 'deepseek-v4-pro')

    def test_effort_modes_and_environment_override(self):
        for flags, effort, overrides in [(('--deep',), 'high', {}), (('--gate',), 'high', {}),
                (('--gate',), 'off', {'LLM_DEEPSEEK_EFFORT': 'off', 'LLM_DEEPSEEK_MODEL': 'deepseek-v4-pro'})]:
            with self.subTest(flags=flags, effort=effort):
                proc, _, _ = self.run_review(flags, overrides=overrides)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(self.record()['config']['reasoningEffort'], effort)
                if overrides:
                    self.assertEqual(self.record()['config']['model'], 'deepseek-v4-pro')

    def test_timeout_kills_provider_process(self):
        proc, _, job = self.run_review(mode='timeout', timeout=1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(job['status'], 'FAILED')
        pid = self.record()['pid']
        # Killed processes may briefly remain as zombies until adopted/reaped.
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            status = Path('/proc')/str(pid)/'stat'
            if not status.exists() or status.read_text().split()[2] == 'Z':
                break
            time.sleep(.05)
        else:
            self.fail('timed-out dsh remains alive')


if __name__ == '__main__':
    unittest.main()
