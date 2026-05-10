#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_FILE="${ROOT_DIR}/services/macos-capture-agent/helper/ScreenCaptureKitHelper.swift"
OUTPUT_DIR="${ROOT_DIR}/services/macos-capture-agent/bin"
OUTPUT_FILE="${OUTPUT_DIR}/macos_capture_helper"
SIGNING_IDENTIFIER="${MACOS_CAPTURE_HELPER_IDENTIFIER:-com.thirdeye.macos-capture-helper}"

mkdir -p "${OUTPUT_DIR}"

xcrun swiftc \
  -parse-as-library \
  -O \
  -framework AppKit \
  -framework AVFoundation \
  -framework CoreAudio \
  -framework CoreMedia \
  -framework ScreenCaptureKit \
  "${SOURCE_FILE}" \
  -o "${OUTPUT_FILE}"

codesign --force --sign - --identifier "${SIGNING_IDENTIFIER}" "${OUTPUT_FILE}"

printf 'Built %s\n' "${OUTPUT_FILE}"
