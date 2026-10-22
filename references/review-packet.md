# Portable review packets

Requires Bash, Git and Python 3.9 or newer. Building a packet makes no model calls.
Run from the repository root or pass `--repo` explicitly.

```bash
bash /path/to/skill/scripts/llm-review-packet.sh \
  --request 'Review the requested behavior' \
  --summary 'Implemented behavior and validation results' \
  --path 'src/file with spaces.py' \
  --path "src/teacher's example.py" \
  --out /tmp/review-context.md
```

`--path` is a repeatable literal repository-relative file or directory name. Parent
traversal and absolute names are rejected. Legacy `--paths 'src tests'` remains
whitespace-separated; it cannot express filenames containing whitespace.
`LLM_REVIEW_PATHS` retains the same legacy behavior. Request, summary and scope
also accept `LLM_REVIEW_REQUEST`, `LLM_REVIEW_SUMMARY`, `LLM_REVIEW_SCOPE`.

Default `--base HEAD` compares the last commit to the current working tree,
including staged and unstaged edits. `--base <branch-or-commit>` additionally
includes committed differences since that baseline. Unborn repositories use the
empty tree (recorded in Git's object database). Deleted tracked files are
included. Untracked UTF-8 text is included within the configured limits.
An invalid baseline or a failed Git operation aborts with no partial packet.

All included diff and untracked content share `--max-diff-chars` (default 60000).
Each untracked file additionally has `--max-untracked-bytes` (default 20000).
Both settings have corresponding `LLM_REVIEW_MAX_*` environment variables.
Omission and truncation markers remain visible outside that content budget.

Sensitive basenames, private-key file extensions, credential-looking values,
symlinks, non-UTF-8/binary untracked text, `_reports` trees and the packet output
itself are excluded. One sensitive file does not suppress safe files. Names such
as `keyboard.py` and `tokenizer.py` are ordinary files. Detected credential content
is omitted at the whole-file diff level, covering removed as well as added lines.
Detection is heuristic: inspect the resulting packet before sharing. Caller
supplied request/summary/scope and filenames are not automatically redacted.
Repository changes must be quiescent during collection; this is not a sandbox
against a concurrently malicious process changing files or symlinks.

`--out` creates a private mode-0600 file and refuses to overwrite any existing
path. Use `--force` for an explicit atomic replacement. Without `--out`, the
packet is written to standard output. Success exits 0, runtime/Git/output errors
exit 1, malformed arguments exit 2. Diagnostics exclude Git stderr and file
contents. No JSON manifest is currently emitted.
