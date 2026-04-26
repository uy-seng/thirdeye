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

COOKIE_JAR="$(mktemp)"
trap 'rm -f "${COOKIE_JAR}"' EXIT

curl -fsS "http://127.0.0.1:8788/api/health" >/dev/null
curl -fsS "http://127.0.0.1:8790/health" >/dev/null
DESKTOP_HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:3000/")"
if [[ "${DESKTOP_HTTP_CODE}" != "200" && "${DESKTOP_HTTP_CODE}" != "401" ]]; then
  printf 'Unexpected desktop HTTP status: %s\n' "${DESKTOP_HTTP_CODE}" >&2
  exit 1
fi

if [[ "${SMOKE_TEST_OPENCLAW:-false}" =~ ^(1|true|yes|on)$ ]]; then
  curl -fsS "http://127.0.0.1:18789/healthz" >/dev/null
fi

curl -fsS -c "${COOKIE_JAR}" -o /dev/null \
  -H "content-type: application/json" \
  -X POST \
  -d "{\"username\":\"${CONTROLLER_USERNAME}\",\"password\":\"${CONTROLLER_PASSWORD}\"}" \
  "http://127.0.0.1:8788/api/session/login"

curl -fsS -b "${COOKIE_JAR}" "http://127.0.0.1:8788/api/settings/test/desktop" >/dev/null
curl -fsS -b "${COOKIE_JAR}" "http://127.0.0.1:8788/api/settings/health" >/dev/null

if [[ "${SMOKE_TEST_OPENCLAW:-false}" =~ ^(1|true|yes|on)$ ]]; then
  curl -fsS -b "${COOKIE_JAR}" "http://127.0.0.1:8788/api/settings/test/openclaw" >/dev/null
fi

curl -fsS -b "${COOKIE_JAR}" "http://127.0.0.1:8788/api/settings/test/deepgram" >/dev/null

printf 'Smoke test passed.\n'
