#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  printf 'Missing .env. Run ./scripts/bootstrap.sh first.\n' >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

curl -fsS "http://127.0.0.1:8788/api/health" >/dev/null
curl -fsS "http://127.0.0.1:8788/api/desktops" >/dev/null

if [[ "${SMOKE_TEST_OPENCLAW:-false}" =~ ^(1|true|yes|on)$ ]]; then
  curl -fsS "http://127.0.0.1:18789/healthz" >/dev/null
fi

printf 'Smoke test passed.\n'
