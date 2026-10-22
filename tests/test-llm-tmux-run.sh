#!/bin/bash
set -euo pipefail

# 默认测本 skill 的 scripts/;测 Codex 侧副本时设
#   RUNNER_UNDER_TEST=$HOME/.codex/scripts/llm-tmux-run.sh CLASSIFIER_UNDER_TEST=$HOME/.codex/scripts/llm-classify.sh
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${RUNNER_UNDER_TEST:-$HERE/../scripts/llm-tmux-run.sh}"
CLASSIFIER="${CLASSIFIER_UNDER_TEST:-$HERE/../scripts/llm-classify.sh}"
TMP="$(mktemp -d)"
REPO="$TMP/repo space's"
export HOME="$TMP/home"
mkdir -p "$HOME"
export TMUX_TMPDIR="$TMP/tmux"
mkdir -p "$TMUX_TMPDIR"
BIN="$TMP/bin"
mkdir -p "$REPO" "$BIN"
SESSIONS=()

cleanup() {
  local session
  for session in "${SESSIONS[@]:-}"; do
    [ -n "$session" ] && tmux kill-session -t "$session" 2>/dev/null || true
  done
  rm -rf "$TMP"
}
trap cleanup EXIT

cat > "$BIN/agy" <<'STUB'
#!/bin/bash
set -euo pipefail
model=""
input_format=""
permissions=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --model|-m) model="${2:-}"; shift 2 ;;
    --input-format) input_format="${2:-}"; shift 2 ;;
    --dangerously-skip-permissions) permissions=1; shift ;;
    --include-directories|--prompt) echo 'legacy Gemini arguments'; exit 64 ;;
    *) shift ;;
  esac
done
[ "$input_format" = "stream-json" ] || exit 64
printf '%s\n' "$model|$permissions" > "$HOME/agy-args"
prompt="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["message"]["content"])')"
report_dir="$(printf '%s\n' "$prompt" | awk '/^Mandatory report directory:$/ {getline; print; exit}')"
job_id="$(basename "$report_dir")"

if printf '%s' "$prompt" | grep -q 'TEST_MODE=ignore_term'; then
  trap '' TERM
  printf '%s\n' "$$" > "$report_dir/provider.pid"
  while true; do sleep 1; done
fi
if printf '%s' "$prompt" | grep -q 'TEST_MODE=auth'; then
  echo 'UNAUTHENTICATED: invalid api key'
  exit 1
fi
if printf '%s' "$prompt" | grep -q 'TEST_MODE=missing'; then
  exit 0
fi
if printf '%s' "$prompt" | grep -q 'TEST_MODE=quota_no_fallback'; then
  echo '{"event":"result","result":{"status":"ERROR","error":"429 RESOURCE_EXHAUSTED quota exceeded"}}'
  exit 1
fi
if [ "$model" = "explicit-test-model" ] && printf '%s' "$prompt" | grep -q 'TEST_MODE=quota'; then
  echo '{"type":"tool_result","status":"success","output":"example 401 invalid token from reviewed source"}'
  echo 'Error 429: RESOURCE_EXHAUSTED daily quota exceeded'
  exit 1
fi
if [ -n "${OPENAI_API_KEY+x}" ] || [ -n "${ANTHROPIC_API_KEY+x}" ] || [ -n "${GEMINI_API_KEY+x}" ] || [ -n "${GOOGLE_API_KEY+x}" ]; then
  echo 'cross-provider credential leaked into Gemini worker'
  exit 70
fi
cat > "$report_dir/progress.md" <<EOF
# Foreign Aid Progress

JOB_ID: $job_id
PROVIDER: gemini
COMPLETION_STATUS: COMPLETE
EOF
cat > "$report_dir/result.md" <<EOF
# Foreign Aid Result

JOB_ID: $job_id
PROVIDER: gemini
COMPLETION_STATUS: COMPLETE
ERROR_CLASS: NONE

## Summary
Stub completed.

## Work Performed
- Exercised quota fallback.

## Evidence
- Stub attempt logs.

## Files Changed Or Reviewed
- None.

## Errors Or Blockers
- None.

## Next Steps
- None.
EOF
if printf '%s' "$prompt" | grep -q 'TEST_MODE=duplicate'; then
  echo 'COMPLETION_STATUS: COMPLETE' >> "$report_dir/result.md"
fi
if printf '%s' "$prompt" | grep -q 'TEST_MODE=nonzero'; then exit 42; fi
echo '{"type":"result","status":"success"}'
STUB
chmod +x "$BIN/agy"

# Never let a launcher regression invoke an installed provider during this test.
cat > "$BIN/timeout" <<STUB
#!/bin/bash
case "\${3:-}" in
  "$BIN/agy"|"$BIN/claude"|"$BIN/claude-explicit"|"$BIN/codex")
    exec /usr/bin/timeout "\$@" ;;
  *) echo 'unexpected provider executable' >&2; exit 72 ;;
esac
STUB
chmod +x "$BIN/timeout"

cat > "$BIN/claude" <<'STUB'
#!/bin/bash
set -euo pipefail
args="$*"
prompt="$(cat)"
report_dir="$(printf '%s\n' "$prompt" | awk '/^Mandatory report directory:$/ {getline; print; exit}')"
job_id="$(basename "$report_dir")"
cat > "$report_dir/result.md" <<EOF
# Foreign Aid Result

JOB_ID: $job_id
PROVIDER: claude
COMPLETION_STATUS: COMPLETE
ERROR_CLASS: NONE

## Summary
Claude launch contract checked.

## Work Performed
Used the selected executable with the caller's requested model.

## Evidence
binary=$(basename "$0")
model_env=${ANTHROPIC_MODEL:-}
args=$args

## Files Changed Or Reviewed
None.

## Errors Or Blockers
None.

## Next Steps
None.
EOF
STUB
chmod +x "$BIN/claude"
cp "$BIN/claude" "$BIN/claude-explicit"
sed -e 's/PROVIDER: claude/PROVIDER: codex/' "$BIN/claude" > "$BIN/codex"
chmod +x "$BIN/codex"

assert_eq() {
  [ "$1" = "$2" ] || { echo "assertion failed: expected '$2', got '$1'" >&2; exit 1; }
}

report_from_output() {
  sed -n '/^📁 report: /{s/^📁 report: //;p;q;}' "$1"
}

remember_session() {
  local report="$1" session
  session="$(sed -n 's/^SESSION=//p' "$report/meta.env" 2>/dev/null | head -1)"
  [ -n "$session" ] && SESSIONS+=("$session")
}

for claude_choice in path explicit; do
  claude_out="$TMP/claude-$claude_choice.out"
  claude_env=(env -u CLAUDE_RAW_BIN)
  expected_binary=claude
  if [ "$claude_choice" = explicit ]; then
    claude_env+=(CLAUDE_RAW_BIN="$BIN/claude-explicit")
    expected_binary=claude-explicit
  fi
  set +e
  "${claude_env[@]}" ANTHROPIC_MODEL=opus PATH="$BIN:$PATH" LLM_SELF_PROVIDER=codex \
    LLM_SKIP_PREFLIGHT=1 LLM_HEARTBEAT_SEC=1 LLM_FAILED_SESSION_TTL_SEC=2 \
    "$RUNNER" --provider claude --repo "$REPO" --timeout 5 'Check Claude launch selection.' \
    > "$claude_out" 2>&1
  claude_rc=$?
  set -e
  claude_report="$(report_from_output "$claude_out")"
  remember_session "$claude_report"
  assert_eq "$claude_rc" 0
  grep -q "^binary=$expected_binary$" "$claude_report/result.md"
  grep -q '^model_env=opus$' "$claude_report/result.md"
  grep -q -- '--model opus --effort low' "$claude_report/result.md"
done

# Fast defaults: Sonnet for Claude, Opus only with --deep; Codex gpt-6.1-sol; all at low effort.
for case_spec in "claude::--model sonnet --effort low" "claude:--deep:--model opus --effort low" \
                 "codex::-m gpt-6.1-sol -c model_reasoning_effort=\"low\"" \
                 "claude:--gate:--model opus --effort medium" \
                 "codex:--gate:-m gpt-6.1-sol -c model_reasoning_effort=\"medium\""; do
  provider="${case_spec%%:*}"; rest="${case_spec#*:}"; flag="${rest%%:*}"; expect="${rest#*:}"
  out="$TMP/default-$provider-${flag:-plain}.out"
  set +e
  env -u CLAUDE_RAW_BIN -u ANTHROPIC_MODEL -u LLM_CLAUDE_MODEL -u LLM_CODEX_MODEL PATH="$BIN:$PATH" \
    LLM_SELF_PROVIDER=none LLM_SKIP_PREFLIGHT=1 LLM_HEARTBEAT_SEC=1 LLM_FAILED_SESSION_TTL_SEC=2 \
    "$RUNNER" --provider "$provider" $flag --repo "$REPO" --timeout 5 'Check default model selection.' \
    > "$out" 2>&1
  rc=$?
  set -e
  report="$(report_from_output "$out")"
  remember_session "$report"
  assert_eq "$rc" 0
  grep -qF -- "$expect" "$report/result.md" || { echo "missing '$expect' for $case_spec" >&2; cat "$report/result.md" >&2; exit 1; }
done

for provider in claude codex; do
  out="$TMP/gate-override-$provider.out"
  env -u CLAUDE_RAW_BIN LLM_SELF_PROVIDER=none PATH="$BIN:$PATH" LLM_HEARTBEAT_SEC=1 \
    LLM_CODEX_MODEL=env-model LLM_CLAUDE_MODEL=env-model LLM_CODEX_EFFORT=high LLM_CLAUDE_EFFORT=high \
    "$RUNNER" --provider "$provider" --gate --model explicit-model --repo "$REPO" --timeout 5 'gate override' > "$out" 2>&1
  report="$(report_from_output "$out")"
  grep -qF 'explicit-model' "$report/result.md"
  if [ "$provider" = claude ]; then expected='--effort high'; else expected='model_reasoning_effort="high"'; fi
  grep -qF -- "$expected" "$report/result.md"
done

pollution_log="$TMP/pollution.log"
cat > "$pollution_log" <<'EOF'
{"type":"tool_result","status":"success","output":"reviewed source says 401 invalid token"}
{"event":"step_update","step_update":{"text_delta":"source mentions 401 invalid token"}}
{"event":"result","result":{"status":"ERROR","response":"quoted 401", "error":"429 RESOURCE_EXHAUSTED quota exceeded"}}
EOF
set +e
classification="$($CLASSIFIER "$pollution_log" gemini 1)"
classification_rc=$?
set -e
assert_eq "$classification_rc" "1"
printf '%s\n' "$classification" | grep -q '^classification=QUOTA_EXHAUSTED$'

quota_out="$TMP/quota.out"
OPENAI_API_KEY=dummy-openai ANTHROPIC_API_KEY=dummy-anthropic GEMINI_API_KEY=dummy-gemini \
  GEMINI_PRIMARY_MODEL=explicit-test-model GEMINI_FALLBACK_MODELS=gemini-test-fallback PATH="$BIN:$PATH" LLM_SKIP_PREFLIGHT=1 LLM_HEARTBEAT_SEC=1 LLM_OUTER_GRACE_SEC=2 \
  "$RUNNER" --provider gemini --repo "$REPO" --timeout 5 'TEST_MODE=quota' > "$quota_out" 2>&1
quota_report="$(report_from_output "$quota_out")"
grep -q 'model_fallback.*reason=QUOTA_EXHAUSTED' "$quota_report/events.tsv"
grep -q '^COMPLETION_STATUS: COMPLETE$' "$quota_report/result.md"
quota_session="$(sed -n 's/^SESSION=//p' "$quota_report/meta.env")"
! tmux has-session -t "$quota_session" 2>/dev/null

no_fallback_out="$TMP/no-fallback.out"
set +e
GEMINI_FALLBACK_MODELS='' PATH="$BIN:$PATH" LLM_SKIP_PREFLIGHT=1 LLM_HEARTBEAT_SEC=1 LLM_FAILED_SESSION_TTL_SEC=2 \
  "$RUNNER" --provider gemini --repo "$REPO" --timeout 5 'TEST_MODE=quota_no_fallback' > "$no_fallback_out" 2>&1
no_fallback_rc=$?
set -e
assert_eq "$no_fallback_rc" "1"
no_fallback_report="$(report_from_output "$no_fallback_out")"
remember_session "$no_fallback_report"
! grep -q 'model_fallback' "$no_fallback_report/events.tsv"
grep -q '^ERROR_CLASS: QUOTA$' "$no_fallback_report/result.md"

auth_out="$TMP/auth.out"
set +e
PATH="$BIN:$PATH" LLM_SKIP_PREFLIGHT=1 LLM_HEARTBEAT_SEC=1 LLM_OUTER_GRACE_SEC=2 LLM_FAILED_SESSION_TTL_SEC=2 \
  "$RUNNER" --provider gemini --repo "$REPO" --timeout 5 'TEST_MODE=auth' > "$auth_out" 2>&1
auth_rc=$?
set -e
assert_eq "$auth_rc" "2"
auth_report="$(report_from_output "$auth_out")"
remember_session "$auth_report"
! grep -q 'model_fallback' "$auth_report/events.tsv"
grep -q '^ERROR_CLASS: AUTH$' "$auth_report/result.md"

missing_out="$TMP/missing.out"
set +e
PATH="$BIN:$PATH" LLM_SKIP_PREFLIGHT=1 LLM_HEARTBEAT_SEC=1 LLM_OUTER_GRACE_SEC=2 LLM_FAILED_SESSION_TTL_SEC=2 \
  "$RUNNER" --provider gemini --repo "$REPO" --timeout 5 'TEST_MODE=missing' > "$missing_out" 2>&1
missing_rc=$?
set -e
assert_eq "$missing_rc" "8"
missing_report="$(report_from_output "$missing_out")"
remember_session "$missing_report"
grep -q '^ERROR_CLASS: MISSING_COMPLETION_MARKER$' "$missing_report/result.md"

duplicate_out="$TMP/duplicate.out"
set +e
PATH="$BIN:$PATH" LLM_SKIP_PREFLIGHT=1 LLM_HEARTBEAT_SEC=1 LLM_OUTER_GRACE_SEC=2 LLM_FAILED_SESSION_TTL_SEC=2 \
  "$RUNNER" --provider gemini --repo "$REPO" --timeout 5 'TEST_MODE=duplicate' > "$duplicate_out" 2>&1
duplicate_rc=$?
set -e
assert_eq "$duplicate_rc" "8"
duplicate_report="$(report_from_output "$duplicate_out")"
remember_session "$duplicate_report"
grep -q '^ERROR_CLASS: MISSING_COMPLETION_MARKER$' "$duplicate_report/result.md"

set +e
LLM_SELF_PROVIDER=codex "$RUNNER" --provider codex --repo "$REPO" 'self call must fail' >/dev/null 2>&1
self_rc=$?
set -e
assert_eq "$self_rc" "9"

for permission in native bypass; do
  out="$TMP/json-$permission"
  PATH="$BIN:$PATH" LLM_SELF_PROVIDER=none LLM_HEARTBEAT_SEC=1 "$RUNNER" --provider gemini --permission-mode "$permission" --model chosen --json --repo "$REPO" --timeout 5 'json check' > "$out"
  python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["status"]=="COMPLETE" and x["exit_code"]==0' "$out"
  expected_permission=0
  [ "$permission" != bypass ] || expected_permission=1
  assert_eq "$(cat "$HOME/agy-args")" "chosen|$expected_permission"
done
set +e
PATH="$BIN:$PATH" LLM_SELF_PROVIDER=none LLM_HEARTBEAT_SEC=1 LLM_FAILED_SESSION_TTL_SEC=1 "$RUNNER" --provider gemini --json --repo "$REPO" --timeout 5 'TEST_MODE=nonzero' > "$TMP/nonzero"
nonzero_rc=$?
set -e
[ "$nonzero_rc" != 0 ]
python3 -c 'import json,sys,pathlib; x=json.load(open(sys.argv[1])); assert x["status"]=="FAILED"; assert pathlib.Path(x["report_dir"],"result.agent.md").exists()' "$TMP/nonzero"
for args in '--unknown' '--timeout invalid'; do
  if "$RUNNER" --provider gemini $args x >/dev/null 2>&1; then exit 1; fi
done
timeout_out="$TMP/ignore-term.out"
started=$SECONDS
set +e
PATH="$BIN:$PATH" LLM_SELF_PROVIDER=none LLM_HEARTBEAT_SEC=1 LLM_FAILED_SESSION_TTL_SEC=1 LLM_OUTER_GRACE_SEC=1 \
  "$RUNNER" --provider gemini --repo "$REPO" --timeout 1 --json 'TEST_MODE=ignore_term' > "$timeout_out" 2> "$TMP/ignore-term.err"
timeout_rc=$?
set -e
[ "$timeout_rc" != 0 ]
[ "$((SECONDS - started))" -lt 15 ]
report="$(python3 -c 'import json,sys; x=json.load(open(sys.argv[1])); assert x["status"]=="FAILED"; print(x["report_dir"])' "$timeout_out")"
remember_session "$report"
provider_pid="$(cat "$report/provider.pid")"
! kill -0 "$provider_pid" 2>/dev/null || { echo 'TERM-ignoring provider survived bounded timeout' >&2; exit 1; }
grep -q '^137$' "$report/.agent_rc"
sleep 3
for retained_session in "${SESSIONS[@]:-}"; do
  ! tmux has-session -t "$retained_session" 2>/dev/null || {
    echo "retained failure session did not expire: $retained_session" >&2
    exit 1
  }
done

echo "PASS: Claude executable/model selection, classifier isolation, quota fallback, credential scoping, strict report gate, bounded retention, and self-provider guard"
