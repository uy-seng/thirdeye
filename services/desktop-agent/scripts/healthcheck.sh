#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8790/health", timeout=3) as response:
    payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "ok":
        raise SystemExit(1)
PY
