#!/usr/bin/env python3
"""Read project-local external review artifacts; never source job metadata."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def fields(path):
    result = {}
    if path.is_symlink():
        return result
    try:
        for line in path.read_text(errors='replace').splitlines():
            match = re.match(r'^([A-Z_]+):\s*(.*)$', line)
            if match and match[1] not in result:
                result[match[1]] = match[2]
    except FileNotFoundError:
        pass
    return result


def jobs(repo):
    raw_root = repo / '_reports' / '_foreign_aid'
    root = raw_root.resolve()
    if not root.is_relative_to(repo) or raw_root.is_symlink():
        raise ValueError('report root must remain within the repository')
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                   and p.resolve().parent == root and (p / 'status.md').is_file() and not (p / 'status.md').is_symlink()), key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)


def choose(repo, needle, exact=False):
    if needle and (needle in {'.', '..'} or '/' in needle or '\\' in needle):
        raise ValueError('job-id must be a directory name, without path components')
    candidates = jobs(repo)
    if not needle:
        if exact:
            raise ValueError('--kill requires an explicit exact job-id')
        matches = candidates[:1]
    else:
        matches = [p for p in candidates if p.name == needle]
        if not matches and not exact:
            matches = [p for p in candidates if needle in p.name]
    if not matches:
        raise ValueError('no matching foreign-aid job')
    if len(matches) != 1:
        raise ValueError('ambiguous job-id; use an exact name')
    return matches[0]


def info(path):
    status, result = fields(path / 'status.md'), fields(path / 'result.md')
    sc, rc = status.get('COMPLETION_STATUS', ''), result.get('COMPLETION_STATUS', '')
    completion = rc or sc or 'UNKNOWN'
    conflict = bool(sc and rc and sc != rc and 'COMPLETE' in {sc, rc})
    if conflict:
        completion = f'CONFLICT:{sc}/{rc}'
    return dict(job_id=path.name, provider=status.get('PROVIDER', ''),
                state=status.get('STATE', ''), completion=completion,
                status_completion=sc, result_completion=rc,
                detail=status.get('DETAIL', ''), report_dir=str(path),
                tmux_session=status.get('TMUX_SESSION', ''))


def session_for(path):
    data = fields(path / 'status.md')
    text = (path / 'status.md').read_text(errors='replace')
    if any(len(re.findall(r'^' + key + r':.*$', text, re.M)) != 1 for key in ('JOB_ID', 'TMUX_SESSION')):
        raise ValueError('duplicate or missing job identity fields')
    expected = 'llm_' + re.sub(r'[^A-Za-z0-9_]', '_', path.name)
    if data.get('JOB_ID') != path.name or data.get('TMUX_SESSION') != expected:
        raise ValueError('job identity or tmux session mismatch; refusing tmux action')
    return expected


def tmux(args):
    try:
        return subprocess.run(['tmux', *args], check=False)
    except FileNotFoundError:
        raise ValueError('tmux is not installed')


def doctor(args):
    selected = ['gemini', 'codex', 'claude', 'deepseek'] if args.provider == 'all' else (['gemini', 'codex', 'claude'] if args.provider == 'both' else [args.provider])
    checks = []
    def add(name, ok, detail):
        checks.append(dict(name=name, ok=ok, detail=detail))
    for tool in ('bash', 'tmux', 'timeout', 'stat', 'sort', 'find', 'python3'):
        add(tool, bool(shutil.which(tool)), shutil.which(tool) or 'not found')
    for binary, flag, marker in [('bash', '--version', 'GNU bash'), ('timeout', '--version', 'GNU coreutils'), ('stat', '--version', 'GNU coreutils'), ('sort', '--version', 'GNU coreutils'), ('find', '--version', 'GNU findutils')]:
        if shutil.which(binary):
            try:
                proc = subprocess.run([binary, flag], capture_output=True, text=True, timeout=5)
                compatible = marker in proc.stdout
                if binary == 'bash':
                    version = re.search(r'version (\d+)', proc.stdout)
                    compatible = compatible and bool(version and int(version[1]) >= 4)
                add(binary + '_compatibility', compatible, 'local version check')
            except (OSError, subprocess.TimeoutExpired):
                add(binary + '_compatibility', False, 'version check failed')
    add('python_version', sys.version_info >= (3, 10), sys.version.split()[0])
    script_dir = Path(__file__).resolve().parent
    for name in ('llm-tmux-run.sh', *[p + '-ask.sh' for p in selected]):
        p = script_dir / name
        add(name, p.is_file() and os.access(p, os.X_OK), str(p))
    providers = []
    specs = {'deepseek': ('dsh', ['--profile', 'headless', '--help'], ['--json', '--session-id']),
             'gemini': ('agy', ['--help'], ['--input-format', '--output-format', '--disable-slash-commands']),
             'codex': ('codex', ['exec', '--help'], ['--model', '--sandbox', '--skip-git-repo-check']),
             'claude': ('claude', ['--help'], ['--print', '--model', '--effort', '--output-format', '--include-partial-messages', '--no-session-persistence'])}
    for provider in selected:
        binary, help_args, required = specs[provider]
        executable = shutil.which(binary)
        row = dict(provider=provider, executable=executable, authentication='NOT_CHECKED', network='NOT_CHECKED', missing_flags=required[:])
        if executable:
            try:
                proc = subprocess.run([executable, *help_args], capture_output=True, text=True, timeout=45 if provider == 'deepseek' else 10)
                output = proc.stdout + proc.stderr
                row['missing_flags'] = [flag for flag in required if flag not in output]
                row['help_exit_code'] = proc.returncode
                row['ok'] = proc.returncode == 0 and not row['missing_flags']
            except (OSError, subprocess.TimeoutExpired) as exc:
                row['ok'] = False
                row['error'] = str(exc)
        else:
            row['ok'] = False
        providers.append(row)
    payload = dict(ok=all(c['ok'] for c in checks) and all(p['ok'] for p in providers),
                   checks=checks, providers=providers, scope='local executable and help checks only; authentication and network are not verified')
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for c in checks:
            print(f"{'OK' if c['ok'] else 'MISSING'} {c['name']}: {c['detail']}")
        for p in providers:
            print(f"{p['provider']}: {'OK' if p['ok'] else 'CHECK_FAILED'} missing_flags={','.join(p['missing_flags']) or 'none'}; auth=NOT_CHECKED network=NOT_CHECKED")
        print(payload['scope'])
    return 0 if payload['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('jobs', 'tail', 'stall'):
        p = sub.add_parser(name)
        p.add_argument('--repo', type=Path)
        if name != 'tail':
            p.add_argument('--json', action='store_true')
        if name == 'jobs':
            group = p.add_mutually_exclusive_group()
            for flag in ('running', 'errors', 'complete'):
                group.add_argument('--' + flag, action='store_true')
            p.add_argument('--limit', type=int, default=20)
        else:
            p.add_argument('job_id', nargs='?' if name == 'tail' else None)
            if name == 'tail':
                group = p.add_mutually_exclusive_group()
                for flag in ('status', 'progress', 'result', 'pane', 'events', 'meta', 'prompt', 'attach', 'kill'):
                    group.add_argument('--' + flag, dest='mode', action='store_const', const=flag)
                group.add_argument('--last', dest='mode', action='store_const', const='result')
    p = sub.add_parser('doctor')
    p.add_argument('provider', nargs='?', default='all', choices=['all', 'both', 'gemini', 'codex', 'claude', 'deepseek'])
    p.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.command == 'doctor':
        return doctor(args)
    repo = args.repo
    if repo is None:
        proc = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        repo = Path(proc.stdout.strip()) if proc.returncode == 0 else Path.cwd()
    repo = repo.resolve(strict=True)
    if not repo.is_dir():
        raise ValueError('--repo must be a directory')
    if args.command == 'jobs':
        if args.limit < 1:
            parser.error('--limit must be a positive integer')
        rows = [info(p) for p in jobs(repo)]
        if args.running:
            rows = [r for r in rows if r['status_completion'] == 'IN_PROGRESS' or r['state'].startswith('RUNNING')]
        if args.errors:
            rows = [r for r in rows if r['completion'].startswith('CONFLICT:') or {r['status_completion'], r['result_completion'], r['state']} & {'FAILED', 'BLOCKED', 'INCOMPLETE'}]
        if args.complete:
            rows = [r for r in rows if r['status_completion'] == r['result_completion'] == 'COMPLETE']
        rows = rows[:args.limit]
        if args.json:
            print(json.dumps(dict(jobs=rows), ensure_ascii=False))
        else:
            print('JOB\tPROVIDER\tSTATE\tCOMPLETION\tDETAIL')
            for r in rows:
                print('\t'.join(r[k].replace('\t', ' ') for k in ('job_id', 'provider', 'state', 'completion', 'detail')))
        return 0
    mode = getattr(args, 'mode', None) or 'pane'
    path = choose(repo, args.job_id, exact=mode == 'kill' and args.command == 'tail')
    if args.command == 'tail':
        if mode in {'kill', 'attach'}:
            session = session_for(path)
            for key, expected in [('LLM_JOB_ID', path.name), ('LLM_REPORT_DIR', str(path))]:
                try:
                    check = subprocess.run(['tmux', 'show-environment', '-t', '=' + session, key], capture_output=True, text=True)
                except FileNotFoundError:
                    raise ValueError('tmux is not installed')
                if check.returncode != 0 or check.stdout.rstrip('\n') != key + '=' + expected:
                    raise ValueError('tmux environment does not match this job; refusing action')
            return tmux(['kill-session' if mode == 'kill' else 'attach-session', '-t', '=' + session]).returncode
        target = path / {'status': 'status.md', 'progress': 'progress.md', 'result': 'result.md', 'pane': 'pane.log', 'events': 'events.tsv', 'meta': 'meta.env', 'prompt': 'prompt.run.md'}[mode]
        if target.is_symlink() or not target.is_file():
            raise ValueError(f'missing or unsafe file: {target.name}')
        if mode == 'pane':
            return subprocess.run(['tail', '-f', '--', str(target)]).returncode
        print(target.read_text(errors='replace'), end='')
        return 0
    row = info(path)
    alive = False
    try:
        session = session_for(path)
        if shutil.which('tmux'):
            alive = subprocess.run(['tmux', 'has-session', '-t', '=' + session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except ValueError:
        pass
    completion = row['completion']
    if completion.startswith('CONFLICT:'):
        classification = 'CONFLICT'
    elif row['status_completion'] == row['result_completion'] == 'COMPLETE':
        classification = 'ENDED'
    elif completion in {'FAILED', 'BLOCKED'}:
        classification = 'ENDED_WITH_ERROR'
    elif not alive:
        classification = 'SUSPECT_STALL'
    elif row['state'] == 'RUNNING_NO_REPORT':
        classification = 'RUNNING_NO_REPORT'
    else:
        classification = 'ACTIVE'
    row.update(classification=classification, tmux_alive=alive)
    if args.json:
        print(json.dumps(row, ensure_ascii=False))
    else:
        for key, value in row.items():
            print(f'{key}={value}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        sys.exit(2)
