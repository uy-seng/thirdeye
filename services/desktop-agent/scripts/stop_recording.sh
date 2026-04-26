#!/usr/bin/env bash
set -euo pipefail

JOB_ID="${JOB_ID:?JOB_ID is required}"
OUTPUT_DIR="${OUTPUT_DIR:-/recordings}"
CAPTURE_RUNTIME_DIR="${CAPTURE_RUNTIME_DIR:-/tmp/capture-runtime}"
PID_FILE="${CAPTURE_RUNTIME_DIR}/recording.pid"
OUTPUT_FILE="${OUTPUT_DIR}/jobs/${JOB_ID}/recording.mp4"

if [[ ! -f "${PID_FILE}" ]]; then
  printf '{"mode":"stopped","pid":null,"output_file":"%s","message":"no_pid_file"}\n' "${OUTPUT_FILE}"
  exit 0
fi

PID="$(cat "${PID_FILE}")"
if kill -0 "${PID}" >/dev/null 2>&1; then
  kill -INT "${PID}" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    if ! kill -0 "${PID}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
fi

if kill -0 "${PID}" >/dev/null 2>&1; then
  kill -TERM "${PID}" >/dev/null 2>&1 || true
fi

rm -f "${PID_FILE}"

if [[ ! -f "${OUTPUT_FILE}" ]]; then
  printf '{"error":"recording_missing","pid":%s,"output_file":"%s"}\n' "${PID}" "${OUTPUT_FILE}"
  exit 1
fi

python3 - <<'PY' "${OUTPUT_FILE}" "${PID}"
import json
import os
import sys

output_file, pid = sys.argv[1:]
print(json.dumps({
    "mode": "stopped",
    "pid": int(pid),
    "output_file": output_file,
    "size_bytes": os.path.getsize(output_file),
}))
PY
