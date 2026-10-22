#!/usr/bin/env bash
# Compatibility entry point; requires Python 3.9+.
set -euo pipefail
exec python3 "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/llm-review-packet.py" "$@"
