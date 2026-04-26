#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${PULSE_SOURCE_OVERRIDE:-}" ]]; then
  printf '%s\n' "${PULSE_SOURCE_OVERRIDE}"
  exit 0
fi

if ! command -v pactl >/dev/null 2>&1; then
  printf 'default.monitor\n'
  exit 0
fi

SOURCE="$(pactl list short sources | awk '
  /\.monitor$/ && /output/ { print $2; exit }
  /\.monitor$/ && first == "" { first = $2 }
  END {
    if (first != "") {
      print first
    }
  }
')"

if [[ -z "${SOURCE}" ]]; then
  SOURCE="$(pactl list short sources | awk 'NR == 1 { print $2 }')"
fi

if [[ -z "${SOURCE}" ]]; then
  printf 'default.monitor\n'
else
  printf '%s\n' "${SOURCE}"
fi
