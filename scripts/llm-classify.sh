#!/bin/bash
# llm-classify.sh — 外部 LLM wrapper 共用的失败分类
# 用法: bash llm-classify.sh <log-file> <provider:codex|gemini|claude> <rc>
#
# 输出格式（stdout，给 cc 读）:
#   classification=<CATEGORY>
#   provider=<openai|gemini|unknown>
#   reason=<人话原因>
#   suggestion=<下一步该做啥>
#   trigger_line=<匹配的原始行>
#
# 退出码:
#   0 = SUCCESS（没检出错误）
#   1 = QUOTA_EXHAUSTED / RATE_LIMIT
#   2 = AUTH / PERMISSION
#   3 = NETWORK / PROXY
#   4 = TIMEOUT
#   5 = SILENT_FAIL（codex 0-token 静默退出）
#   6 = MODEL_REJECT（model 不支持 / model not found）
#   7 = UNKNOWN_FAIL（rc!=0 但没匹配任何模式）
#   8 = TOOLING / wrapper or CLI argument error

LOG="${1:?用法: llm-classify.sh <log> <codex|gemini|claude> <rc>}"
PROVIDER="${2:-unknown}"
RC="${3:-0}"

[ ! -f "$LOG" ] && { echo "classification=NO_LOG"; exit 7; }

emit() {
  echo "classification=$1"
  echo "provider=$PROVIDER"
  echo "reason=$2"
  echo "suggestion=$3"
  [ -n "$4" ] && echo "trigger_line=$4"
}

QUOTA_RE="rate.?limit|quota.*(exhausted|exceeded|limit|insufficient)|RESOURCE_EXHAUSTED|usage.?limit|limit.?reached|too.?many.?requests|capacity.*(exhausted|available)|no capacity available|MODEL_CAPACITY_EXHAUSTED|insufficient.?(quota|credits|balance)|payment.?required|out.?of.?credit|credit.?balance|billing|\b429\b|\b402\b"

RAW_SCAN_LOG="$(mktemp)"
SCAN_LOG="$(mktemp)"
trap 'rm -f "$RAW_SCAN_LOG" "$SCAN_LOG"' EXIT
awk '
  /^---$/ { seen_marker=1; next }
  seen_marker { print }
' "$LOG" > "$RAW_SCAN_LOG"
if [ ! -s "$RAW_SCAN_LOG" ]; then
  cp "$LOG" "$RAW_SCAN_LOG"
fi

# Streamed assistant/tool records can contain prompts or source code with strings such as
# 401, 429, and "invalid token". They are task data, not provider diagnostics.
if [ "$PROVIDER" = "gemini" ]; then
  python3 - "$RAW_SCAN_LOG" "$SCAN_LOG" <<'PYSCAN'
import json, pathlib, sys
lines = []
for line in pathlib.Path(sys.argv[1]).read_text(errors="replace").splitlines():
    try:
        item = json.loads(line)
    except ValueError:
        lines.append(line)
        continue
    if not isinstance(item, dict):
        continue
    if item.get("event") == "result":
        # Agent prose can quote error strings. Only the provider's error is diagnostic.
        error = item.get("result", {}).get("error")
        if error:
            lines.append(str(error))
    elif item.get("event") in ("init", "step_update"):
        continue
    elif item.get("type") not in ("message", "tool_use", "tool_result", "assistant", "user", "stream_event"):
        lines.append(line)
pathlib.Path(sys.argv[2]).write_text("\n".join(lines))
PYSCAN
elif [ "$PROVIDER" = "claude" ]; then
  awk '!/^\{"type":"(message|tool_use|tool_result|assistant|user|stream_event)"/' \
    "$RAW_SCAN_LOG" > "$SCAN_LOG"
else
  cp "$RAW_SCAN_LOG" "$SCAN_LOG"
fi

# ---- SUCCESS / SILENT_FAIL ----
# rc=0 logs often contain copied source text, prompts, or reviewer prose with words like
# 401/403/timeout. Do not classify those as provider failures after a clean exit.
if [ "$RC" = "0" ]; then
  if [ "$PROVIDER" = "codex" ]; then
    SILENT=0
    if grep -qiE "tokens? used:?\s+0\s*$" "$SCAN_LOG"; then
      SILENT=1
    fi
    if [ "$SILENT" = "0" ] && awk '
        /tokens used$/ { getline next_line; if (next_line ~ /^[[:space:]]*0[[:space:]]*$/) { print "match"; exit } }
      ' "$SCAN_LOG" | grep -q match; then
      SILENT=1
    fi
    if [ "$SILENT" = "1" ]; then
      emit "SILENT_FAIL" \
        "codex 0-token 静默退出（见 share-external-llm SKILL.md §长论文审稿失败模式 #5）" \
        "改用 reviewer sub-agent（general-purpose），别再修 codex prompt" \
        "$(grep -iE 'tokens? used' "$SCAN_LOG" | head -1)"
      exit 5
    fi
    if ! grep -qiE "tokens? used|^codex$|assistant" "$SCAN_LOG"; then
      emit "SILENT_FAIL" \
        "codex 无任何输出退出" \
        "改用 sub-agent" \
        "$(tail -3 "$LOG" | tr '\n' ' | ')"
      exit 5
    fi
  fi
  TRIG=$(grep -iE "$QUOTA_RE" "$SCAN_LOG" | head -1)
  if [ -n "$TRIG" ]; then
    PORTAL=""
    case "$PROVIDER" in
      codex)  PORTAL="platform.openai.com/usage" ;;
      gemini) PORTAL="agy -p /usage（会员额度）" ;;
      claude) PORTAL="console.anthropic.com / claude.ai 账号额度" ;;
    esac
    emit "SUCCESS_WITH_WARNINGS" \
      "调用完成，但日志中出现限流/额度/容量告警（可能是 CLI 重试后成功）" \
      "本次结果可用；后续同类任务若失败，等一会儿或看 $PORTAL" \
      "$TRIG"
    exit 0
  fi
  emit "SUCCESS" "调用正常完成" "" ""
  exit 0
fi

# ---- AUTH / PERMISSION ----
TRIG=$(grep -iE "PERMISSION_DENIED|UNAUTHENTICATED|FatalAuthenticationError|Error authenticating|Manual authorization is required|current session is non-interactive|provide a GEMINI_API_KEY|Application Default Credentials|invalid.?api.?key|invalid.?token|expired.?token|not.?authenticated|authentication required|please.?(re)?login|\b401\b|\b403\b" "$SCAN_LOG" | head -1)
if [ -n "$TRIG" ]; then
  emit "AUTH" \
    "认证/权限失败（token 失效 / 未登录 / 区域被封）" \
    "使用 provider CLI 重新登录，并检查当前账户权限与自定义端点设置" \
    "$TRIG"
  exit 2
fi

# ---- QUOTA / RATE LIMIT ----
TRIG=$(grep -iE "$QUOTA_RE" "$SCAN_LOG" | head -1)
if [ -n "$TRIG" ]; then
  PORTAL=""
  case "$PROVIDER" in
    codex)  PORTAL="platform.openai.com/usage" ;;
    gemini) PORTAL="agy -p /usage（会员额度）" ;;
    claude) PORTAL="console.anthropic.com / claude.ai 账号额度" ;;
  esac
  emit "QUOTA_EXHAUSTED" \
    "限流/额度/模型容量耗尽" \
    "等一会儿重试 / 看 $PORTAL / 必要时换 provider 或充值" \
    "$TRIG"
  exit 1
fi

# ---- MODEL_REJECT ----
TRIG=$(grep -iE "model.?(is.?)?not.?supported|model.?not.?found|unknown.?model|unsupported.?model|invalid.?model|model.?does.?not.?exist" "$SCAN_LOG" | head -1)
if [ -n "$TRIG" ]; then
  emit "MODEL_REJECT" \
    "模型名错 / 账户不支持指定模型" \
    "检查外援 wrapper 的显式模型链和当前账户可用模型" \
    "$TRIG"
  exit 6
fi

# ---- TOOLING / CLI ARGUMENT ERROR ----
TRIG=$(grep -iE "blocked: .*dangerously|requires --verbose|unknown option|unrecognized option|invalid option|invalid approval mode|usage: .*claude|usage: .*gemini|usage: .*agy|usage: .*codex|bad provider|prompt file not found|tmux session died" "$SCAN_LOG" | head -1)
if [ -n "$TRIG" ]; then
  emit "TOOLING" \
    "wrapper/CLI 参数或运行方式错误" \
    "修 wrapper 参数或 provider CLI 调用方式后重试" \
    "$TRIG"
  exit 8
fi

# ---- NETWORK / PROXY ----
TRIG=$(grep -iE "ECONNREFUSED|EAI_AGAIN|ENETUNREACH|ETIMEDOUT|EHOSTUNREACH|getaddrinfo|connection.?refused|connection.?reset|TLS.?handsh|SSL.?handsh|proxy.?(error|refused)|tunnel.?(failed|error)|certificate.?(verify|error)|\b502\b|\b503\b|\b504\b" "$SCAN_LOG" | head -1)
if [ -n "$TRIG" ]; then
  emit "NETWORK" \
    "网络/代理失败（上游 5xx / TLS / DNS）" \
    "检查调用者配置的代理与服务端点" \
    "$TRIG"
  exit 3
fi

# ---- TIMEOUT fallback ----
if [ "$RC" = "124" ]; then
  EVENTS="${LOG%.log}.events.tsv"
  HEARTBEAT=""
  if [ -f "$EVENTS" ]; then
    HEARTBEAT="$(awk -F '\t' '$4 == "heartbeat" { last=$5 } END { print last }' "$EVENTS" | head -c 220)"
  fi
  if [ -n "$HEARTBEAT" ]; then
    emit "TIMEOUT" \
      "$PROVIDER 被外层 timeout 强杀；最后心跳显示: $HEARTBEAT" \
      "看事件线: bash llm-tail.sh --events $(basename "$LOG" .log | sed 's/^llm-job-//')；若 alive=1 且有 CPU, 可加大 timeout 或拆小包" \
      "$(tail -3 "$LOG" | tr '\n' ' | ')"
    exit 4
  fi
  emit "TIMEOUT" \
    "$PROVIDER 被外层 timeout 强杀" \
    "缩小任务范围 / CODEX_TIMEOUT=1200 cask ... / GEMINI_TIMEOUT=1200 gask ... / CLAUDE_TIMEOUT=1200 claude-ask ...；也可看事件线确认是否仍在做事" \
    "$(tail -3 "$LOG" | tr '\n' ' | ')"
  exit 4
fi

# ---- 非 0 退出但没匹配任何模式 ----
if [ "$RC" != "0" ]; then
  TRIG=$(grep -iE "^Error|FATAL|Killed|panic|traceback|exception" "$SCAN_LOG" | head -1)
  emit "UNKNOWN_FAIL" \
    "退出码 $RC，未匹配已知失败模式" \
    "看完整 log: $LOG" \
    "${TRIG:-$(tail -3 "$LOG" | tr '\n' ' | ')}"
  exit 7
fi

# ---- 未知干净退出路径 ----
emit "SUCCESS" "调用正常完成" "" ""
exit 0
