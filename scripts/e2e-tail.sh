#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8080}"
LOG_FILE="${LOG_FILE:-/tmp/truthbattle_api.log}"
NONSTREAM_PROMPT="${NONSTREAM_PROMPT:-solve x^2 - 5x + 6 = 0 for x}"
STREAM_PROMPT="${STREAM_PROMPT:-differentiate x^3 + 2x}"
MODEL="${MODEL:-truthbattle-lean-sympy}"

if [[ ! -f "$LOG_FILE" ]]; then
  echo "Log file not found: $LOG_FILE" >&2
  echo "Start the API and set LOG_FILE if needed." >&2
  exit 1
fi

TAIL_CAPTURE="/tmp/truthbattle_tail_capture.log"
NONSTREAM_HEADERS="/tmp/truthbattle_nonstream_headers.log"
STREAM_HEADERS="/tmp/truthbattle_stream_headers.log"
NONSTREAM_BODY="/tmp/truthbattle_nonstream_body.json"
STREAM_BODY="/tmp/truthbattle_stream_body.sse"

: > "$TAIL_CAPTURE"
(tail -n0 -f "$LOG_FILE" > "$TAIL_CAPTURE") &
TAIL_PID=$!
cleanup() {
  kill "$TAIL_PID" >/dev/null 2>&1 || true
  wait "$TAIL_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 0.3

curl -sS -v "$API_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"$NONSTREAM_PROMPT\"}],\"stream\":false}" \
  > "$NONSTREAM_BODY" 2> "$NONSTREAM_HEADERS"

curl -sS -N -v "$API_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"$STREAM_PROMPT\"}],\"stream\":true}" \
  > "$STREAM_BODY" 2> "$STREAM_HEADERS"

sleep 0.5
cleanup

echo "=== NON-STREAM HEADERS ==="
cat "$NONSTREAM_HEADERS"
echo
echo "=== NON-STREAM SUMMARY ==="
python3 - <<'PY'
import json
j=json.load(open("/tmp/truthbattle_nonstream_body.json"))
msg=j["choices"][0]["message"]["content"]
trace=[x["node"] for x in j.get("truthbattle_trace",[])]
print(msg[:700])
print("\nTrace:", trace)
print("Verdict:", j.get("truthbattle_verdict",{}).get("verdict"))
PY
echo
echo "=== STREAM HEADERS ==="
cat "$STREAM_HEADERS"
echo
echo "=== STREAM SSE (first 20 lines) ==="
sed -n '1,20p' "$STREAM_BODY"
echo
echo "=== SERVER TAIL CAPTURE ==="
cat "$TAIL_CAPTURE"
