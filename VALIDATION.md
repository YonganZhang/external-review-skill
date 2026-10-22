# Release validation

Linux, Python 3.10, Bash and tmux. Synthetic verification does not require provider accounts:

- 43 Python tests cover provider selection and parallel partial completion, strict reports, job/session identity, staged/base/untracked packets and output preservation, DeepSeek event/usage contracts, secure key handoff and seven end-to-end fake dsh launches.
- 18 isolated provider launches exercise the tmux runner, including malformed/missing reports, nonzero exit with a COMPLETE report, explicit model/permission flags, quota-only fallback, path quoting, fast/deep/gate profiles and a TERM-ignoring process that is killed after the five-second grace.

The release process additionally checks manifest hashes, deterministic ZIP bytes, extraction, project-local installation, repeated installation and modified-file rejection. Tests do not establish correctness of a provider's review conclusions. Authentication and live service availability depend on the recipient's environment.

On 2026-10-22, an additional live smoke test completed with Claude and Gemini in native permission mode against the same synthetic two-line Python example. Both exited zero, wrote valid independent reports, and the example remained unchanged. This does not establish live Codex authentication or the availability of any recipient's account. Runtime logs are deliberately excluded from the release.

Run the commands in README to reproduce the synthetic checks. Review limitations and permission behavior in `references/providers.md` and `references/troubleshooting.md` before use.

DeepSeek v1.1.0 validation (2026-10-22): official npm `@deepseek-ai/dsh@0.2.1-rc.2` on Node 22.22.1 completed a native-permission Flash/low review through the full orchestrator. It read a synthetic Python file, executed a reproduction, identified the seeded denominator error, wrote a strict report and left the source unchanged. The root stream reported 11,878 uncached input, 71,168 cache-read input and 2,865 output tokens. At that date's tariffs this root-only token estimate is CNY 0.02476136–0.04952272, not an account billing reconciliation.

Two Flash/high integration-review attempts reached their explicitly shortened 300-second and 240-second timeouts and correctly returned FAILED; final events were not mistaken for success. These did not yield completed cross-model code-review reports. The normal per-provider default remains 1,200 seconds. A Claude integration-review attempt was blocked by account weekly quota, so no successful Claude review of v1.1.0 is claimed. Prior v1.0.0 Claude/Gemini smoke evidence remains distinct.

After final shared-skill installation, a second Flash/low native run also completed through the installed orchestrator, read the same fixture and returned a strict report. The final runtime files were byte-compared between the shared skill and release payload. The fixture remained unchanged. Local package tests: 43 passed; shared runtime tests: 41 passed. No successful high-effort code-review conclusion is claimed.
