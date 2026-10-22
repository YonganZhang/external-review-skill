# Script entry points

| Entry | Purpose |
|---|---|
| `external-review.py` | Select providers, run independent reviews, retain round summary and partial failure |
| `llm-review-packet.sh` → `llm-review-packet.py` | Build bounded Git review evidence |
| `claude-ask.sh`, `codex-ask.sh`, `gemini-ask.sh` | Single-provider task wrappers |
| `llm-tmux-run.sh` | Provider lifecycle and report artifact owner |
| `llm-report.py` | Strict report validation, called by the runner |
| `llm-classify.sh` | Classify provider diagnostics without model calls |
| `llm-jobs.sh`, `llm-tail.sh`, `llm-stall-doctor.sh`, `llm-doctor.sh` → `llm-jobs.py` | Status, explicit per-job session operations and local dependency diagnosis |

Use `--help` on an entry for its current flags. Main instructions: [SKILL](../SKILL.md), [README](../README.md). Synthetic tests: [tests](../tests/README.md). Installation and release tooling live at package root.
