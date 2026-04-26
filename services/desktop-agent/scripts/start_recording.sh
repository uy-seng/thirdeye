#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FFMPEG_BIN="${FFMPEG_BIN:-ffmpeg}"
JOB_ID="${JOB_ID:?JOB_ID is required}"
OUTPUT_DIR="${OUTPUT_DIR:-/recordings}"
CAPTURE_RUNTIME_DIR="${CAPTURE_RUNTIME_DIR:-/tmp/capture-runtime}"
X11_SOCKET_DIR="${X11_SOCKET_DIR:-/tmp/.X11-unix}"
WIDTH="${RECORDING_WIDTH:-1280}"
HEIGHT="${RECORDING_HEIGHT:-720}"
FPS="${RECORDING_FPS:-15}"

resolve_display_name() {
  if [[ -n "${RECORDING_DISPLAY:-}" ]]; then
    printf '%s' "${RECORDING_DISPLAY}"
    return
  fi

  if [[ -n "${DISPLAY:-}" ]]; then
    local display_number="${DISPLAY#:}"
    display_number="${display_number%%.*}"
    if [[ -S "${X11_SOCKET_DIR}/X${display_number}" ]]; then
      printf ':%s' "${display_number}"
      return
    fi
  fi

  local socket_path
  for socket_path in "${X11_SOCKET_DIR}"/X*; do
    if [[ -S "${socket_path}" ]]; then
      printf ':%s' "${socket_path##*X}"
      return
    fi
  done

  printf '%s' "${DISPLAY:-:0}"
}

DISPLAY_NAME="$(resolve_display_name)"

JOB_DIR="${OUTPUT_DIR}/jobs/${JOB_ID}"
PID_FILE="${CAPTURE_RUNTIME_DIR}/recording.pid"
LOG_FILE="${JOB_DIR}/ffmpeg-recording.log"
OUTPUT_FILE="${JOB_DIR}/recording.mp4"

mkdir -p "${JOB_DIR}" "${CAPTURE_RUNTIME_DIR}"
PULSE_SOURCE="$("${SCRIPT_DIR}/detect_audio_source.sh")"

COMMAND=(
  "${FFMPEG_BIN}"
  -y
  -video_size "${WIDTH}x${HEIGHT}"
  -framerate "${FPS}"
  -f x11grab
  -i "${DISPLAY_NAME}"
  -f pulse
  -i "${PULSE_SOURCE}"
  -c:v libx264
  -preset veryfast
  -pix_fmt yuv420p
  -c:a aac
  -b:a 192k
  "${OUTPUT_FILE}"
)

if [[ "${FAKE_CAPTURE:-0}" == "1" ]]; then
  COMMAND=(
    "${FFMPEG_BIN}"
    -y
    -f lavfi
    -i "color=c=black:s=${WIDTH}x${HEIGHT}:r=${FPS}"
    -f lavfi
    -i "sine=frequency=880:sample_rate=48000"
    -t "${FAKE_CAPTURE_SECONDS:-5}"
    -c:v libx264
    -pix_fmt yuv420p
    -c:a aac
    -b:a 128k
    "${OUTPUT_FILE}"
)
fi

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  python3 - <<'PY' "${OUTPUT_FILE}" "${LOG_FILE}" "${PID_FILE}" "${PULSE_SOURCE}" "${COMMAND[@]}"
import json
import sys

output_file, log_file, pid_file, pulse_source, *command = sys.argv[1:]
print(json.dumps({
    "mode": "dry-run",
    "output_file": output_file,
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
    printf '{"error":"recording_already_running","pid":%s}\n' "${EXISTING_PID}"
    exit 1
  fi
fi

"${COMMAND[@]}" >>"${LOG_FILE}" 2>&1 &
PID="$!"
printf '%s\n' "${PID}" > "${PID_FILE}"

sleep "${RECORDING_STARTUP_GRACE_SECONDS:-1}"
if ! kill -0 "${PID}" >/dev/null 2>&1; then
  set +e
  wait "${PID}"
  EXIT_CODE="$?"
  set -e
  rm -f "${PID_FILE}"
  python3 - <<'PY' "${OUTPUT_FILE}" "${LOG_FILE}" "${EXIT_CODE}"
import json
import pathlib
import sys

output_file, log_file, exit_code = sys.argv[1:]
log_lines: list[str] = []
log_path = pathlib.Path(log_file)
if log_path.exists():
    log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
print(json.dumps({
    "error": "recording_start_failed",
    "output_file": output_file,
    "log_file": log_file,
    "exit_code": int(exit_code),
    "log_tail": "\n".join(log_lines),
}))
PY
  exit 1
fi

python3 - <<'PY' "${OUTPUT_FILE}" "${LOG_FILE}" "${PID_FILE}" "${PULSE_SOURCE}" "${PID}"
import json
import sys

output_file, log_file, pid_file, pulse_source, pid = sys.argv[1:]
print(json.dumps({
    "mode": "started",
    "output_file": output_file,
    "log_file": log_file,
    "pid_file": pid_file,
    "pulse_source": pulse_source,
    "pid": int(pid),
}))
PY
