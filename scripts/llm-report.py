#!/usr/bin/env python3
"""Strict final-report validation shared by the worker and caller."""
import pathlib
import re
import sys

SECTIONS = ('Summary', 'Work Performed', 'Evidence', 'Files Changed Or Reviewed', 'Errors Or Blockers', 'Next Steps')

def validate(path, job_id, provider):
    try:
        text = pathlib.Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return False
    for key, expected in dict(JOB_ID=job_id, PROVIDER=provider, COMPLETION_STATUS='COMPLETE', ERROR_CLASS='NONE').items():
        values = re.findall(r'^\s*' + key + r'\s*:\s*([^\n]*)$', text, re.M)
        if len(values) != 1 or values[0].strip() != expected:
            return False
    for name in SECTIONS:
        matches = list(re.finditer(r'^##\s+' + re.escape(name) + r'\s*$', text, re.M))
        if len(matches) != 1:
            return False
        remainder = text[matches[0].end():]
        body = re.split(r'^##\s+', remainder, maxsplit=1, flags=re.M)[0].strip()
        # Header fields are metadata, not section evidence.
        body = re.sub(r'^(?:JOB_ID|PROVIDER|COMPLETION_STATUS|ERROR_CLASS)\s*:.*$', '', body, flags=re.M).strip()
        if not body or body.strip('-* \t\n') in ('', 'Pending.', 'Pending'):
            return False
    return True

if __name__ == '__main__':
    sys.exit(0 if len(sys.argv) == 4 and validate(*sys.argv[1:]) else 1)
