# Source and scope

This is a standalone release of Yongan Zhang's `share-external-llm` workflow, published by its owner. Source baseline: `21c5aa24f7df01cd1aaf6b0343bddff06d7f6219`; the later `--gate` model/effort profile from `fa2384bcd37b647d32ac4739ecdd5b7be9e9ac87` is preserved. The original private repository and its history are not included.

Release changes: strict exit/report validation; independent review orchestration; staged/base/untracked review packets; explicit model and permission controls; local job identity checks; portable installation, tests and documentation. Private proxy loading and a fixed Gemini default were removed. Existing fast Claude/Codex profiles remain configurable.

The payload contains only this external-review capability and synthetic tests. It excludes other applications, personal memory contents, credentials, private prompts, runtime reports and service binaries. Claude Code, Codex, Antigravity and DeepSeek Harness are separately installed services/tools governed by their respective terms; their names identify interoperability, not endorsement.

DeepSeek integration uses the official `deepseek-ai/deepseek-harness` project (MIT), npm `@deepseek-ai/dsh@0.2.1-rc.2`. Contract reference inspected at commit `687f282e8625c6b8d11ff58211a90524be2e4317`; the npm release and source commit are separate provenance records, not a claimed reproducible mapping. Harness dependencies and source are not vendored here. The adapter reuses the official headless runtime and adapts provider selection, report validation and usage output. Interactive account login, Web UI hosting and automatic updates are outside this adapter.
