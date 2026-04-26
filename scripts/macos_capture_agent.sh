#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="${MACOS_CAPTURE_LABEL:-com.thirdeye.macos-capture-agent}"
HOST="${MACOS_CAPTURE_HOST:-127.0.0.1}"
PORT="${MACOS_CAPTURE_PORT:-8791}"
RUNTIME_ROOT="${RUNTIME_ROOT:-${ROOT_DIR}/runtime}"
RUNTIME_DIR="${MACOS_CAPTURE_RUNTIME_DIR:-${RUNTIME_ROOT}/macos-capture-runtime}"
LOG_DIR="${MACOS_CAPTURE_LOG_DIR:-${RUNTIME_ROOT}/logs}"
PLIST="${MACOS_CAPTURE_PLIST:-${RUNTIME_ROOT}/macos-capture-agent.plist}"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
HELPER_BIN="${MACOS_CAPTURE_HELPER_BIN:-${ROOT_DIR}/services/macos-capture-agent/bin/macos_capture_helper}"
PYTHONPATH_DIRS="${ROOT_DIR}/services/controller-api/src:${ROOT_DIR}/services/desktop-agent/src:${ROOT_DIR}/services/macos-capture-agent/src:${ROOT_DIR}/packages"
LOG_FILE="${LOG_DIR}/macos-capture-agent.log"
DOMAIN="gui/$(id -u)"

usage() {
  cat <<USAGE
Usage: $0 <up|status|down|logs|permissions>

Commands:
  up           Start the macOS capture agent as a user launchctl service.
  status       Show service, port, health, and target endpoint status.
  down         Stop the service and remove its generated plist.
  logs         Follow the agent log.
  permissions  Open macOS Screen & System Audio Recording settings.
USAGE
}

require_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    printf 'macOS capture is only available on macOS.\n' >&2
    exit 1
  fi
}

require_runtime() {
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    printf 'Missing virtualenv Python at %s. Run ./scripts/bootstrap.sh first.\n' "${PYTHON_BIN}" >&2
    exit 1
  fi
  if [[ ! -x "${HELPER_BIN}" ]]; then
    printf 'Missing macOS capture helper at %s. Run make macos-capture-build first.\n' "${HELPER_BIN}" >&2
    exit 1
  fi
}

write_plist() {
  mkdir -p "${RUNTIME_DIR}" "${LOG_DIR}" "$(dirname "${PLIST}")"
  cat >"${PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>-m</string>
    <string>uvicorn</string>
    <string>thirdeye_macos_capture.agent.main:app</string>
    <string>--host</string>
    <string>${HOST}</string>
    <string>--port</string>
    <string>${PORT}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>MACOS_CAPTURE_RUNTIME_DIR</key>
    <string>${RUNTIME_DIR}</string>
    <key>MACOS_CAPTURE_HELPER_BIN</key>
    <string>${HELPER_BIN}</string>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>PYTHONPATH</key>
    <string>${PYTHONPATH_DIRS}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_FILE}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_FILE}</string>
</dict>
</plist>
PLIST
}

is_loaded() {
  launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1
}

bootout() {
  launchctl bootout "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
  if [[ -f "${PLIST}" ]]; then
    launchctl bootout "${DOMAIN}" "${PLIST}" >/dev/null 2>&1 || true
  fi
}

wait_for_health() {
  for _ in {1..20}; do
    if curl -fsS --max-time 1 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

up() {
  require_macos
  require_runtime
  write_plist
  bootout
  launchctl bootstrap "${DOMAIN}" "${PLIST}"
  launchctl kickstart -k "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
  if wait_for_health; then
    printf 'macOS capture agent is running at http://%s:%s\n' "${HOST}" "${PORT}"
    printf 'Log: %s\n' "${LOG_FILE}"
  else
    printf 'macOS capture agent did not become healthy. Check %s\n' "${LOG_FILE}" >&2
    exit 1
  fi
}

status() {
  require_macos
  local target_body target_code target_error target_output

  printf 'Label: %s\n' "${LABEL}"
  printf 'Plist: %s\n' "${PLIST}"
  printf 'Log: %s\n' "${LOG_FILE}"
  printf 'Helper: %s\n' "${HELPER_BIN}"

  if is_loaded; then
    printf 'launchctl: loaded\n'
  else
    printf 'launchctl: not loaded\n'
  fi

  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'port: listening on %s:%s\n' "${HOST}" "${PORT}"
  else
    printf 'port: not listening on %s:%s\n' "${HOST}" "${PORT}"
  fi

  if health="$(curl -fsS --max-time 3 "http://${HOST}:${PORT}/health" 2>&1)"; then
    printf 'health: %s\n' "${health}"
  else
    printf 'health: unavailable (%s)\n' "${health}"
  fi

  target_body="$(mktemp)"
  target_error="$(mktemp)"
  target_code="$(curl -sS --max-time 5 -o "${target_body}" -w '%{http_code}' "http://${HOST}:${PORT}/targets" 2>"${target_error}" || true)"
  target_output="$(cat "${target_body}")"
  if [[ "${target_code}" == "200" ]]; then
    target_count="$(printf '%s' "${target_output}" | "${PYTHON_BIN}" -c 'import json, sys; print(len(json.load(sys.stdin).get("targets", [])))' 2>/dev/null || printf 'unknown')"
    printf 'targets: %s available\n' "${target_count}"
  else
    if [[ -n "${target_output}" ]]; then
      printf 'targets: unavailable (HTTP %s %s)\n' "${target_code}" "${target_output}"
    else
      printf 'targets: unavailable (%s)\n' "$(cat "${target_error}")"
    fi
    if [[ "${target_output}" == *"screen_recording_permission_denied"* ]]; then
      printf 'permission: run make macos-capture-permissions, allow thirdeye in Screen & System Audio Recording when using the app, then run make macos-capture-status again.\n'
    fi
  fi
  rm -f "${target_body}" "${target_error}"
}

down() {
  require_macos
  bootout
  rm -f "${PLIST}"
  printf 'macOS capture agent stopped.\n'
}

logs() {
  mkdir -p "${LOG_DIR}"
  touch "${LOG_FILE}"
  tail -f "${LOG_FILE}"
}

permissions() {
  require_macos
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
  printf 'Opened macOS Screen & System Audio Recording settings. Allow thirdeye when using the app, then run make macos-capture-status.\n'
}

command="${1:-}"
case "${command}" in
  up)
    up
    ;;
  status)
    status
    ;;
  down)
    down
    ;;
  logs)
    logs
    ;;
  permissions)
    permissions
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
