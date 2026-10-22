"""Synthetic orchestrator tests: no provider or network access."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/external-review.py"
spec = importlib.util.spec_from_file_location("external_review", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReviewTests(unittest.TestCase):
    def test_selection(self):
        self.assertEqual(module.select_providers("codex", None), ["claude", "gemini"])
        self.assertEqual(module.select_providers("claude", None), ["codex", "gemini"])
        self.assertEqual(module.select_providers("unknown", "gemini"), ["gemini"])
        for host, names in [("unknown", None), ("codex", "codex"), ("claude", "gemini,gemini"), ("claude", "bogus")]:
            with self.assertRaises(ValueError):
                module.select_providers(host, names)

    def test_round_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "copied scripts"
            scripts.mkdir()
            (scripts / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
            repo = root / "research project"
            repo.mkdir()
            packet = root / "packet.md"
            packet.write_text("Synthetic review input\n")
            stub = '''#!/usr/bin/env python3
import json,os,pathlib,sys,time
args=sys.argv[1:]; repo=pathlib.Path(args[args.index('--repo')+1]); name=pathlib.Path(__file__).stem.split('-')[0]
marker=repo/(name+'.started');marker.touch()
other=repo/(('gemini' if name=='claude' else 'claude')+'.started')
deadline=time.monotonic()+5
while not other.exists() and time.monotonic()<deadline:time.sleep(.01)
assert other.exists(), 'reviewers were not launched concurrently'
packet=pathlib.Path(args[args.index('--prompt-file')+1]).read_text()
assert packet.endswith('Synthetic review input\\n') and 'Do not modify project' in packet
job='synthetic__'+name+'__1'; report=repo/'_reports/_foreign_aid'/job; report.mkdir(exist_ok=True)
(report/'result.md').write_text('Synthetic '+name+' report')
rc=3 if os.environ.get('SYNTHETIC_FAIL')==name else 0
print(json.dumps({'job_id':job,'provider':name,'report_dir':str(report),'status':'COMPLETE' if rc==0 else 'FAILED','exit_code':rc}))
sys.exit(rc)
'''
            for name in ["claude", "gemini"]:
                backend = scripts / f"{name}.py"
                backend.write_text(stub)
                (scripts / f"{name}-ask.sh").write_text(f'#!/bin/bash\nexec "{sys.executable}" "{backend}" "$@"\n')
            env = {"PATH": os.defpath, "HOME": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
            command = [sys.executable, str(scripts / SCRIPT.name), "--repo", str(repo), "--host", "codex", "--prompt-file", str(packet), "--json"]
            preview = subprocess.run([*command, "--dry-run"], env=env, capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertFalse((repo / "_reports").exists())
            completed = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(len(result["results"]), 2)
            first_report = Path(result["batch_dir"]) / "summary.json"
            self.assertEqual(json.loads(first_report.read_text()), result)
            partial = subprocess.run(command, env={**env, "SYNTHETIC_FAIL": "gemini"}, capture_output=True, text=True)
            self.assertEqual(partial.returncode, 1, partial.stderr)
            result2 = json.loads(partial.stdout)
            self.assertEqual(result2["status"], "PARTIAL")
            self.assertEqual(result2["completed_providers"], ["claude"])
            self.assertEqual(result2["failed_providers"], ["gemini"])
            self.assertNotEqual(result["batch_id"], result2["batch_id"])
            self.assertEqual(json.loads(first_report.read_text()), result)


if __name__ == "__main__":
    unittest.main()
