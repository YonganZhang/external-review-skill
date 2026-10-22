# Provider setup and configuration

Install the official CLI for each service you select, authenticate using its supported login flow, and check its help before use:

| Provider | Executable | Official documentation |
|---|---|---|
| Claude | `claude` | [Claude Code CLI](https://code.claude.com/docs/en/cli-reference) |
| Codex | `codex` | [Codex CLI](https://developers.openai.com/codex/cli/) |
| DeepSeek | `dsh` | [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) · [本技能接入](deepseek.md) |
| Gemini | `agy` | [Antigravity CLI](https://www.antigravity.google/docs/cli/reference/) |

This package's Gemini adapter targets Antigravity `agy`. The separate `gemini` CLI is not interchangeable. No credentials are installed or bundled. Doctor `all` checks all four providers; legacy `both` checks the original three. Standard caller environment and existing CLI configuration are used; no private proxy file is sourced. Run `bash scripts/llm-doctor.sh <provider> --json` to check local interface compatibility. Successful help checks do not establish authentication, network access or quota.

## Models

The defaults retain the original workflow's fast-review profile:

| Provider | Normal | `--deep` | `--gate` |
|---|---|---|---|
| Codex | `gpt-6.1-sol`, low | same | same model, medium |
| Claude | `sonnet`, low | `opus`, low | `opus`, medium |
| DeepSeek | `deepseek-flash`, low | same model, high | same model, high |
| Gemini | CLI default | CLI default | CLI default |

Availability depends on the installed CLI and account. Set an available model explicitly if a default is unavailable; a failure never authorizes a silent model change.

Unified entry: `--model claude=<model>` / `codex=<model>` / `gemini=<model>` / `deepseek=<model>`. Direct wrapper: `--model <model>`. Explicit flags take priority over environment model choices.

Environment overrides: `LLM_CODEX_MODEL`, `LLM_CODEX_EFFORT`, `LLM_CLAUDE_MODEL`, `LLM_CLAUDE_EFFORT`, `LLM_GEMINI_MODEL`, `LLM_DEEPSEEK_MODEL`, `LLM_DEEPSEEK_EFFORT`. Claude additionally accepts a caller-set `ANTHROPIC_MODEL`; Gemini accepts legacy `GEMINI_PRIMARY_MODEL`. Explicit effort environment values override the fast/deep/gate profile. Actual selections appear in `events.tsv` as `model_start`.

Gemini retries only when the caller explicitly supplies comma-separated `GEMINI_FALLBACK_MODELS` and the error classifier reports quota exhaustion. Other failures are returned. The adapter does not switch to an API-key account. Do not assume fallback models have independent quota.

## Permissions

`native` is the default. Claude and agy retain their CLI defaults; Codex and DeepSeek use `workspace-write` so it can write its report. The review prompt instructs the provider to leave project sources unchanged. This is not an OS read-only sandbox: local CLI configuration, project instructions and tools still matter.

`--permission-mode bypass` deliberately passes the provider's permission bypass flag. Use it only when explicitly authorized for a trusted task. For source isolation, review a disposable checkout or container and compare its diff afterward.

The skill starts per-job hidden tmux sessions and does not modify an existing interactive session. It adds no global command queue or resource reservation. Calls still incur the selected provider's normal usage charges or quota consumption.
