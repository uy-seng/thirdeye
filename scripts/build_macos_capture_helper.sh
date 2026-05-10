#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_FILE="${ROOT_DIR}/services/macos-capture-agent/helper/ScreenCaptureKitHelper.swift"
OUTPUT_DIR="${ROOT_DIR}/services/macos-capture-agent/bin"
OUTPUT_FILE="${OUTPUT_DIR}/macos_capture_helper"
SIGNING_IDENTIFIER="${MACOS_CAPTURE_HELPER_IDENTIFIER:-com.thirdeye.macos-capture-helper}"

mkdir -p "${OUTPUT_DIR}"

if ! command -v pkg-config >/dev/null 2>&1 || ! pkg-config speexdsp >/dev/null 2>&1; then
  printf 'Missing SpeexDSP build dependency. Install it with: brew install speexdsp pkg-config\n' >&2
  exit 1
fi

SPEEX_MODULE_DIR="${OUTPUT_DIR}/CSpeexDSP"
SPEEX_INCLUDE_DIR="$(pkg-config --variable=includedir speexdsp)"
mkdir -p "${SPEEX_MODULE_DIR}"
cat > "${SPEEX_MODULE_DIR}/module.modulemap" <<EOF
module CSpeexDSP [system] {
  header "${SPEEX_INCLUDE_DIR}/speex/speex_echo.h"
  export *
}
EOF

IFS=' ' read -r -a SPEEX_CFLAGS <<< "$(pkg-config --cflags speexdsp)"
IFS=' ' read -r -a SPEEX_LIBS <<< "$(pkg-config --libs speexdsp)"

xcrun swiftc \
  -parse-as-library \
  -O \
  -I "${SPEEX_MODULE_DIR}" \
  "${SPEEX_CFLAGS[@]}" \
  -framework AppKit \
  -framework AVFoundation \
  -framework CoreAudio \
  -framework CoreMedia \
  -framework ScreenCaptureKit \
  "${SOURCE_FILE}" \
  "${SPEEX_LIBS[@]}" \
  -o "${OUTPUT_FILE}"

codesign --force --sign - --identifier "${SIGNING_IDENTIFIER}" "${OUTPUT_FILE}"

printf 'Built %s\n' "${OUTPUT_FILE}"
