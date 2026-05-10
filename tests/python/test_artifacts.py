from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jobs.artifacts import ArtifactManager


def test_copy_recording_raises_when_stage_recording_is_missing(settings) -> None:
    artifacts = ArtifactManager(settings)

    with pytest.raises(FileNotFoundError, match="recording stage file is missing"):
        artifacts.copy_recording("job-123")

    assert not (Path(settings.artifacts_root) / "jobs" / "job-123" / "recording.mp4").exists()


def test_mix_recording_with_microphone_replaces_stage_recording_with_mixed_mp4(settings, monkeypatch) -> None:
    artifacts = ArtifactManager(settings)
    stage_recording = artifacts.recording_stage_path("job-123")
    microphone_stage = artifacts.microphone_stage_path("job-123")
    stage_recording.write_bytes(b"video-with-system-audio")
    microphone_stage.write_bytes(b"processed-mic-pcm")
    calls: list[list[str]] = []

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool, timeout: int) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "ffprobe" and "-select_streams" in command:
            return subprocess.CompletedProcess(command, 0, stdout="0\n", stderr="")
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"mixed-video")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="12.0\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    artifacts.mix_recording_with_microphone("job-123")

    assert stage_recording.read_bytes() == b"mixed-video"
    assert any("amix=inputs=2" in " ".join(command) for command in calls)
    assert any("-nostdin" in command for command in calls if command[0] == "ffmpeg")


def test_mix_recording_with_microphone_fails_instead_of_hanging_on_media_timeout(settings, monkeypatch) -> None:
    artifacts = ArtifactManager(settings)
    stage_recording = artifacts.recording_stage_path("job-timeout")
    microphone_stage = artifacts.microphone_stage_path("job-timeout")
    stage_recording.write_bytes(b"video-with-system-audio")
    microphone_stage.write_bytes(b"processed-mic-pcm")

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool, timeout: int) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout="0\n", stderr="")
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="timed out"):
        artifacts.mix_recording_with_microphone("job-timeout")


def test_debug_artifacts_are_registered_from_logs_root(settings) -> None:
    artifacts = ArtifactManager(settings)
    paths = artifacts.job_paths("job-debug")
    paths.transcript_json.write_text('{"segments":[]}\n', encoding="utf-8")

    registered = artifacts.register_file("job-debug", paths.transcript_json, content_type="application/json")

    assert registered.name == "transcript.json"
    assert registered.path == str(paths.logs_root / "transcript.json")
