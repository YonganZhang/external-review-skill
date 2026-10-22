#!/bin/bash
set -euo pipefail
exec "$(dirname "$0")/llm-tmux-run.sh" --provider codex "$@"
