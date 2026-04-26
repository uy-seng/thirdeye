#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
fi

mkdir -p \
  "${ROOT_DIR}/runtime/desktop-config" \
  "${ROOT_DIR}/runtime/recordings" \
  "${ROOT_DIR}/runtime/artifacts" \
  "${ROOT_DIR}/runtime/controller" \
  "${ROOT_DIR}/runtime/controller-events"

printf 'Bootstrap complete.\n'
printf 'Next steps:\n'
printf '  1. Edit %s/.env\n' "${ROOT_DIR}"
printf '  2. Run make build && make up to start the Docker desktop stack\n'
printf '  3. Run make up-openclaw when you want the helper gateway (token comes from ~/.openclaw/openclaw.json)\n'
printf '  4. Run make macos-capture-up when you want This Mac capture targets in the background\n'
printf '  5. Run make macos-app-dev to start the native app\n'
printf '  6. Run make smoke once the local API is available on http://127.0.0.1:8788\n'
