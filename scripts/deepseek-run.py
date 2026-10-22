#!/usr/bin/env python3
"""Run one official dsh headless task; success requires a strict report."""
import argparse
import importlib.util
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile


def parser():
    p = argparse.ArgumentParser(description=__doc__, epilog='Example: deepseek-run.py --bin /opt/bin/dsh --repo . --prompt-file prompt.txt --report-dir reports/job-1')
    p.add_argument('--bin', required=True)
    p.add_argument('--repo', required=True)
    p.add_argument('--prompt-file', required=True)
    p.add_argument('--report-dir', required=True)
    p.add_argument('--model', choices=('deepseek-flash', 'deepseek-v4-pro'), default='deepseek-flash')
    p.add_argument('--effort', choices=('off', 'low', 'high', 'max'), default='low')
    p.add_argument('--permission-mode', choices=('native', 'bypass'), default='native')
    p.add_argument('--key-file')
    return p


def validate_report(path, job):
    spec = importlib.util.spec_from_file_location('llm_report', Path(__file__).with_name('llm-report.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate(path, job, 'deepseek')


def parse_stream(path):
    events = []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            event = json.loads(line)
            if not isinstance(event, dict) or not isinstance(event.get('type'), str):
                raise ValueError('invalid event')
            events.append(event)
    finals = [event for event in events if event['type'] == 'final']
    if len(finals) == 1 and isinstance(finals[0].get('text'), str):
        path.with_name('deepseek-final.txt').write_text(finals[0]['text'], encoding='utf-8')
    if (not events or events[0]['type'] != 'session' or len(finals) != 1
            or events[-1]['type'] != 'final' or any(e['type'] == 'error' for e in events)):
        raise ValueError('incomplete or failed stream')
    final = finals[0].get('text')
    if not isinstance(final, str) or not final.strip():
        raise ValueError('missing final text')
    ends = [e for e in events if e['type'] == 'status' and e.get('phase') == 'turn_end']
    if not ends or ends[-1].get('reason') != {'kind': 'completed'}:
        raise ValueError('turn did not complete')
    return final


def run(args):
    key = None
    if args.key_file:
        key_path = Path(args.key_file)
        try:
            key = key_path.read_text(encoding='utf-8').strip()
        finally:
            key_path.unlink(missing_ok=True)
        if not key:
            raise ValueError('empty key file')
    binary = Path(args.bin)
    if not binary.is_absolute() or not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('dsh binary must be an absolute executable path')
    repo = Path(args.repo).resolve(strict=True)
    if not repo.is_dir():
        raise ValueError('repository must be a directory')
    prompt = Path(args.prompt_file).read_bytes()
    if not prompt.strip():
        raise ValueError('empty prompt')
    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(report_dir, 0o700)
    home = Path(tempfile.mkdtemp(prefix='deepseek-home-', dir=report_dir))
    patch = home / 'job.patch.json'
    patch.write_text(json.dumps([{'id': 'agent-default-model', 'config': {
        'provider': 'deepseek-official', 'model': args.model, 'reasoningEffort': args.effort}}]), encoding='utf-8')
    env = dict(os.environ)
    for name in list(env):
        if name == 'DEEPSEEK_BASE_URL' or (name.endswith(('_API_KEY', '_AUTH_TOKEN')) and name != 'DEEPSEEK_API_KEY'):
            del env[name]
    if not env.get('DEEPSEEK_API_KEY'):
        env.pop('DEEPSEEK_API_KEY', None)
    if key is not None:
        env['DEEPSEEK_API_KEY'] = key
    env['DSH_HOME'] = str(home)
    env['DSH_PERMISSION_MODE'] = 'workspace-write' if args.permission_mode == 'native' else 'danger-full-access'
    events_path = report_dir / 'deepseek-events.jsonl'
    # GNU timeout sends TERM to this whole process group. Keep the supervisor
    # waiting so timeout's kill-after can reap a child that ignores TERM.
    previous_term = signal.signal(signal.SIGTERM, lambda _signal, _frame: None)
    try:
        with events_path.open('wb') as stdout, (report_dir / 'deepseek-stderr.log').open('wb') as stderr:
            process = subprocess.run([str(binary), '--profile', 'headless', '--patch', str(patch), '--json', '-'],
                                     cwd=repo, env=env, input=prompt, stdout=stdout, stderr=stderr, check=False)
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    (report_dir / "deepseek-exit-code.txt").write_text(str(process.returncode) + "\n")
    final = parse_stream(events_path)
    # Preserve the actual answer even if the process failed or report is invalid.
    final_path = report_dir / 'deepseek-final.txt'
    final_path.write_text(final, encoding='utf-8')
    if process.returncode:
        raise ValueError('dsh process failed')
    result = report_dir / 'result.md'
    if not validate_report(result, report_dir.name):
        if not validate_report(final_path, report_dir.name):
            raise ValueError('no valid final report')
        result.write_text(final, encoding='utf-8')
    return 0


def main():
    args = parser().parse_args()
    try:
        return run(args)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        # Never echo child output, credentials, prompts, paths or exception text.
        print('deepseek adapter: execution or report validation failed; inspect job artifacts', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
