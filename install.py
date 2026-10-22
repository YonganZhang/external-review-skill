#!/usr/bin/env python3
"""Verify this release and install project-local Claude/Codex skill copies."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def verified_files(root):
    manifest = json.loads((root / 'MANIFEST.json').read_text())
    if manifest.get('schema') != 1 or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported release manifest')
    files = manifest['files']
    for name, digest in files.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or '\\' in name:
            raise ValueError('Unsafe manifest path')
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing or unsafe release file: {name}')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Release checksum mismatch: {name}')
    if 'SKILL.md' not in files or 'scripts/external-review.py' not in files:
        raise ValueError('Incomplete skill release')
    return [*sorted(files), 'MANIFEST.json']


def same_install(destination, files):
    if destination.is_symlink() or not destination.is_dir():
        return False
    for name in files:
        path = destination / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != (ROOT / name).read_bytes():
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True, help='Existing project directory')
    parser.add_argument('--target', choices=['codex', 'claude', 'both'], default='both')
    parser.add_argument('--apply', action='store_true', help='Copy files; default only previews')
    args = parser.parse_args()
    try:
        files = verified_files(ROOT)
        project = args.project.expanduser().resolve(strict=True)
        if not project.is_dir():
            raise ValueError('--project must be a directory')
        targets = ['codex', 'claude'] if args.target == 'both' else [args.target]
        destinations = [project / ('.agents' if name == 'codex' else '.claude') / 'skills/share-external-llm' for name in targets]
        pending = []
        for dest in destinations:
            if not dest.parent.resolve().is_relative_to(project):
                raise ValueError(f'Install parent escapes project: {dest.parent}')
            if dest.exists() or dest.is_symlink():
                if same_install(dest, files):
                    print(f'Already installed: {dest}')
                    continue
                raise ValueError(f'Existing different skill; preserve or move it before installing: {dest}')
            pending.append(dest)
        for dest in pending:
            if not args.apply:
                print(f'Would install: {dest}')
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.external-review-install-', dir=dest.parent) as temporary:
                staged = Path(temporary) / 'skill'
                staged.mkdir()
                for name in files:
                    out = staged / name
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, out)
                    out.chmod(0o755 if name.endswith(('.sh', '.py')) else 0o644)
                staged.rename(dest)
            print(f'Installed: {dest}')
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
