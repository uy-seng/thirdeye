#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${APP_DIR}/.." && pwd)"
TAURI_DIR="${APP_DIR}/tauri"
APP_BIN="${TAURI_DIR}/target/debug/thirdeye"
HELPER_SOURCE="${REPO_ROOT}/services/macos-capture-agent/bin/macos_capture_helper"
HELPER_RESOURCE="${TAURI_DIR}/target/debug/macos_capture/bin/macos_capture_helper"
IDENTIFIER="${THIRDEYE_MACOS_IDENTIFIER:-com.thirdeye.desktop}"
VITE_PID=""

cleanup() {
  if [[ -n "${VITE_PID}" ]]; then
    kill "${VITE_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

cd "${REPO_ROOT}"
./scripts/build_macos_capture_helper.sh

cd "${APP_DIR}"
npm run ui:dev &
VITE_PID="$!"

cd "${TAURI_DIR}"
DEP_TAURI_DEV=true cargo build
mkdir -p "$(dirname "${HELPER_RESOURCE}")"
cp "${HELPER_SOURCE}" "${HELPER_RESOURCE}"
codesign --force --sign - --identifier "${THIRDEYE_MACOS_IDENTIFIER:-com.thirdeye.desktop}" "${APP_BIN}"

THIRDEYE_REPO_ROOT="${REPO_ROOT}" "${APP_BIN}"
