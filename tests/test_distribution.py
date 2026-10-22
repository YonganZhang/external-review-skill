"""Build, extract and install synthetic copies; never modify the source package."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_reproducible_archive_install_and_tamper(self):
        with tempfile.TemporaryDirectory(prefix='release space ') as temp:
            root = Path(temp)
            source = root / 'source'
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('__pycache__', '.git', '*.pyc'))
            archives = [root / 'first.zip', root / 'second.zip']
            for archive in archives:
                result = subprocess.run([sys.executable, str(source / 'release.py'), '--out', str(archive)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertGreater(json.loads(result.stdout)['files'], 20)
            self.assertEqual(archives[0].read_bytes(), archives[1].read_bytes())
            with zipfile.ZipFile(archives[0]) as archive:
                self.assertTrue(all(name.startswith('share-external-llm/') for name in archive.namelist()))
                archive.extractall(root / 'unpacked')
            unpacked = root / 'unpacked/share-external-llm'
            project = root / "teacher's project"
            project.mkdir()
            command = [sys.executable, str(unpacked / 'install.py'), '--project', str(project)]
            preview = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertEqual(list(project.iterdir()), [])
            installed = subprocess.run([*command, '--apply'], capture_output=True, text=True)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            repeat = subprocess.run([*command, '--apply'], capture_output=True, text=True)
            self.assertEqual(repeat.returncode, 0, repeat.stderr)
            self.assertEqual(repeat.stdout.count('Already installed'), 2)
            codex = project / '.agents/skills/share-external-llm'
            claude = project / '.claude/skills/share-external-llm'
            self.assertEqual((codex / 'SKILL.md').read_bytes(), (claude / 'SKILL.md').read_bytes())
            help_result = subprocess.run([sys.executable, str(codex / 'scripts/external-review.py'), '--help'], capture_output=True, text=True)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            (codex / 'SKILL.md').write_text('Locally customized skill')
            conflict = subprocess.run([*command, '--apply'], capture_output=True, text=True)
            self.assertEqual(conflict.returncode, 1)
            self.assertEqual((codex / 'SKILL.md').read_text(), 'Locally customized skill')
            (unpacked / 'scripts/external-review.py').write_text('Changed after release')
            tampered = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(tampered.returncode, 1)
            self.assertIn('checksum mismatch', tampered.stderr)

    def test_unlisted_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('__pycache__', '.git', '*.pyc'))
            (source / 'private-notes.txt').write_text('Synthetic excluded material')
            archive = root / 'release.zip'
            result = subprocess.run([sys.executable, str(source / 'release.py'), '--out', str(archive)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(archive.exists())


if __name__ == '__main__':
    unittest.main()
