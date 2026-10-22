#!/bin/bash
# llm-tmux-run.sh — run an external AI CLI inside tmux with project-local live reports.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
detect_self_provider() {
  if [ -n "${LLM_SELF_PROVIDER:-}" ]; then
    printf '%s\n' "$LLM_SELF_PROVIDER"
  elif [ -n "${CODEX_THREAD_ID:-}" ] || [ -n "${CODEX_CI:-}" ] || [ -n "${CODEX_MANAGED_BY_NPM:-}" ]; then
    printf 'codex\n'
  elif [ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_CODE:-}" ] || [ -n "${CLAUDE_SESSION_ID:-}" ] || [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
    printf 'claude\n'
  elif [[ "$SCRIPT_DIR" == *"/.codex/"* ]]; then
    printf 'codex\n'
  elif [[ "$SCRIPT_DIR" == *"/.claude/"* ]]; then
    printf 'claude\n'
  else
    printf 'unknown\n'
  fi
}
SELF_PROVIDER="$(detect_self_provider)"
PROVIDER=""
PROMPT=""
PROMPT_FILE=""
REPO=""
TIMEOUT_SEC=""
DEEP=0
GATE=0
MODEL=""
JSON_MODE=0
PERMISSION_MODE=native
SUMMARY_EMITTED=0
SUMMARY_FD=1
finish_summary() {
  local rc=$?
  [ -z "${DEEPSEEK_KEY_FILE:-}" ] || rm -f -- "$DEEPSEEK_KEY_FILE"
  if [ "$JSON_MODE" = 1 ]; then
    python3 - "${JOB_ID:-}" "$PROVIDER" "${REPORT_DIR:-}" "$rc" >&3 <<'PYSUM'
import json,sys
print(json.dumps(dict(job_id=sys.argv[1],provider=sys.argv[2],report_dir=sys.argv[3],status="COMPLETE" if sys.argv[4]=="0" else "FAILED",exit_code=int(sys.argv[4]))))
PYSUM
  fi
}
exec 3>&1
trap finish_summary EXIT

usage() {
  cat >&2 <<'EOF'
Usage:
  llm-tmux-run.sh --provider <codex|gemini|claude|deepseek> "<prompt>"
  llm-tmux-run.sh --provider <codex|gemini|claude|deepseek> --prompt-file <file>

Options:
  --repo <path>       Project root for _reports/_foreign_aid (default: git root or cwd)
  --timeout <sec>     Override provider timeout
  --deep              Claude uses Opus/low; DeepSeek keeps its model with high effort
  --gate              Pre-action review: Claude Opus + medium; Codex medium; DeepSeek high
  --model <name>      Explicit provider model; Gemini otherwise follows agy default
  --json              Emit one JSON summary on stdout; progress on stderr
  --permission-mode native|bypass  CLI permissions (default native)

Models (fast by default; env overrides win):
  deepseek LLM_DEEPSEEK_MODEL (deepseek-flash), LLM_DEEPSEEK_EFFORT (low; high with --deep/--gate)
  codex   LLM_CODEX_MODEL (gpt-6.1-sol), LLM_CODEX_EFFORT (low; medium with --gate)
  claude  LLM_CLAUDE_MODEL (sonnet; opus with --deep/--gate), LLM_CLAUDE_EFFORT (low; medium with --gate);
          a caller-set ANTHROPIC_MODEL is honoured when LLM_CLAUDE_MODEL is unset

Completion gate:
  The tmux session is closed only when result.md contains:
  COMPLETION_STATUS: COMPLETE
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --provider) PROVIDER="${2:?provider required}"; shift 2 ;;
    --prompt-file) PROMPT_FILE="${2:?prompt file required}"; shift 2 ;;
    --repo) REPO="${2:?repo path required}"; shift 2 ;;
    --timeout) TIMEOUT_SEC="${2:?timeout seconds required}"; shift 2 ;;
    --deep) DEEP=1; shift ;;
    --gate) GATE=1; shift ;;
    --model) MODEL="${2:?model required}"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    --permission-mode) PERMISSION_MODE="${2:?permission mode required}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; PROMPT="${*:-}"; break ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
    *)
      PROMPT="$1"
      shift
      ;;
  esac
done

[ "$JSON_MODE" != 1 ] || exec 1>&2
case "$PERMISSION_MODE" in native|bypass) ;; *) echo "invalid permission mode" >&2; exit 2 ;; esac
[ -n "$PROVIDER" ] || { echo "provider required" >&2; usage; exit 2; }
case "$PROVIDER" in codex|gemini|claude|deepseek) ;; *) echo "bad provider: $PROVIDER" >&2; exit 2 ;; esac

if [ "$PROVIDER" = "$SELF_PROVIDER" ] && [ "${LLM_ALLOW_SELF_EXTERNAL:-0}" != "1" ]; then
  echo "🔴 Refusing self-provider external call: $SELF_PROVIDER -> $PROVIDER" >&2
  echo "Use the current host's native subagent/Task path for self-review. Set LLM_ALLOW_SELF_EXTERNAL=1 only for explicit CLI isolation debugging." >&2
  exit 9
fi

if [ -n "$PROMPT_FILE" ] && [ ! -f "$PROMPT_FILE" ]; then
  echo "prompt file not found: $PROMPT_FILE" >&2
  exit 2
fi
if [ -z "$PROMPT_FILE" ] && [ -z "$PROMPT" ]; then
  echo "prompt or --prompt-file required" >&2
  usage
  exit 2
fi

if [ -z "$REPO" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
fi
REPO="$(cd "$REPO" && pwd)"

case "$PROVIDER" in
  deepseek)
    BIN="dsh"
    DEFAULT_TIMEOUT="${DEEPSEEK_TIMEOUT:-1200}"
    PREFLIGHT_URL="https://api.deepseek.com/"
    ;;
  codex)
    BIN="codex"
    DEFAULT_TIMEOUT="${CODEX_TIMEOUT:-1200}"
    PREFLIGHT_URL="https://api.openai.com/v1/models"
    ;;
  gemini)
    BIN="agy"
    DEFAULT_TIMEOUT="${GEMINI_TIMEOUT:-1200}"
    PREFLIGHT_URL="https://www.antigravity.google/"
    ;;
  claude)
    BIN="claude"
    DEFAULT_TIMEOUT="${CLAUDE_TIMEOUT:-1200}"
    PREFLIGHT_URL="https://api.anthropic.com/"
    ;;
esac
TIMEOUT_SEC="${TIMEOUT_SEC:-$DEFAULT_TIMEOUT}"
HEARTBEAT_SEC="${LLM_HEARTBEAT_SEC:-30}"
REPORT_STALE_SEC="${LLM_REPORT_STALE_SEC:-120}"
OUTER_GRACE_SEC="${LLM_OUTER_GRACE_SEC:-30}"
FAILED_SESSION_TTL_SEC="${LLM_FAILED_SESSION_TTL_SEC:-21600}"
if ! [[ "$FAILED_SESSION_TTL_SEC" =~ ^[0-9]+$ ]]; then
  echo "LLM_FAILED_SESSION_TTL_SEC must be a non-negative integer" >&2
  exit 2
fi
GEMINI_PRIMARY_MODEL="${MODEL:-${LLM_GEMINI_MODEL:-${GEMINI_PRIMARY_MODEL:-}}}"
# Fast defaults; --gate raises default effort, explicit caller choices still win.
default_effort=low
[ "$GATE" != 1 ] || default_effort=medium
CODEX_MODEL="${MODEL:-${LLM_CODEX_MODEL:-gpt-6.1-sol}}"
CODEX_EFFORT="${LLM_CODEX_EFFORT:-$default_effort}"
if [ -n "${LLM_CLAUDE_MODEL:-}" ]; then
  CLAUDE_MODEL="$LLM_CLAUDE_MODEL"
elif [ -n "${ANTHROPIC_MODEL:-}" ]; then
  CLAUDE_MODEL="$ANTHROPIC_MODEL"
elif [ "$DEEP" = 1 ] || [ "$GATE" = 1 ]; then
  CLAUDE_MODEL=opus
else
  CLAUDE_MODEL=sonnet
fi
CLAUDE_MODEL="${MODEL:-$CLAUDE_MODEL}"
CLAUDE_EFFORT="${LLM_CLAUDE_EFFORT:-$default_effort}"
DEEPSEEK_MODEL="${MODEL:-${LLM_DEEPSEEK_MODEL:-deepseek-flash}}"
deepseek_default_effort=low
if [ "$DEEP" = 1 ] || [ "$GATE" = 1 ]; then deepseek_default_effort=high; fi
DEEPSEEK_EFFORT="${LLM_DEEPSEEK_EFFORT:-$deepseek_default_effort}"
DEEPSEEK_ADAPTER="$SCRIPT_DIR/deepseek-run.py"
DEEPSEEK_USAGE="$SCRIPT_DIR/deepseek-usage.py"
DEEPSEEK_KEY_FILE=""
if [ "$PROVIDER" = deepseek ]; then
  case "$DEEPSEEK_MODEL" in deepseek-flash|deepseek-v4-pro) ;; *) echo "unsupported DeepSeek model" >&2; exit 2 ;; esac
  case "$DEEPSEEK_EFFORT" in off|low|high|max) ;; *) echo "unsupported DeepSeek effort" >&2; exit 2 ;; esac
fi
for timing_name in TIMEOUT_SEC HEARTBEAT_SEC REPORT_STALE_SEC OUTER_GRACE_SEC FAILED_SESSION_TTL_SEC; do
  [[ "${!timing_name}" =~ ^[0-9]{1,8}$ ]] || { echo "$timing_name must be an integer" >&2; exit 2; }
  printf -v "$timing_name" '%d' "$((10#${!timing_name}))"
done
[ "$TIMEOUT_SEC" -gt 0 ] && [ "$HEARTBEAT_SEC" -gt 0 ] || { echo "timeout and heartbeat must be positive" >&2; exit 2; }
REPORT_VALIDATOR="$SCRIPT_DIR/llm-report.py"
GEMINI_FALLBACK_MODELS="${GEMINI_FALLBACK_MODELS:-}"
CLASSIFY_SCRIPT="$SCRIPT_DIR/llm-classify.sh"
PROVIDER_ATTEMPTS_MAX=1
if [ "$PROVIDER" = "gemini" ]; then
  IFS=',' read -r -a _gemini_fallbacks <<< "$GEMINI_FALLBACK_MODELS"
  for _gemini_model in "${_gemini_fallbacks[@]}"; do
    [ -n "$_gemini_model" ] && PROVIDER_ATTEMPTS_MAX=$((PROVIDER_ATTEMPTS_MAX + 1))
  done
fi

JOB_ID="$(date +%Y%m%dT%H%M%S)__${PROVIDER}__$$"
SESSION="llm_${JOB_ID//[^A-Za-z0-9_]/_}"
REPORT_DIR="$REPO/_reports/_foreign_aid/$JOB_ID"
STATUS_FILE="$REPORT_DIR/status.md"
PROGRESS_FILE="$REPORT_DIR/progress.md"
RESULT_FILE="$REPORT_DIR/result.md"
EVENTS_FILE="$REPORT_DIR/events.tsv"
PANE_LOG="$REPORT_DIR/pane.log"
PROMPT_RUN="$REPORT_DIR/prompt.run.md"
RUNNER="$REPORT_DIR/run.sh"
META="$REPORT_DIR/meta.env"
DONE_FILE="$REPORT_DIR/.agent_done"
RC_FILE="$REPORT_DIR/.agent_rc"
FINAL_CLASS_FILE="$REPORT_DIR/provider-final-classification.txt"

mkdir -p "$REPORT_DIR"
chmod 700 "$REPORT_DIR"
: > "$PANE_LOG"
chmod 600 "$PANE_LOG"

prompt_chars=0
prompt_sha=""
if [ -n "$PROMPT_FILE" ]; then
  prompt_chars="$(wc -m < "$PROMPT_FILE" | tr -d ' ')"
  prompt_sha="$(sha256sum "$PROMPT_FILE" | awk '{print $1}')"
else
  prompt_chars="${#PROMPT}"
  prompt_sha="$(printf '%s' "$PROMPT" | sha256sum | awk '{print $1}')"
fi

write_status() {
  local state="$1" completion="$2" detail="${3:-}"
  cat > "$STATUS_FILE" <<EOF
# Foreign Aid Live Status

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
HOST_PROVIDER: $SELF_PROVIDER
STATE: $state
COMPLETION_STATUS: $completion
DETAIL: $detail
STARTED_AT: $STARTED_AT
UPDATED_AT: $(date -Iseconds)
TIMEOUT_SEC: $TIMEOUT_SEC
PROVIDER_ATTEMPTS_MAX: $PROVIDER_ATTEMPTS_MAX
TMUX_SESSION: $SESSION
REPO: $REPO
REPORT_DIR: $REPORT_DIR
PROGRESS_FILE: $PROGRESS_FILE
RESULT_FILE: $RESULT_FILE
PANE_LOG: pane.log
EVENTS_FILE: events.tsv
PROMPT_SHA256: $prompt_sha
PROMPT_CHARS: $prompt_chars

Attach:
\`\`\`bash
tmux attach -t $SESSION
\`\`\`
EOF
  chmod 600 "$STATUS_FILE"
}

event() {
  local type="$1"; shift
  local message="$*"
  if [ ! -f "$EVENTS_FILE" ]; then
    printf "ts\telapsed_s\tprovider\ttype\tmessage\n" > "$EVENTS_FILE"
    chmod 600 "$EVENTS_FILE"
  fi
  local now elapsed
  now="$(date +%s)"
  elapsed=$(( now - START_EPOCH ))
  printf "%s\t%s\t%s\t%s\t%s\n" "$(date -Iseconds)" "$elapsed" "$PROVIDER" "$type" "$(printf '%s' "$message" | tr '\t\r\n' '   ')" >> "$EVENTS_FILE"
}

valid_report() {
  python3 "$REPORT_VALIDATOR" "$1" "$JOB_ID" "$PROVIDER"
}

classification_exit_code() {
  case "$1" in
    QUOTA_EXHAUSTED) echo 1 ;;
    AUTH) echo 2 ;;
    NETWORK) echo 3 ;;
    TIMEOUT) echo 4 ;;
    SILENT_FAIL) echo 5 ;;
    MODEL_REJECT) echo 6 ;;
    UNKNOWN_FAIL|NO_LOG) echo 7 ;;
    TOOLING) echo 8 ;;
    *) echo 8 ;;
  esac
}

public_error_class() {
  case "$1" in
    QUOTA_EXHAUSTED) echo QUOTA ;;
    AUTH|NETWORK|TIMEOUT|TOOLING|MODEL_REJECT|MISSING_COMPLETION_MARKER|TMUX_DIED|OUTER_TIMEOUT) echo "$1" ;;
    *) echo UNKNOWN ;;
  esac
}

STARTED_AT="$(date -Iseconds)"
START_EPOCH="$(date +%s)"
write_status "PREPARING" "IN_PROGRESS" "creating tmux report workspace"
event "start" "report_dir=$REPORT_DIR timeout=${TIMEOUT_SEC}s"

cat > "$PROGRESS_FILE" <<EOF
# Foreign Aid Progress

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
COMPLETION_STATUS: IN_PROGRESS

The invoked agent must update this file while working.
EOF
chmod 600 "$PROGRESS_FILE"

cat > "$RESULT_FILE" <<EOF
# Foreign Aid Result

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
COMPLETION_STATUS: IN_PROGRESS

## Summary
Pending.

## Evidence
Pending.

## Files Changed Or Reviewed
Pending.

## Errors Or Blockers
Pending.

## Next Steps
Pending.
EOF
chmod 600 "$RESULT_FILE"

if ! command -v tmux >/dev/null 2>&1; then
  write_status "FAILED" "FAILED" "tmux not installed"
  event "failed" "tmux not installed"
  echo "🔴 tmux not installed; report: $REPORT_DIR" >&2
  exit 127
fi
if ! command -v "$BIN" >/dev/null 2>&1; then
  write_status "FAILED" "FAILED" "$BIN CLI not found"
  event "failed" "$BIN CLI not found"
  echo "🔴 $BIN CLI not found; report: $REPORT_DIR" >&2
  exit 127
fi
BIN_PATH="$(command -v "$BIN")"
BIN_PATH="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$BIN_PATH")"
if [ "$PROVIDER" = claude ] && [ -n "${CLAUDE_RAW_BIN:-}" ]; then
  BIN_PATH="$(command -v "$CLAUDE_RAW_BIN")"
  BIN_PATH="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$BIN_PATH")"
fi
GEMINI_BIN_PATH=""
GEMINI_EXEC_PATH=""
if [ "$PROVIDER" = "gemini" ]; then
  GEMINI_BIN_PATH="$BIN_PATH"
  GEMINI_EXEC_PATH="$(dirname "$GEMINI_BIN_PATH"):/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
fi

if [ "${LLM_PREFLIGHT:-0}" = "1" ] && [ "${LLM_SKIP_PREFLIGHT:-0}" != "1" ]; then
  write_status "PREFLIGHT" "IN_PROGRESS" "$PREFLIGHT_URL"
  event "preflight_start" "$PREFLIGHT_URL"
  if ! timeout 5s curl -sI -o /dev/null "$PREFLIGHT_URL"; then
    write_status "FAILED" "FAILED" "network preflight failed: $PREFLIGHT_URL"
    event "preflight_fail" "$PREFLIGHT_URL"
    cat > "$RESULT_FILE" <<EOF
# Foreign Aid Result

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
COMPLETION_STATUS: FAILED
ERROR_CLASS: NETWORK

## Summary
Network preflight failed before launching tmux worker.

## Evidence
$PREFLIGHT_URL was not reachable within 5 seconds.

## Files Changed Or Reviewed
None.

## Errors Or Blockers
Network or proxy failure.

## Next Steps
Check proxy/network, then rerun the external aid job.
EOF
    echo "🔴 network preflight failed; report: $REPORT_DIR" >&2
    exit 3
  fi
  event "preflight_ok" "$PREFLIGHT_URL"
fi

cat > "$PROMPT_RUN" <<EOF
You are a CLI worker launched by another AI through tmux.

Project root:
$REPO

Mandatory report directory:
$REPORT_DIR

You must update these files (absolute paths; never write progress.md/result.md into the project root):
- $PROGRESS_FILE: append/update what you are doing as you move through phases.
- $RESULT_FILE: final report. The caller will not treat the job as complete unless this file contains exactly:
  COMPLETION_STATUS: COMPLETE

Use this final result.md template:

# Foreign Aid Result

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
COMPLETION_STATUS: COMPLETE | FAILED | BLOCKED
ERROR_CLASS: NONE | QUOTA | AUTH | NETWORK | TIMEOUT | TOOLING | MODEL_REJECT | MISSING_COMPLETION_MARKER | TMUX_DIED | OUTER_TIMEOUT | UNKNOWN

## Summary
One concise paragraph.

## Work Performed
- Concrete actions you actually performed.

## Evidence
- Files, commands, logs, or observations supporting the result.

## Files Changed Or Reviewed
- Paths or "None".

## Errors Or Blockers
- If none, write "None".

## Next Steps
- What the caller should do next.

Rules:
- Do not write COMPLETION_STATUS: COMPLETE until the requested work is genuinely done.
- If quota/auth/network/tooling/model refusal prevents completion, write FAILED or BLOCKED and include ERROR_CLASS.
- Before every meaningful phase, update progress.md with timestamp, phase, and what remains.
- Do not rely on chat output alone. The report files are the contract.
- Write JOB_ID, PROVIDER, COMPLETION_STATUS, ERROR_CLASS, and every required section exactly once. Do not repeat the completion marker at the end.
- Read the requested project sources; write only the report files. Do not edit reviewed sources.
- Permissions follow the selected CLI policy; this instruction is not an OS-enforced read-only sandbox.
- Never print, copy, or persist credentials or decrypted secrets.
- Do not use destructive git, broad cleanup, or unrelated process-kill commands.
- The worktree may already be dirty. Preserve existing changes and make each action idempotent so a quota fallback can safely continue.

User task starts below.

---
EOF
if [ -n "$PROMPT_FILE" ]; then
  cat "$PROMPT_FILE" >> "$PROMPT_RUN"
else
  printf '%s\n' "$PROMPT" >> "$PROMPT_RUN"
fi
chmod 600 "$PROMPT_RUN"

# Transfer only the caller's DeepSeek key through a private, short-lived file.
# Never put a credential in tmux arguments, metadata or the report tree.
if [ "$PROVIDER" = deepseek ] && [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  DEEPSEEK_KEY_FILE="$(python3 - <<'PYKEY'
import os,tempfile
fd,path=tempfile.mkstemp(prefix='external-review-key-')
with os.fdopen(fd,'w') as stream: stream.write(os.environ['DEEPSEEK_API_KEY'])
print(path)
PYKEY
)"
fi
{
  printf 'DEEPSEEK_MODEL=%q\n' "$DEEPSEEK_MODEL"
  printf 'DEEPSEEK_EFFORT=%q\n' "$DEEPSEEK_EFFORT"
  printf 'DEEPSEEK_ADAPTER=%q\n' "$DEEPSEEK_ADAPTER"
  printf 'DEEPSEEK_USAGE=%q\n' "$DEEPSEEK_USAGE"
  printf 'DEEPSEEK_KEY_FILE=%q\n' "$DEEPSEEK_KEY_FILE"
  printf 'REPORT_VALIDATOR=%q\n' "$REPORT_VALIDATOR"
  printf 'BIN_PATH=%q\n' "$BIN_PATH"
  printf 'PERMISSION_MODE=%q\n' "$PERMISSION_MODE"
  printf 'PROVIDER=%q\n' "$PROVIDER"
  printf 'REPO=%q\n' "$REPO"
  printf 'REPORT_DIR=%q\n' "$REPORT_DIR"
  printf 'STATUS_FILE=%q\n' "$STATUS_FILE"
  printf 'PROGRESS_FILE=%q\n' "$PROGRESS_FILE"
  printf 'RESULT_FILE=%q\n' "$RESULT_FILE"
  printf 'EVENTS_FILE=%q\n' "$EVENTS_FILE"
  printf 'PANE_LOG=%q\n' "$PANE_LOG"
  printf 'PROMPT_RUN=%q\n' "$PROMPT_RUN"
  printf 'DONE_FILE=%q\n' "$DONE_FILE"
  printf 'RC_FILE=%q\n' "$RC_FILE"
  printf 'FINAL_CLASS_FILE=%q\n' "$FINAL_CLASS_FILE"
  printf 'TIMEOUT_SEC=%q\n' "$TIMEOUT_SEC"
  printf 'HEARTBEAT_SEC=%q\n' "$HEARTBEAT_SEC"
  printf 'REPORT_STALE_SEC=%q\n' "$REPORT_STALE_SEC"
  printf 'OUTER_GRACE_SEC=%q\n' "$OUTER_GRACE_SEC"
  printf 'FAILED_SESSION_TTL_SEC=%q\n' "$FAILED_SESSION_TTL_SEC"
  printf 'SESSION=%q\n' "$SESSION"
  printf 'JOB_ID=%q\n' "$JOB_ID"
  printf 'START_EPOCH=%q\n' "$START_EPOCH"
  printf 'GEMINI_PRIMARY_MODEL=%q\n' "$GEMINI_PRIMARY_MODEL"
  printf 'CODEX_MODEL=%q\n' "$CODEX_MODEL"
  printf 'CODEX_EFFORT=%q\n' "$CODEX_EFFORT"
  printf 'CLAUDE_MODEL=%q\n' "$CLAUDE_MODEL"
  printf 'CLAUDE_EFFORT=%q\n' "$CLAUDE_EFFORT"
  printf 'GEMINI_FALLBACK_MODELS=%q\n' "$GEMINI_FALLBACK_MODELS"
  printf 'CLASSIFY_SCRIPT=%q\n' "$CLASSIFY_SCRIPT"
  printf 'PROVIDER_ATTEMPTS_MAX=%q\n' "$PROVIDER_ATTEMPTS_MAX"
  printf 'GEMINI_BIN_PATH=%q\n' "$GEMINI_BIN_PATH"
  printf 'GEMINI_EXEC_PATH=%q\n' "$GEMINI_EXEC_PATH"
} > "$META"
chmod 600 "$META"

cat > "$RUNNER" <<'RUNNER_EOF'
#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/meta.env"

event() {
  local type="$1"; shift
  local message="$*"
  if [ ! -f "$EVENTS_FILE" ]; then
    printf "ts\telapsed_s\tprovider\ttype\tmessage\n" > "$EVENTS_FILE"
    chmod 600 "$EVENTS_FILE"
  fi
  local now elapsed
  now="$(date +%s)"
  elapsed=$(( now - START_EPOCH ))
  printf "%s\t%s\t%s\t%s\t%s\n" "$(date -Iseconds)" "$elapsed" "$PROVIDER" "$type" "$(printf '%s' "$message" | tr '\t\r\n' '   ')" >> "$EVENTS_FILE"
}

valid_report() {
  python3 "$REPORT_VALIDATOR" "$1" "$JOB_ID" "$PROVIDER"
}

write_status() {
  local state="$1" completion="$2" detail="${3:-}"
  local last_line progress_age pane_bytes now
  now="$(date +%s)"
  progress_age=$(( now - $(stat -c %Y "$PROGRESS_FILE" 2>/dev/null || echo "$now") ))
  pane_bytes="$(stat -c %s "$PANE_LOG" 2>/dev/null || echo 0)"
  if [ "$state" = "RUNNING" ] && [ "$progress_age" -gt "$REPORT_STALE_SEC" ]; then
    state="RUNNING_NO_REPORT"
    detail="$detail; progress.md stale for ${progress_age}s"
  fi
  last_line="$(tail -1 "$PANE_LOG" 2>/dev/null | head -c 240 || true)"
  cat > "$STATUS_FILE" <<EOF
# Foreign Aid Live Status

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
STATE: $state
COMPLETION_STATUS: $completion
DETAIL: $detail
UPDATED_AT: $(date -Iseconds)
TIMEOUT_SEC: $TIMEOUT_SEC
PROVIDER_ATTEMPTS_MAX: $PROVIDER_ATTEMPTS_MAX
TMUX_SESSION: $SESSION
REPORT_DIR: $REPORT_DIR
PROGRESS_AGE_SEC: $progress_age
PANE_BYTES: $pane_bytes
LAST_OUTPUT: $last_line

Attach:
\`\`\`bash
tmux attach -t $SESSION
\`\`\`
EOF
  chmod 600 "$STATUS_FILE"
}

run_provider() {
  cd "$REPO"
  case "$PROVIDER" in
    deepseek)
      local key_args=() deepseek_rc
      [ -z "$DEEPSEEK_KEY_FILE" ] || key_args=(--key-file "$DEEPSEEK_KEY_FILE")
      timeout --kill-after=5s "$TIMEOUT_SEC" python3 "$DEEPSEEK_ADAPTER" \
        --bin "$BIN_PATH" --repo "$REPO" --prompt-file "$PROMPT_RUN" --report-dir "$REPORT_DIR" \
        --model "$DEEPSEEK_MODEL" --effort "$DEEPSEEK_EFFORT" --permission-mode "$PERMISSION_MODE" "${key_args[@]}"
      deepseek_rc=$?
      if [ -f "$REPORT_DIR/deepseek-events.jsonl" ]; then
        python3 "$DEEPSEEK_USAGE" --events "$REPORT_DIR/deepseek-events.jsonl" --model "$DEEPSEEK_MODEL" \
          --out "$REPORT_DIR/deepseek-usage.json" || event "usage_unavailable" "DeepSeek usage could not be parsed"
      fi
      return "$deepseek_rc"
      ;;
    codex)
      local permission_args=(-s workspace-write)
      [ "$PERMISSION_MODE" != bypass ] || permission_args=(--dangerously-bypass-approvals-and-sandbox)
      timeout --kill-after=5s "$TIMEOUT_SEC" "$BIN_PATH" exec \
        -m "$CODEX_MODEL" -c model_reasoning_effort="\"$CODEX_EFFORT\"" \
        "${permission_args[@]}" \
        --skip-git-repo-check \
        - < "$PROMPT_RUN"
      ;;
    gemini)
      # Use the official cached OAuth login; inherited API keys must not change billing.
      unset GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT
      unset OPENAI_API_KEY CODEX_API_KEY ANTHROPIC_API_KEY
      python3 - "$PROMPT_RUN" "$REPORT_DIR/prompt.ndjson" <<'PYINPUT'
import json, pathlib, sys
prompt = pathlib.Path(sys.argv[1]).read_text()
pathlib.Path(sys.argv[2]).write_text(json.dumps({"event": "user", "message": {"content": prompt}}) + "\n")
PYINPUT
      local models=("$GEMINI_PRIMARY_MODEL") fallback model safe_model attempt_log rc classification i
      IFS=',' read -r -a fallback <<< "$GEMINI_FALLBACK_MODELS"
      for model in "${fallback[@]}"; do
        [ -n "$model" ] && models+=("$model")
      done

      for i in "${!models[@]}"; do
        model="${models[$i]}"
        safe_model="${model//[^A-Za-z0-9_.-]/_}"
        attempt_log="$REPORT_DIR/gemini-attempt-$((i + 1))-$safe_model.log"
        event "model_attempt" "model=$model attempt=$((i + 1))/${#models[@]}"
        echo "Gemini model attempt $((i + 1))/${#models[@]}: $model"

        set +e
        local permission_args=() model_args=()
        [ "$PERMISSION_MODE" != bypass ] || permission_args=(--dangerously-skip-permissions)
        [ -z "$model" ] || model_args=(--model "$model")
        PATH="$GEMINI_EXEC_PATH" \
          timeout --kill-after=5s "$TIMEOUT_SEC" "$GEMINI_BIN_PATH" \
            "${model_args[@]}" \
            "${permission_args[@]}" \
            --disable-slash-commands \
            --input-format stream-json \
            --output-format stream-json \
            < "$REPORT_DIR/prompt.ndjson" 2>&1 | tee -a "$attempt_log"
        rc=${PIPESTATUS[0]}
        set -e

        if [ "$rc" -eq 0 ]; then
          rm -f "$FINAL_CLASS_FILE"
          event "model_attempt_ok" "model=$model rc=0"
          return 0
        fi

        classification="UNKNOWN"
        if [ -x "$CLASSIFY_SCRIPT" ]; then
          set +e
          "$CLASSIFY_SCRIPT" "$attempt_log" gemini "$rc" > "$REPORT_DIR/gemini-attempt-$((i + 1))-classification.txt"
          set -e
          classification="$(awk -F= '/^classification=/{print $2; exit}' "$REPORT_DIR/gemini-attempt-$((i + 1))-classification.txt" 2>/dev/null || true)"
          [ -n "$classification" ] || classification="UNKNOWN"
          cp "$REPORT_DIR/gemini-attempt-$((i + 1))-classification.txt" "$FINAL_CLASS_FILE"
        fi
        event "model_attempt_fail" "model=$model rc=$rc classification=$classification"

        if [ "$classification" = "QUOTA_EXHAUSTED" ] && [ "$i" -lt "$(( ${#models[@]} - 1 ))" ]; then
          echo "Quota exhausted for $model; falling back to ${models[$((i + 1))]}"
          event "model_fallback" "from=$model to=${models[$((i + 1))]} reason=QUOTA_EXHAUSTED"
          continue
        fi
        return "$rc"
      done
      return 1
      ;;
    claude)
      # Follow the caller's installed CLI; keep explicit executable overrides.
      CLAUDE_BIN="$BIN_PATH"
      if [[ "$(readlink -f "$CLAUDE_BIN" 2>/dev/null || printf '%s' "$CLAUDE_BIN")" == *"claude-clean"* ]]; then
        echo "blocked: resolved claude binary is claude-clean: $CLAUDE_BIN" >&2
        return 64
      fi
      local permission_args=()
      [ "$PERMISSION_MODE" != bypass ] || permission_args=(--dangerously-skip-permissions)
      timeout --kill-after=5s "$TIMEOUT_SEC" "$CLAUDE_BIN" --print \
        --model "$CLAUDE_MODEL" --effort "$CLAUDE_EFFORT" \
        "${permission_args[@]}" \
        --verbose \
        --output-format=stream-json \
        --include-partial-messages \
        --no-session-persistence < "$PROMPT_RUN"
      ;;
  esac
}

write_status "RUNNING" "IN_PROGRESS" "tmux worker started"
case "$PROVIDER" in
  deepseek) event "model_start" "provider=$PROVIDER model=$DEEPSEEK_MODEL effort=$DEEPSEEK_EFFORT" ;;
  codex) event "model_start" "provider=$PROVIDER model=$CODEX_MODEL effort=$CODEX_EFFORT" ;;
  claude) event "model_start" "provider=$PROVIDER model=$CLAUDE_MODEL effort=$CLAUDE_EFFORT" ;;
  *) event "model_start" "provider=$PROVIDER" ;;
esac
(
  while true; do
    sleep "$HEARTBEAT_SEC"
    write_status "RUNNING" "IN_PROGRESS" "heartbeat; provider process still active or session still open"
    event "heartbeat" "tmux session active progress_age=$(($(date +%s) - $(stat -c %Y "$PROGRESS_FILE" 2>/dev/null || date +%s))) pane_bytes=$(stat -c %s "$PANE_LOG" 2>/dev/null || echo 0)"
  done
) &
HB_PID=$!

set +e
run_provider 2>&1 | tee -a "$PANE_LOG"
RC=${PIPESTATUS[0]}
set -e
kill "$HB_PID" >/dev/null 2>&1 || true
wait "$HB_PID" 2>/dev/null || true
printf '%s\n' "$RC" > "$RC_FILE"
event "model_end" "rc=$RC"
touch "$DONE_FILE"

if [ "$RC" -eq 0 ] && valid_report "$RESULT_FILE"; then
  write_status "COMPLETE" "COMPLETE" "completion marker confirmed"
  event "complete_marker_found" "result.md complete"
  exit 0
fi

write_status "INCOMPLETE" "INCOMPLETE" "provider exited rc=$RC without a valid COMPLETE report; retained for ${FAILED_SESSION_TTL_SEC}s"
event "missing_complete_marker" "provider exited rc=$RC; tmux retained for ${FAILED_SESSION_TTL_SEC}s"
{
  echo ""
  echo "=== COMPLETION MARKER MISSING ==="
  echo "result.md does not satisfy the strict COMPLETE report contract"
  echo "This tmux session is retained for ${FAILED_SESSION_TTL_SEC}s for inspection."
  echo "Report directory: $REPORT_DIR"
} | tee -a "$PANE_LOG"

sleep "$FAILED_SESSION_TTL_SEC"
event "retention_expired" "closing incomplete tmux session after ${FAILED_SESSION_TTL_SEC}s"
exit 0
RUNNER_EOF
chmod +x "$RUNNER"

write_status "STARTING" "IN_PROGRESS" "launching tmux session"
event "tmux_start" "session=$SESSION"
TMUX_ENV_ARGS=()
add_tmux_env() {
  local name="$1"
  if [ -n "${!name+x}" ]; then
    TMUX_ENV_ARGS+=(-e "$name=${!name}")
  fi
}
for env_name in \
  PATH HOME USER LOGNAME SHELL LANG LC_ALL LC_CTYPE TERM \
  XDG_CONFIG_HOME XDG_CACHE_HOME XDG_DATA_HOME \
  HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy
do
  add_tmux_env "$env_name"
done
case "$PROVIDER" in
  deepseek)
    TMUX_ENV_ARGS+=(-e "DEEPSEEK_API_KEY=")
    ;;
  codex)
    for env_name in OPENAI_API_KEY CODEX_API_KEY CODEX_HOME; do add_tmux_env "$env_name"; done
    ;;
  gemini)
    # agy uses its own cached Google OAuth credentials, not the Gemini API key.
    :
    ;;
  claude)
    for env_name in ANTHROPIC_API_KEY CLAUDE_CONFIG_DIR CLAUDE_RAW_BIN ANTHROPIC_MODEL; do add_tmux_env "$env_name"; done
    ;;
esac
tmux new-session -d -s "$SESSION" \
  -e "LLM_JOB_ID=$JOB_ID" -e "LLM_REPORT_DIR=$REPORT_DIR" \
  "${TMUX_ENV_ARGS[@]}" "$(printf '%q %q' "$(command -v bash)" "$RUNNER")"

echo "📋 job: $JOB_ID"
echo "📁 report: $REPORT_DIR"
echo "🖥️  tmux: tmux attach -t $SESSION"

last_notice=0
deadline=$(( START_EPOCH + (TIMEOUT_SEC + 5) * PROVIDER_ATTEMPTS_MAX + OUTER_GRACE_SEC ))
while [ ! -f "$DONE_FILE" ]; do
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    sleep 0.1
    [ -f "$DONE_FILE" ] && break
    cp "$RESULT_FILE" "$REPORT_DIR/result.agent.md" 2>/dev/null || true
    cat > "$RESULT_FILE" <<EOF
# Foreign Aid Result

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
COMPLETION_STATUS: FAILED
ERROR_CLASS: TMUX_DIED

## Summary
The tmux session ended before the worker wrote its done marker.

## Work Performed
- Launched tmux session: $SESSION

## Evidence
- status.md: $STATUS_FILE
- events.tsv: $EVENTS_FILE
- pane.log: $PANE_LOG

## Files Changed Or Reviewed
- Unknown; no valid final report was produced.

## Errors Or Blockers
- Tmux session died before completion.

## Next Steps
- Inspect pane.log and events.tsv, then rerun after fixing the underlying provider/tooling issue.
EOF
    chmod 600 "$RESULT_FILE"
    write_status "FAILED" "FAILED" "tmux session died before done marker"
    chmod 400 "$RESULT_FILE" "$STATUS_FILE" 2>/dev/null || true
    event "tmux_died" "session ended without done file"
    echo "🔴 tmux session died before completion; report: $REPORT_DIR" >&2
    exit 6
  fi
  now="$(date +%s)"
  if [ "$now" -gt "$deadline" ]; then
    cp "$RESULT_FILE" "$REPORT_DIR/result.agent.md" 2>/dev/null || true
    cat > "$RESULT_FILE" <<EOF
# Foreign Aid Result

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
COMPLETION_STATUS: FAILED
ERROR_CLASS: OUTER_TIMEOUT

## Summary
The outer caller timed out while the tmux session was still alive and no done marker had appeared.

## Work Performed
- Launched tmux session: $SESSION
- Waited $(( (TIMEOUT_SEC + 5) * PROVIDER_ATTEMPTS_MAX + OUTER_GRACE_SEC )) seconds for the done marker.

## Evidence
- status.md: $STATUS_FILE
- events.tsv: $EVENTS_FILE
- pane.log: $PANE_LOG

## Files Changed Or Reviewed
- Unknown; no valid final report was produced before the outer timeout.

## Errors Or Blockers
- Missing done marker before outer timeout.

## Next Steps
- Attach to tmux for inspection, or kill the session after collecting evidence.
EOF
    chmod 600 "$RESULT_FILE"
    write_status "INCOMPLETE" "INCOMPLETE" "outer timeout; tmux retained for bounded inspection"
    chmod 400 "$RESULT_FILE" "$STATUS_FILE" 2>/dev/null || true
    event "outer_timeout" "deadline=$deadline session=$SESSION"
    echo "🔴 outer timeout; tmux retained temporarily: tmux attach -t $SESSION" >&2
    echo "📁 report: $REPORT_DIR" >&2
    exit 4
  fi
  if [ $(( now - last_notice )) -ge "$HEARTBEAT_SEC" ]; then
    echo "… running: $JOB_ID · report/status.md · attach: tmux attach -t $SESSION"
    last_notice="$now"
  fi
  sleep 2
done

RC="$(cat "$RC_FILE" 2>/dev/null || echo 1)"
if [ "$RC" -eq 0 ] && valid_report "$RESULT_FILE"; then
  write_status "COMPLETE" "COMPLETE" "completion marker confirmed; closing tmux"
  event "tmux_close" "complete marker confirmed"
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  chmod 400 "$RESULT_FILE" "$STATUS_FILE" 2>/dev/null || true
  echo "✅ complete: $REPORT_DIR/result.md"
  exit 0
fi

CLASSIFY="$SCRIPT_DIR/llm-classify.sh"
classification_rc=1
if [ "$PROVIDER" = "gemini" ] && [ -s "$FINAL_CLASS_FILE" ]; then
  cp "$FINAL_CLASS_FILE" "$REPORT_DIR/error_class.txt"
  internal_classification="$(awk -F= '/^classification=/{print $2; exit}' "$REPORT_DIR/error_class.txt" 2>/dev/null || true)"
  classification_rc="$(classification_exit_code "${internal_classification:-UNKNOWN_FAIL}")"
elif [ -x "$CLASSIFY" ]; then
  set +e
  "$CLASSIFY" "$PANE_LOG" "$PROVIDER" "$RC" > "$REPORT_DIR/error_class.txt"
  classification_rc=$?
  set -e
fi
internal_classification="$(awk -F= '/^classification=/{print $2; exit}' "$REPORT_DIR/error_class.txt" 2>/dev/null || true)"
[ -n "$internal_classification" ] || internal_classification="MISSING_COMPLETION_MARKER"
if [ "$internal_classification" = "SUCCESS" ] || [ "$internal_classification" = "SUCCESS_WITH_WARNINGS" ]; then
  internal_classification="MISSING_COMPLETION_MARKER"
fi
classification="$(public_error_class "$internal_classification")"
cp "$RESULT_FILE" "$REPORT_DIR/result.agent.md" 2>/dev/null || true
cat > "$RESULT_FILE" <<EOF
# Foreign Aid Result

JOB_ID: $JOB_ID
PROVIDER: $PROVIDER
COMPLETION_STATUS: FAILED
ERROR_CLASS: $classification

## Summary
The provider failed or produced an invalid report; inspect the preserved result.agent.md and provider exit code.

## Work Performed
- Launched provider in tmux session: $SESSION
- Captured pane output and events under this report directory.

## Evidence
- pane.log: $PANE_LOG
- events.tsv: $EVENTS_FILE
- error_class.txt: $REPORT_DIR/error_class.txt

## Files Changed Or Reviewed
- Unknown; the provider did not produce a valid final report.

## Errors Or Blockers
- Required: zero provider exit AND a valid strict COMPLETE report
- Provider rc: $RC
- Internal classification: $internal_classification
- Public error class: $classification

## Next Steps
- Inspect pane.log and attach to tmux if the session is still open.
- Fix auth/quota/network/tooling issues if shown in error_class.txt, then rerun.
EOF
chmod 600 "$RESULT_FILE"
write_status "FAILED" "FAILED" "provider failure or invalid completion report; tmux retained for ${FAILED_SESSION_TTL_SEC}s; rc=$RC"
chmod 400 "$RESULT_FILE" "$STATUS_FILE" 2>/dev/null || true
event "incomplete_return" "rc=$RC classification_rc=$classification_rc session=$SESSION"
echo "🔴 failed: provider rc=$RC or invalid strict COMPLETE report"
echo "📁 report: $REPORT_DIR"
echo "🖥️  retained ${FAILED_SESSION_TTL_SEC}s: tmux attach -t $SESSION"
echo "📄 classification: $REPORT_DIR/error_class.txt"
if [ "$classification_rc" = "0" ]; then
  classification_rc=8
fi
exit "$classification_rc"
