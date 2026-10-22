# Script entry points

| Entry | Purpose |
|---|---|
| `external-review.py` | Select providers, run independent reviews, retain round summary and partial failure |
| `llm-review-packet.sh` → `llm-review-packet.py` | Build bounded Git review evidence |
| `claude-ask.sh`, `codex-ask.sh`, `gemini-ask.sh`, `deepseek-ask.sh` | Single-provider task wrappers |
| `llm-tmux-run.sh` | Provider lifecycle and report artifact owner |
| `deepseek-run.py` | Run official dsh headless with per-job home and validate actual terminal events/report; normally called by the runner |
| `deepseek-usage.py` | Summarize root-agent tokens and dated idle/peak cost estimates: `--events <jsonl> --model deepseek-flash [--out <json>]` |
| `llm-report.py` | Strict report validation, called by the runner |
| `llm-classify.sh` | Classify provider diagnostics without model calls |
| `llm-jobs.sh`, `llm-tail.sh`, `llm-stall-doctor.sh`, `llm-doctor.sh` → `llm-jobs.py` | Status, explicit per-job session operations and local dependency diagnosis |

Use `--help` on an entry for its current flags. Main instructions: [SKILL](../SKILL.md), [README](../README.md). Synthetic tests: [tests](../tests/README.md). Installation and release tooling live at package root.
