# Source and scope

This is a standalone release of Yongan Zhang's `share-external-llm` workflow, published by its owner. Source baseline: `21c5aa24f7df01cd1aaf6b0343bddff06d7f6219`; the later `--gate` model/effort profile from `fa2384bcd37b647d32ac4739ecdd5b7be9e9ac87` is preserved. The original private repository and its history are not included.

Release changes: strict exit/report validation; independent review orchestration; staged/base/untracked review packets; explicit model and permission controls; local job identity checks; portable installation, tests and documentation. Private proxy loading and a fixed Gemini default were removed. Existing fast Claude/Codex profiles remain configurable.

The payload contains only this external-review capability and synthetic tests. It excludes other applications, personal memory contents, credentials, private prompts, runtime reports and service binaries. Claude Code, Codex and Antigravity are separately installed services/tools governed by their respective terms; their names identify interoperability, not endorsement.
