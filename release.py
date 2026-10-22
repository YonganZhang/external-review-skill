#!/usr/bin/env python3
"""Build a deterministic, allowlisted release manifest and ZIP (maintainer tool)."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
ROOT_FILES = {'SKILL.md', 'README.md', 'LICENSE', 'NOTICE.md', 'VALIDATION.md', 'install.py', 'release.py', '.gitignore'}
DIRECTORIES = {'scripts', 'references', 'examples', 'tests'}
SUFFIXES = {'.md', '.py', '.sh', '.json'}
PRIVATE = re.compile(r'/mnt/data/[A-Za-z0-9_]|/home/[^ /\n]+/|/Users/[^ /\n]+/|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{20,}')


def collect():
    files = []
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if any(part in {'.git', '__pycache__', '.pytest_cache'} for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f'Symlink is not distributable: {relative}')
        if path.is_dir():
            if relative.parts[0] not in DIRECTORIES:
                raise ValueError(f'Unlisted directory: {relative}')
            continue
        if relative.as_posix() == 'MANIFEST.json':
            continue
        if len(relative.parts) == 1:
            allowed = path.name in ROOT_FILES
        else:
            allowed = relative.parts[0] in DIRECTORIES and path.suffix in SUFFIXES
        if not allowed:
            raise ValueError(f'Unlisted file: {relative}')
        if PRIVATE.search(path.read_text(encoding='utf-8')):
            raise ValueError(f'Private path or credential-shaped data: {relative}')
        files.append(relative.as_posix())
    missing = ROOT_FILES - set(files)
    if missing:
        raise ValueError('Missing release files: ' + ', '.join(sorted(missing)))
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New ZIP path outside the source directory')
    args = parser.parse_args()
    try:
        out = args.out.expanduser().resolve()
        if out.is_relative_to(ROOT):
            raise ValueError('ZIP must be outside the source directory')
        if out.exists():
            raise ValueError('Output exists; choose a new path')
        files = collect()
        manifest = {'schema': 1, 'name': 'share-external-llm',
                    'files': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}}
        (ROOT / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted([*files, 'MANIFEST.json']):
                info = zipfile.ZipInfo('share-external-llm/' + name, date_time=(2026, 1, 1, 0, 0, 0))
                info.create_system = 3
                mode = 0o755 if name.endswith(('.sh', '.py')) else 0o644
                info.external_attr = (0o100000 | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, (ROOT / name).read_bytes())
        print(json.dumps({'zip': str(out), 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(), 'files': len(files) + 1}))
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
