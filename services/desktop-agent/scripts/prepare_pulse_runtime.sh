#!/usr/bin/env bash
set -euo pipefail

XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/config/.XDG}"
CONTAINER_ENV_DIR="${CONTAINER_ENV_DIR:-/run/s6/container_environment}"
CAPTURE_RUNTIME_DIR="${CAPTURE_RUNTIME_DIR:-/tmp/capture-runtime}"
PULSE_RUNTIME_PATH="${PULSE_RUNTIME_PATH:-/defaults}"
PULSE_SOCKET_TARGET="${PULSE_SOCKET_TARGET:-${PULSE_RUNTIME_PATH}/native}"
ABC_USER="${ABC_USER:-abc}"
ABC_GROUP="${ABC_GROUP:-$(id -gn "${ABC_USER}" 2>/dev/null || printf '%s' "${ABC_USER}")}"
ENABLE_BROWSER_AUDIO_RECOVERY="${ENABLE_BROWSER_AUDIO_RECOVERY:-0}"
RECOVERY_COOLDOWN_SECONDS="${RECOVERY_COOLDOWN_SECONDS:-5}"

XDG_PULSE_DIR="${XDG_RUNTIME_DIR}/pulse"
XDG_PULSE_SOCKET="${XDG_PULSE_DIR}/native"
RECOVERY_STAMP="${CAPTURE_RUNTIME_DIR}/browser-audio-recovery.stamp"
BROWSER_AUDIO_RESTARTED=0

write_container_env() {
  local name="$1"
  local value="$2"
  local target="${CONTAINER_ENV_DIR}/${name}"
  if ! printf '%s' "${value}" > "${target}" 2>/dev/null; then
    return 0
  fi
}

if [[ ! -S "${PULSE_SOCKET_TARGET}" ]]; then
  ALT_SOCKET="$(find /tmp -maxdepth 2 -type s -path '/tmp/pulse-*/native' 2>/dev/null | head -n 1 || true)"
  if [[ -n "${ALT_SOCKET}" ]]; then
    PULSE_SOCKET_TARGET="${ALT_SOCKET}"
  fi
fi

mkdir -p "${XDG_PULSE_DIR}" "${CONTAINER_ENV_DIR}" "${CAPTURE_RUNTIME_DIR}"
if [[ -d "${PULSE_RUNTIME_PATH}" ]]; then
  chown "${ABC_USER}:${ABC_GROUP}" "${PULSE_RUNTIME_PATH}" 2>/dev/null || true
  chmod 700 "${PULSE_RUNTIME_PATH}" 2>/dev/null || true
fi
chown "${ABC_USER}:${ABC_GROUP}" "${XDG_RUNTIME_DIR}" "${XDG_PULSE_DIR}" 2>/dev/null || true

rm -f "${XDG_PULSE_SOCKET}"
ln -s "${PULSE_SOCKET_TARGET}" "${XDG_PULSE_SOCKET}"
chown -h "${ABC_USER}:${ABC_GROUP}" "${XDG_PULSE_SOCKET}" 2>/dev/null || true

write_container_env "PULSE_SERVER" "unix:${PULSE_SOCKET_TARGET}"
write_container_env "PULSE_RUNTIME_PATH" "${PULSE_RUNTIME_PATH}"

has_chromium_client() {
  PULSE_SERVER="unix:${PULSE_SOCKET_TARGET}" pactl list short clients 2>/dev/null | awk '$3 == "chromium" { found = 1 } END { exit found ? 0 : 1 }'
}

if [[ "${ENABLE_BROWSER_AUDIO_RECOVERY}" == "1" ]] && command -v pactl >/dev/null 2>&1; then
  if ! has_chromium_client && pgrep -u "${ABC_USER}" -f '/usr/lib/chromium/chromium' >/dev/null 2>&1; then
    NOW="$(date +%s)"
    LAST_ATTEMPT=0
    if [[ -f "${RECOVERY_STAMP}" ]]; then
      LAST_ATTEMPT="$(cat "${RECOVERY_STAMP}" 2>/dev/null || printf '0')"
    fi
    if (( NOW - LAST_ATTEMPT >= RECOVERY_COOLDOWN_SECONDS )); then
      pkill -u "${ABC_USER}" -f 'audio\.mojom\.AudioService' 2>/dev/null || true
      printf '%s\n' "${NOW}" > "${RECOVERY_STAMP}"
      BROWSER_AUDIO_RESTARTED=1
      for _ in $(seq 1 15); do
        if has_chromium_client; then
          break
        fi
        sleep 0.2
      done
    fi
  fi
fi

python3 - <<'PY' "${PULSE_SOCKET_TARGET}" "${XDG_PULSE_SOCKET}" "${PULSE_RUNTIME_PATH}" "${BROWSER_AUDIO_RESTARTED}"
import json
import sys

pulse_socket, xdg_pulse_socket, pulse_runtime_path, browser_audio_restarted = sys.argv[1:]
print(json.dumps({
    "mode": "prepared",
    "pulse_socket": pulse_socket,
    "xdg_pulse_socket": xdg_pulse_socket,
    "pulse_runtime_path": pulse_runtime_path,
    "browser_audio_restarted": browser_audio_restarted == "1",
}))
PY
