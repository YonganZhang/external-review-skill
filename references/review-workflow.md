# Evidence-driven review

Prepare a concrete question, baseline, file scope, changed behavior and existing verification results. The packet builder collects evidence but cannot know whether the scope is sufficient. Inspect its exclusions and truncation summary. Do not include credentials, private conversations or unnecessary personal data.

Each reviewer should inspect both sides of an interface: inputs and outputs, producer and consumer, success and failure lifecycle. For concurrency changes, trace ownership and cleanup; for data changes, inspect real readers and writers. Prefer a small reproduction that distinguishes the suspected defect from normal behavior. State when a finding is an inference rather than reproduced.

Require findings to include severity, concrete trigger, affected path/line, user-visible consequence and supporting evidence. Unsupported possibilities belong under coverage gaps, not confirmed defects. Zero findings is an acceptable outcome with a clear statement of reviewed scope and untested behavior.

The unified entry prepends a review-only task instruction, then snapshots the same input for all providers. Different providers run independently; do not feed one provider's conclusions into the other before the first round completes. Each round is retained separately. `input_sha256` identifies the supplied file and `prompt_sha256` identifies the shared review instruction plus that file; provider-specific report instructions are added by each runner afterward.

After completion, read the raw reports, verify findings against the current code, remove duplicates and identify disagreements. Mark stale findings if code changed since the snapshot. A passing format checker means the worker reported completion; it is not endorsement of its conclusions. `PARTIAL` and `FAILED` require an explicit coverage statement. Do not manufacture missing reports or replace them with the host's own review.

Apply fixes only within the user's authorized scope. Keep the original reports, explain which findings were accepted or rejected and why, then run checks appropriate to the resulting change.
