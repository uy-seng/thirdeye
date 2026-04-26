#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FFMPEG_BIN="${FFMPEG_BIN:-ffmpeg}"
JOB_ID="${JOB_ID:?JOB_ID is required}"
OUTPUT_DIR="${OUTPUT_DIR:-/recordings}"
CAPTURE_RUNTIME_DIR="${CAPTURE_RUNTIME_DIR:-/tmp/capture-runtime}"

JOB_DIR="${OUTPUT_DIR}/jobs/${JOB_ID}"
PID_FILE="${CAPTURE_RUNTIME_DIR}/live-audio.pid"
FIFO_PATH="${CAPTURE_RUNTIME_DIR}/live_audio.pcm"
LOG_FILE="${JOB_DIR}/ffmpeg-live-audio.log"

mkdir -p "${JOB_DIR}" "${CAPTURE_RUNTIME_DIR}"
PULSE_SOURCE="$("${SCRIPT_DIR}/detect_audio_source.sh")"

COMMAND=(
  "${FFMPEG_BIN}"
  -nostdin
  -f pulse
  -i "${PULSE_SOURCE}"
  -ac 1
  -ar 16000
  -f s16le
  -
)

if [[ "${FAKE_CAPTURE:-0}" == "1" ]]; then
  COMMAND=(
    "${FFMPEG_BIN}"
    -nostdin
    -f lavfi
    -i "sine=frequency=440:sample_rate=16000"
    -ac 1
    -ar 16000
    -f s16le
    -
  )
fi

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  python3 - <<'PY' "${FIFO_PATH}" "${LOG_FILE}" "${PID_FILE}" "${PULSE_SOURCE}" "${COMMAND[@]}"
import json
import sys

fifo_path, log_file, pid_file, pulse_source, *command = sys.argv[1:]
print(json.dumps({
    "mode": "dry-run",
    "fifo_path": fifo_path,
    "log_file": log_file,
    "pid_file": pid_file,
    "pulse_source": pulse_source,
    "command": command,
}))
PY
  exit 0
fi

if [[ -f "${PID_FILE}" ]]; then
  EXISTING_PID="$(cat "${PID_FILE}")"
  if kill -0 "${EXISTING_PID}" >/dev/null 2>&1; then
    printf '{"error":"live_audio_already_running","pid":%s}\n' "${EXISTING_PID}"
    exit 1
  fi
fi

rm -f "${FIFO_PATH}"
mkfifo "${FIFO_PATH}"
"${COMMAND[@]}" >"${FIFO_PATH}" 2>>"${LOG_FILE}" &
PID="$!"
printf '%s\n' "${PID}" > "${PID_FILE}"

python3 - <<'PY' "${FIFO_PATH}" "${LOG_FILE}" "${PID_FILE}" "${PULSE_SOURCE}" "${PID}"
import json
import sys

fifo_path, log_file, pid_file, pulse_source, pid = sys.argv[1:]
print(json.dumps({
    "mode": "started",
    "fifo_path": fifo_path,
    "log_file": log_file,
    "pid_file": pid_file,
    "pulse_source": pulse_source,
    "pid": int(pid),
}))
PY
