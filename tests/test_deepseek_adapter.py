"""Synthetic dsh contract tests; no provider calls or real credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ADAPTER = Path(__file__).resolve().parents[1] / 'scripts' / 'deepseek-run.py'


class DeepSeekAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dsh adapter ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo with spaces'
        self.repo.mkdir()
        self.report = self.root / 'job-test'
        self.prompt = self.root / 'prompt with spaces.txt'
        self.prompt.write_text('test stdin\nwith literal $(echo danger)\n')
        self.binary = self.root / 'fake dsh'
        self.binary.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
patch = pathlib.Path(sys.argv[sys.argv.index('--patch')+1])
record = {'argv': sys.argv[1:], 'patch': json.loads(patch.read_text()), 'stdin': sys.stdin.read(), 'cwd': os.getcwd(), 'permission': os.environ['DSH_PERMISSION_MODE'], 'key': os.environ.get('DEEPSEEK_API_KEY'), 'unrelated': os.environ.get('OPENAI_API_KEY'), 'base': os.environ.get('DEEPSEEK_BASE_URL'), 'home': os.environ['DSH_HOME']}
pathlib.Path(os.environ['FAKE_RECORD']).write_text(json.dumps(record))
if os.environ.get('FAKE_REPORT'):
 pathlib.Path(os.environ['FAKE_RESULT_PATH']).write_text(os.environ['FAKE_REPORT'])
print(os.environ['FAKE_EVENTS'])
sys.exit(int(os.environ.get('FAKE_RC', '0')))
''')
        self.binary.chmod(0o700)
        self.text = 'JOB_ID: job-test\nPROVIDER: deepseek\nCOMPLETION_STATUS: COMPLETE\nERROR_CLASS: NONE\n' + ''.join('## '+s+'\nVerified.\n' for s in ('Summary', 'Work Performed', 'Evidence', 'Files Changed Or Reviewed', 'Errors Or Blockers', 'Next Steps'))
        self.events = [{'type': 'session'}, {'type': 'status', 'phase': 'turn_end', 'reason': {'kind': 'completed'}}, {'type': 'final', 'text': self.text}]

    def run_adapter(self, extra=(), **env):
        child_env = {**os.environ, 'FAKE_RECORD': str(self.root/'record.json'),
                     'FAKE_RESULT_PATH': str(self.report/'result.md'),
                     'FAKE_EVENTS': '\n'.join(json.dumps(e) for e in self.events), **env}
        return subprocess.run([sys.executable, str(ADAPTER), '--bin', str(self.binary), '--repo', str(self.repo), '--prompt-file', str(self.prompt), '--report-dir', str(self.report), *extra], env=child_env, capture_output=True, text=True)

    def test_native_stdin_patch_and_isolation(self):
        proc = self.run_adapter(OPENAI_API_KEY='irrelevant', DEEPSEEK_BASE_URL='https://bad')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        record = json.loads((self.root/'record.json').read_text())
        self.assertEqual(record['stdin'], self.prompt.read_text())
        self.assertEqual(record['permission'], 'workspace-write')
        self.assertEqual(record['argv'][-2:], ['--json', '-'])
        self.assertEqual(record['patch'][0]['config'], {'provider': 'deepseek-official', 'model': 'deepseek-flash', 'reasoningEffort': 'low'})
        self.assertIsNone(record['unrelated'])
        self.assertIsNone(record['base'])
        self.assertTrue(Path(record['home']).is_relative_to(self.report))
        self.assertEqual((self.report/'result.md').read_text(), self.text)
        self.assertEqual(proc.stdout, '')

    def test_bypass_key_file_cleanup(self):
        key = self.root/'secret'
        key.write_text('synthetic-secret-42\n')
        proc = self.run_adapter(('--permission-mode', 'bypass', '--key-file', str(key), '--model', 'deepseek-v4-pro', '--effort', 'max'))
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(key.exists())
        record = json.loads((self.root/'record.json').read_text())
        self.assertEqual(record['key'], 'synthetic-secret-42')
        self.assertEqual(record['permission'], 'danger-full-access')
        self.assertEqual(record['patch'][0]['config']['reasoningEffort'], 'max')
        self.assertNotIn('synthetic-secret-42', json.dumps(record['argv']) + json.dumps(record['patch']) + proc.stderr)
        for path in self.report.rglob('*'):
            if path.is_file():
                self.assertNotIn('synthetic-secret-42', path.read_text())

    def test_direct_key_env_forwarded_and_job_home_unique(self):
        self.assertEqual(self.run_adapter(DEEPSEEK_API_KEY='synthetic-direct').returncode, 0)
        first = json.loads((self.root/'record.json').read_text())
        self.assertEqual(first['key'], 'synthetic-direct')
        self.assertEqual(self.run_adapter(DEEPSEEK_API_KEY='synthetic-direct').returncode, 0)
        second = json.loads((self.root/'record.json').read_text())
        self.assertNotEqual(first['home'], second['home'])

    def test_empty_tmux_key_does_not_hide_official_dotenv_fallback(self):
        self.assertEqual(self.run_adapter(DEEPSEEK_API_KEY='').returncode, 0)
        record = json.loads((self.root/'record.json').read_text())
        self.assertIsNone(record['key'])

    def test_reject_bad_options(self):
        for option, value in (('--model', 'other-model'), ('--effort', 'medium')):
            with self.subTest(option=option):
                self.assertEqual(self.run_adapter((option, value)).returncode, 2)

    def test_failed_process_cannot_be_masked_by_report(self):
        proc = self.run_adapter(FAKE_RC='1', FAKE_REPORT=self.text)
        self.assertEqual(proc.returncode, 1)

    def test_invalid_streams(self):
        variants = [[], self.events[:-1], self.events+[self.events[-1]],
                    [self.events[0], {'type': 'error', 'message': 'private'}, self.events[-1]],
                    [self.events[0], {'type': 'status', 'phase': 'turn_end', 'reason': {'kind': 'error'}}, self.events[-1]],
                    [self.events[0], self.events[1], {'type': 'final', 'text': ''}]]
        for events in variants:
            with self.subTest(events=events):
                self.events = events
                self.assertEqual(self.run_adapter(FAKE_REPORT=self.text).returncode, 1)
        self.assertEqual(self.run_adapter(FAKE_EVENTS='not json').returncode, 1)

    def test_invalid_final_preserved(self):
        self.events[-1]['text'] = 'Incomplete answer'
        self.assertEqual(self.run_adapter().returncode, 1)
        self.assertEqual((self.report/'deepseek-final.txt').read_text(), 'Incomplete answer')
        self.assertFalse((self.report/'result.md').exists())

    def test_valid_written_report_not_overwritten(self):
        self.events[-1]['text'] = 'Done; report written.'
        self.assertEqual(self.run_adapter(FAKE_REPORT=self.text).returncode, 0)
        self.assertEqual((self.report/'result.md').read_text(), self.text)

    def test_key_cleaned_even_when_launch_validation_fails(self):
        key = self.root/'secret'
        key.write_text('synthetic-secret')
        self.binary.unlink()
        self.assertEqual(self.run_adapter(('--key-file', str(key))).returncode, 1)
        self.assertFalse(key.exists())


if __name__ == '__main__':
    unittest.main()
