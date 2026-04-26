from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_macos_capture_agent_uses_thirdeye_service_identity() -> None:
    source = (ROOT / "scripts" / "macos_capture_agent.sh").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "com.thirdeye.macos-capture-agent" in source
    assert 'HELPER_BIN="${MACOS_CAPTURE_HELPER_BIN:-' in source
    assert "com.thirdeye.macos-capture-agent" in makefile
    assert "com.whisper" not in source
    assert "com.whisper" not in makefile


def test_macos_capture_helper_build_uses_stable_thirdeye_signature_identity() -> None:
    source = (ROOT / "scripts" / "build_macos_capture_helper.sh").read_text(encoding="utf-8")
    runtime = (
        ROOT / "services" / "macos-capture-agent" / "src" / "thirdeye_macos_capture" / "agent" / "runtime.py"
    ).read_text(encoding="utf-8")
    tauri_config = (ROOT / "apps" / "tauri" / "tauri.conf.json").read_text(encoding="utf-8")

    assert "com.thirdeye.macos-capture-helper" in source
    assert "codesign" in source
    assert "--identifier" in source
    assert "services/macos-capture-agent/bin/macos_capture_helper" in runtime
    assert "../../services/macos-capture-agent/bin/macos_capture_helper" in tauri_config
    assert "macos_capture/bin/macos_capture_helper" in tauri_config


def test_custom_tauri_dev_script_refreshes_bundled_capture_helper() -> None:
    source = (ROOT / "apps" / "scripts" / "dev.sh").read_text(encoding="utf-8")

    assert 'HELPER_SOURCE="${REPO_ROOT}/services/macos-capture-agent/bin/macos_capture_helper"' in source
    assert 'HELPER_RESOURCE="${TAURI_DIR}/target/debug/macos_capture/bin/macos_capture_helper"' in source
    assert 'cp "${HELPER_SOURCE}" "${HELPER_RESOURCE}"' in source


def test_macos_capture_helper_excludes_thirdeye_ui_from_display_captures() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert 'private let thirdeyeBundleIdentifier = "com.thirdeye.desktop"' in helper
    assert 'private let thirdeyeApplicationName = "thirdeye"' in helper
    assert "let excludedApplications = content.applications.filter(isReliableThirdeyeApplicationExclusion)" in helper
    assert "let exceptingWindows = content.windows.filter(isThirdeyeWindowException)" in helper
    assert "SCContentFilter(display: display, excludingWindows: exceptingWindows)" in helper
    assert "excludingApplications: excludedApplications" in helper
    assert "exceptingWindows: exceptingWindows" in helper
    assert "SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])" not in helper


def test_macos_capture_helper_hides_and_rejects_thirdeye_targets() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert "case protectedApplication" in helper
    assert "thirdeye cannot be recorded" in helper
    assert "throw HelperError.protectedApplication" in helper
    assert "if isThirdeyeApplication(application) {" in helper
    assert "if isThirdeyeApplication(window.owningApplication) {" in helper


def test_macos_capture_helper_lists_displays_apps_and_user_windows() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")
    start = helper.index("func listTargets() async throws")
    end = helper.index("func runStream(command: HelperCommand)", start)
    list_targets_source = helper[start:end]

    assert '"kind": "display"' in list_targets_source
    assert '"kind": "application"' in list_targets_source
    assert '"kind": "window"' in list_targets_source
    assert "for app in selectableApplications" in list_targets_source
    assert "for window in selectableWindows" in list_targets_source
    assert ".filter(isUserSelectableWindow)" in list_targets_source


def test_macos_capture_helper_uses_display_scoped_window_capture_filter() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")
    start = helper.index('case "window":')
    end = helper.index("default:", start)
    window_capture_source = helper[start:end]

    assert "SCContentFilter(desktopIndependentWindow:" not in window_capture_source
    assert "SCContentFilter(display: display, including: [window])" in window_capture_source


def test_macos_capture_helper_filters_noisy_system_windows() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert "private func isUserSelectableWindow(_ window: SCWindow) -> Bool" in helper
    assert '"control center"' in helper
    assert '"dock"' in helper
    assert '"notification center"' in helper
    assert '"wallpaper"' in helper
    assert '"backstop"' in helper
    assert '"menubar"' in helper
    assert '"(control center)"' in helper
    assert "window.frame.width >= 120" in helper
    assert "window.frame.height >= 80" in helper
