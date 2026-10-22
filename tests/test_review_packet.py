from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/llm-review-packet.sh'

class PacketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Synthetic Test')
    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True).stdout.decode().strip()
    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'synthetic')
        return self.git('rev-parse', 'HEAD')
    def packet(self, *args):
        return subprocess.run([str(SCRIPT), '--repo', str(self.root), *args], capture_output=True, text=True)
    def test_baseline_staged_unstaged(self):
        self.write('a', 'initial\n')
        base = self.commit()
        self.write('a', 'committed\n')
        self.commit()
        self.write('a', 'staged\n')
        self.git('add', 'a')
        result = self.packet('--base', base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('-initial', result.stdout)
        self.assertIn('+staged', result.stdout)
        self.write('a', 'unstaged\n')
        result = self.packet()
        self.assertIn('-committed', result.stdout)
        self.assertIn('+unstaged', result.stdout)
    def test_unborn_literal_path(self):
        name = "teacher's file.py"
        self.write(name, 'synthetic\n')
        self.git('add', name)
        result = self.packet('--path', name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('+synthetic', result.stdout)
    def test_output_preservation(self):
        self.write('packet.md', 'preserve')
        out = self.root / 'packet.md'
        self.assertEqual(self.packet('--out', str(out)).returncode, 1)
        self.assertEqual(out.read_text(), 'preserve')
        self.assertEqual(self.packet('--out', str(out), '--force').returncode, 0)
        self.assertNotIn('###', out.read_text())
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
    def test_credentials_safe_names_and_reports(self):
        self.write('keyboard.py', 'SAFE KEYBOARD')
        self.write('tokenizer.py', 'SAFE TOKENIZER')
        self.write('config.py', 'api_key = "sk-' + 'z' * 24 + '"')
        self.write('.env', 'SECRET PRIVATE')
        self.write('_reports/report.md', 'REPORT PRIVATE')
        self.git('add', '.')
        result = self.packet()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SAFE KEYBOARD', result.stdout)
        self.assertIn('SAFE TOKENIZER', result.stdout)
        for forbidden in ['z' * 24, 'SECRET PRIVATE', 'REPORT PRIVATE']:
            self.assertNotIn(forbidden, result.stdout)
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as outside:
            source = Path(outside) / 'private'
            source.write_text('OUTSIDE PRIVATE')
            (self.root / 'link').symlink_to(source)
            result = self.packet()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('OUTSIDE PRIVATE', result.stdout)
            self.assertIn('symlink', result.stdout)
    def test_total_budget(self):
        self.write('a', 'x' * 60)
        self.write('b', 'y' * 60)
        result = self.packet('--max-diff-chars', '70')
        self.assertIn('x' * 60, result.stdout)
        self.assertNotIn('y' * 11, result.stdout)
        self.assertIn('truncated', result.stdout)
    def test_errors(self):
        self.assertEqual(self.packet('--base', 'missing-revision').returncode, 1)
        result = subprocess.run([str(SCRIPT), '--repo', str(self.root.parent)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('fatal:', result.stderr)
        self.assertEqual(self.packet('--unknown').returncode, 2)
    def test_git_failure_preserves_output(self):
        self.write('a', 'initial')
        self.commit()
        self.write('packet.md', 'PRESERVE')
        (self.root / '.git/index').write_bytes(b'corrupt index')
        result = self.packet('--out', str(self.root / 'packet.md'), '--force')
        self.assertEqual(result.returncode, 1)
        self.assertEqual((self.root / 'packet.md').read_text(), 'PRESERVE')
        self.assertNotIn('fatal:', result.stderr)
    def test_legacy_paths(self):
        self.write('one', 'FIRST')
        self.write('two', 'SECOND')
        self.write('three', 'THIRD')
        result = self.packet('--paths', 'one two')
        self.assertIn('FIRST', result.stdout)
        self.assertIn('SECOND', result.stdout)
        self.assertNotIn('THIRD', result.stdout)

if __name__ == '__main__':
    unittest.main()
