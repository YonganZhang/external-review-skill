# Troubleshooting

Run commands from the skill directory. Every command accepts `--help`.

```bash
bash scripts/llm-jobs.sh --repo /path/to/project --json
bash scripts/llm-tail.sh --repo /path/to/project --status <full-job-id>
bash scripts/llm-stall-doctor.sh --repo /path/to/project --json <full-job-id>
bash scripts/llm-doctor.sh all --json
```

Read the job's `status.md`, `progress.md`, `result.md`, `events.tsv` and `pane.log`. A worker's invalid or failed original report is retained as `result.agent.md` when the runner replaces it with a failure report. Paths and prompts may contain private project information, so review logs before sharing them.

| Outcome | Next step |
|---|---|
| AUTH | Verify the chosen CLI is logged in under the same user and environment; never paste credentials into a report |
| QUOTA | Check that service's account or wait for reset; no implicit account/model fallback |
| NETWORK | Check the actual CLI endpoint and caller proxy configuration; generic public URL failures are not proof of service failure |
| TOOLING / MODEL_REJECT | Inspect local CLI help/version and model availability; supply a supported explicit model |
| TIMEOUT / OUTER_TIMEOUT | Inspect progress and provider exit status; choose a suitable timeout for a subsequent attempt |
| MISSING_COMPLETION_MARKER | Inspect `result.agent.md`; a chat response or process exit is not a substitute for the required file |
| TMUX_DIED | Check the report and terminal log; killing a session does not constitute successful review |
| CONFLICT from stall doctor | Status and result disagree; inspect artifacts before accepting completion |

Success requires a zero provider exit and a unique, nonempty strict report. The runner closes successful hidden sessions; reports remain. Failed sessions are retained for diagnosis for 21600 seconds by default (`LLM_FAILED_SESSION_TTL_SEC`; zero means immediate expiry). Provider process groups are time-bounded with GNU `timeout`; if TERM is ignored, SIGKILL follows after a five-second grace. The outer deadline includes that grace per allowed attempt. Detached processes that deliberately escape the process group require a stronger external supervisor.

`llm-tail.sh --repo <project> --kill <full-job-id>` explicitly terminates one identified session. It requires the full job ID and matching tmux job metadata; it never kills all sessions. Older jobs without matching metadata may be viewable but cannot be killed through this helper.

`LLM_HEARTBEAT_SEC` controls status polling, not model effort. `LLM_REPORT_STALE_SEC` controls stale-progress hints. `LLM_OUTER_GRACE_SEC` controls the outer wait allowance. These values do not change machine-wide scheduling or memory limits.
