#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_CONFIG_FILE="${HOME}/.openclaw/openclaw.json"
RESTART_GATEWAY=false

ensure_responses_route() {
  if [[ ! -f "${HOST_CONFIG_FILE}" ]]; then
    return
  fi

  python3 - "$HOST_CONFIG_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
raw = path.read_text(encoding="utf-8")


def parse_config(text):
    try:
        return json.loads(text), False
    except json.JSONDecodeError:
        repaired = text
        while repaired.endswith("\\n"):
            repaired = repaired[:-2] + "\n"
        if repaired == text:
            raise
        return json.loads(repaired), True

payload, repaired = parse_config(raw)
if repaired:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

gateway = payload.setdefault("gateway", {})
http = gateway.setdefault("http", {})
endpoints = http.setdefault("endpoints", {})
responses = endpoints.setdefault("responses", {})
responses["enabled"] = True

path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

usage() {
  cat <<'EOF'
Usage: ./scripts/remediate_openclaw_gateway.sh [--restart]

Resolve the Docker OpenClaw gateway token from ~/.openclaw/openclaw.json
without calling any remote services.

Behavior:
  1. Read gateway.auth.token from ~/.openclaw/openclaw.json.
  2. Print the tokenized dashboard URL for the Docker helper gateway.
  3. Optionally stop any host OpenClaw gateway and recreate the Docker helper.

Options:
  --restart  Stop any host OpenClaw gateway on port 18789 and recreate the
             Docker OpenClaw service.
  -h, --help Show this help text.
EOF
}

is_placeholder_token() {
  case "${1:-}" in
    ""|"replace-with-long-random-token"|"change-me"|"change-me-now")
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

read_host_token() {
  if [[ ! -f "${HOST_CONFIG_FILE}" ]]; then
    return 0
  fi

  python3 - "${HOST_CONFIG_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

token = (((payload.get("gateway") or {}).get("auth") or {}).get("token") or "")
if isinstance(token, str):
    print(token)
PY
}

restart_gateway() {
  if command -v openclaw >/dev/null 2>&1; then
    openclaw gateway stop >/dev/null 2>&1 || true
  fi

  (
    cd "${ROOT_DIR}"
    docker compose -f infra/compose.yaml --profile openclaw up -d --force-recreate --no-deps openclaw
  )
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart)
      RESTART_GATEWAY=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

ensure_responses_route

host_token="$(read_host_token || true)"
if is_placeholder_token "${host_token}"; then
  printf 'Unable to read a usable gateway token from %s\n' "${HOST_CONFIG_FILE}" >&2
  printf 'Run `openclaw configure` or fix your host OpenClaw config, then retry.\n' >&2
  exit 1
fi

resolved_token="${host_token}"

if [[ "${RESTART_GATEWAY}" == true ]]; then
  restart_gateway
fi

printf 'Resolved gateway token from %s\n' "${HOST_CONFIG_FILE}"
printf 'Dashboard URL: http://127.0.0.1:18789/#token=%s\n' "${resolved_token}"
