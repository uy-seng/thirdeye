from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_macos_live_audio_fifo_matches_deepgram_linear16_contract() -> None:
    deepgram_client = (
        ROOT / "services" / "controller-api" / "src" / "transcripts" / "deepgram_client.py"
    ).read_text(encoding="utf-8")
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert '"encoding": "linear16"' in deepgram_client
    assert '"sample_rate": 16000' in deepgram_client
    assert '"channels": 1' in deepgram_client
    assert "AVAudioConverter" in helper
    assert ".pcmFormatInt16" in helper
    assert "CMSampleBufferCopyPCMDataIntoAudioBufferList" in helper


def test_macos_helper_uses_core_audio_tap_for_muted_app_capture() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")
    info_plist = (ROOT / "apps" / "tauri" / "Info.plist").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build_macos_capture_helper.sh").read_text(encoding="utf-8")

    assert "import CoreAudio" in helper
    assert "CATapDescription" in helper
    assert "kAudioHardwarePropertyTranslatePIDToProcessObject" in helper
    assert "AudioHardwareCreateProcessTap" in helper
    assert "kAudioAggregateDeviceTapListKey" in helper
    assert "CATapMuteBehavior.muted" in helper
    assert "processTreeProcessIDs(rootedAt: processID)" in helper
    assert "appBundleProcessIDs(rootedAt: processID)" in helper
    assert "bundleIDsInAppBundle(rootedAt: rootProcessID)" in helper
    assert '"\\(bundleID).helper.renderer"' not in helper
    assert "tapDescription.bundleIDs" in helper
    assert "NSAudioCaptureUsageDescription" in info_plist
    assert "-framework CoreAudio" in build_script


def test_macos_helper_includes_known_conferencing_audio_owners_in_muted_tap() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert "relatedAudioOwnerProcessIDs" in helper
    assert "knownAudioOwnerBundleIDs" in helper
    assert '"us.zoom.xos"' in helper
    assert '"zoom.us.ZoomAudioDevice"' in helper
    assert '"com.microsoft.teams2"' in helper
    assert '"com.microsoft.MSTeamsAudioDevice"' in helper
    assert "matching HAL audio driver pids" in helper


def test_macos_helper_prefers_selected_app_pid_for_application_targets() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert "target.app_pid" in helper
    assert "application.processID == targetAppPID" in helper


def test_macos_muted_recording_writes_tap_audio_to_mp4() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert "recordsAudio: recordsAudio && !muteTargetAudio" not in helper
    assert "appendMutedRecordingAudio" in helper
    assert "recordingAudioSampleBuffer" in helper
    assert "CMAudioSampleBufferCreateWithPacketDescriptions" in helper
    assert "CMSampleBufferSetDataBufferFromAudioBufferList" in helper
    assert "CMSampleBufferSetDataReady" in helper
    assert "muted recording audio append failed" in helper


def test_macos_helper_accepts_runtime_mute_commands_without_restarting_capture() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert "--mute-command-file" in helper
    assert "--mute-state-file" in helper
    assert "makeMuteCommandFileWatcher" in helper
    assert "setTargetAudioMuted" in helper
    assert "updateConfiguration" in helper
    assert "startProcessTapAudioCapture" in helper
    assert "stopProcessTapAudioCapture" in helper


def test_macos_runtime_mute_audio_starts_at_current_recording_time() -> None:
    helper = (ROOT / "services" / "macos-capture-agent" / "helper" / "ScreenCaptureKitHelper.swift").read_text(encoding="utf-8")

    assert "latestRecordingPresentationTime" in helper
    assert "mutedRecordingAudioStartTime" in helper
    assert "resetMutedRecordingAudioClock()" in helper
    assert "rememberRecordingPresentationTime(presentationTime)" in helper
    assert "mutedRecordingAudioStartTime = latestRecordingPresentationTime ?? recordingSessionStartTime" in helper
    assert "appendRecordingAudioSample(sampleBuffer)" in helper
    assert "normalizedRecordingAudioBuffer" in helper
    assert "audioInput.append(sampleBuffer)" not in helper
