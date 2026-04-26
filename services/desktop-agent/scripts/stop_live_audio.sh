#!/usr/bin/env bash
set -euo pipefail

CAPTURE_RUNTIME_DIR="${CAPTURE_RUNTIME_DIR:-/tmp/capture-runtime}"
PID_FILE="${CAPTURE_RUNTIME_DIR}/live-audio.pid"
FIFO_PATH="${CAPTURE_RUNTIME_DIR}/live_audio.pcm"

if [[ ! -f "${PID_FILE}" ]]; then
  printf '{"mode":"stopped","pid":null,"fifo_path":"%s","message":"no_pid_file"}\n' "${FIFO_PATH}"
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

rm -f "${PID_FILE}" "${FIFO_PATH}"
printf '{"mode":"stopped","pid":%s,"fifo_path":"%s"}\n' "${PID}" "${FIFO_PATH}"
