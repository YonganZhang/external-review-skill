# Release validation

Linux, Python 3.10, Bash and tmux. Synthetic verification does not require provider accounts:

- 21 Python tests cover provider selection and parallel partial completion, strict reports, job/session identity, staged/base/untracked packets and output preservation.
- 18 isolated provider launches exercise the tmux runner, including malformed/missing reports, nonzero exit with a COMPLETE report, explicit model/permission flags, quota-only fallback, path quoting, fast/deep/gate profiles and a TERM-ignoring process that is killed after the five-second grace.

The release process additionally checks manifest hashes, deterministic ZIP bytes, extraction, project-local installation, repeated installation and modified-file rejection. Tests do not establish correctness of a provider's review conclusions. Authentication and live service availability depend on the recipient's environment.

On 2026-10-22, an additional live smoke test completed with Claude and Gemini in native permission mode against the same synthetic two-line Python example. Both exited zero, wrote valid independent reports, and the example remained unchanged. This does not establish live Codex authentication or the availability of any recipient's account. Runtime logs are deliberately excluded from the release.

Run the commands in README to reproduce the synthetic checks. Review limitations and permission behavior in `references/providers.md` and `references/troubleshooting.md` before use.
