#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${RUNTIME_ROOT:-${ROOT_DIR}/runtime}"
SOURCE_DIR="${RUNTIME_ROOT}/artifacts"
DEST="${1:-${ROOT_DIR}/exported-artifacts}"

if [[ ! -d "${SOURCE_DIR}" ]]; then
  printf 'Artifacts source not found: %s\n' "${SOURCE_DIR}" >&2
  exit 1
fi

mkdir -p "${DEST}"
cp -R "${SOURCE_DIR}/." "${DEST}"
printf 'Artifacts exported from %s to %s\n' "${SOURCE_DIR}" "${DEST}"
