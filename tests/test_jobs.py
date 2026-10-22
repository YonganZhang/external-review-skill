import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import os

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'

class JobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='jobs space ')
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo with spaces'
        self.reports = self.repo / '_reports/_foreign_aid'
        self.reports.mkdir(parents=True)
        self.env = os.environ.copy()
        self.env['HOME'] = str(self.root / 'home')
        Path(self.env['HOME']).mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env['PATH'] = str(self.bin) + os.pathsep + self.env['PATH']
        self.log = self.root / 'tmux.log'
        self.env['TMUX_TEST_LOG'] = str(self.log)
        (self.bin / 'tmux').write_text('#!/bin/sh\nif [ "$1" = show-environment ]; then case "$4" in LLM_JOB_ID) echo "LLM_JOB_ID=$TMUX_TEST_JOB";; LLM_REPORT_DIR) echo "LLM_REPORT_DIR=$TMUX_TEST_DIR";; esac; exit 0; fi\nprintf "%s\\n" "$*" >> "$TMUX_TEST_LOG"\nexit 0\n')
        (self.bin / 'tmux').chmod(0o755)
    def tearDown(self):
        self.tmp.cleanup()
    def run_cli(self, script, *args):
        return subprocess.run(['bash', str(SCRIPTS / script), '--repo', str(self.repo), *args], env=self.env, capture_output=True, text=True)
    def job(self, name, state='RUNNING', status='IN_PROGRESS', result=None, session=None):
        path = self.reports / name
        path.mkdir()
        expected = 'llm_' + ''.join(c if c.isascii() and (c.isalnum() or c == '_') else '_' for c in name)
        (path / 'status.md').write_text(f'JOB_ID: {name}\nPROVIDER: codex\nSTATE: {state}\nCOMPLETION_STATUS: {status}\nTMUX_SESSION: {session or expected}\n')
        if result:
            (path / 'result.md').write_text('COMPLETION_STATUS: ' + result + '\n')
        return path
    def test_spaces_json_and_filters_before_limit(self):
        self.job('older job', 'DONE', 'COMPLETE', 'COMPLETE')
        self.job('newer job')
        (self.reports / 'reviews').mkdir()
        proc = self.run_cli('llm-jobs.sh', '--complete', '--limit', '1', '--json')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = json.loads(proc.stdout)['jobs']
        self.assertEqual([r['job_id'] for r in rows], ['older job'])
        self.assertIn('repo with spaces', rows[0]['report_dir'])
    def test_invalid_args(self):
        for script, args in [('llm-jobs.sh', ['--limit','0']), ('llm-jobs.sh',['--limit','n']), ('llm-tail.sh',['--typo']), ('llm-stall-doctor.sh',['--typo'])]:
            proc = self.run_cli(script, *args)
            self.assertEqual(proc.returncode, 2)
            self.assertTrue(proc.stderr)
    def test_traversal_and_ambiguity(self):
        self.job('foo_one')
        self.job('foo_two')
        for needle in ('../secret', '/tmp', 'foo', '..'):
            proc = self.run_cli('llm-tail.sh', '--status', needle)
            self.assertEqual(proc.returncode, 2, proc.stdout)
        proc = self.run_cli('llm-tail.sh', '--status', 'foo_one')
        self.assertEqual(proc.returncode, 0, proc.stderr)
    def test_kill_requires_exact_identity_and_does_not_source_meta(self):
        job = self.job('review_job')
        self.env['TMUX_TEST_JOB'] = job.name
        self.env['TMUX_TEST_DIR'] = str(job)
        sentinel = self.root / 'sourced'
        (job / 'meta.env').write_text(f'touch "{sentinel}"\n')
        for args in [('--kill',), ('--kill', 'review')]:
            self.assertEqual(self.run_cli('llm-tail.sh', *args).returncode, 2)
        self.assertFalse(self.log.exists())
        proc = self.run_cli('llm-tail.sh', '--kill', 'review_job')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.log.read_text().strip(), 'kill-session -t =llm_review_job')
        self.assertFalse(sentinel.exists())
        self.log.unlink()
        self.env['TMUX_TEST_JOB'] = 'unrelated'
        self.assertEqual(self.run_cli('llm-tail.sh', '--kill', 'review_job').returncode, 2)
        self.assertFalse(self.log.exists())
        self.env['TMUX_TEST_JOB'] = job.name
        with (job / 'status.md').open('a') as output:
            output.write('TMUX_SESSION: unrelated\n')
        self.assertEqual(self.run_cli('llm-tail.sh', '--kill', 'review_job').returncode, 2)
        self.assertFalse(self.log.exists())
        (job / 'status.md').write_text('JOB_ID: review_job\nTMUX_SESSION: unrelated\n')
        self.assertEqual(self.run_cli('llm-tail.sh', '--kill', 'review_job').returncode, 2)
        self.assertFalse(self.log.exists())
    def test_symlink_job_is_excluded(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'status.md').write_text('STATE: RUNNING\n')
        (self.reports / 'unsafe').symlink_to(outside, target_is_directory=True)
        proc = self.run_cli('llm-jobs.sh', '--json')
        self.assertEqual(json.loads(proc.stdout)['jobs'], [])
    def test_stall_conflict(self):
        self.job('conflict', status='COMPLETE', result='FAILED')
        proc = self.run_cli('llm-stall-doctor.sh', '--json', 'conflict')
        self.assertEqual(json.loads(proc.stdout)['classification'], 'CONFLICT')
    def test_doctor_all_is_local_and_auth_unchecked(self):
        flags = '--input-format --output-format --disable-slash-commands --model --sandbox --skip-git-repo-check --print --effort --include-partial-messages --no-session-persistence'
        for binary in ('agy', 'claude', 'codex'):
            p = self.bin / binary
            p.write_text('#!/bin/sh\ncase "$*" in "--help"|"exec --help") printf "%s\\n" "' + flags + '";; *) exit 99;; esac\n')
            p.chmod(0o755)
        # A private environment file must never execute during a doctor check.
        private = Path(self.env['HOME']) / '.config/proxy-private.env'
        private.parent.mkdir()
        private.write_text('touch "' + str(self.root / 'private-sourced') + '"\n')
        proc = subprocess.run(['bash',str(SCRIPTS / 'llm-doctor.sh'),'both','--json'], env=self.env,capture_output=True,text=True)
        data = json.loads(proc.stdout)
        self.assertEqual([p['provider'] for p in data['providers']], ['gemini','codex','claude'])
        self.assertTrue(all(p['authentication'] == 'NOT_CHECKED' for p in data['providers']))
        self.assertFalse((self.root / 'private-sourced').exists())

if __name__ == '__main__':
    unittest.main()
