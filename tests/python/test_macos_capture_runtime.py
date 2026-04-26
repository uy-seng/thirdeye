from __future__ import annotations

import os
import signal
import stat
import textwrap
import asyncio
from pathlib import Path

import pytest

from thirdeye_macos_capture.agent.runtime import MacOSCaptureRuntime, MacOSCaptureRuntimeError


def test_stop_process_waits_for_started_helper_without_sigkill(tmp_path: Path, monkeypatch) -> None:
    helper = tmp_path / "helper.py"
    marker = tmp_path / "stopped.txt"
    helper.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import signal
            import sys
            import time
            from pathlib import Path

            marker = Path({str(marker)!r})

            def stop(signum, frame):
                marker.write_text("stopped", encoding="utf-8")
                sys.exit(0)

            signal.signal(signal.SIGINT, stop)

            while True:
                time.sleep(0.05)
            """
        ),
        encoding="utf-8",
    )
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("MACOS_CAPTURE_STOP_TIMEOUT_SECONDS", "0.2")

    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    runtime.helper_bin = helper
    pid_file = tmp_path / "recording.pid"
    log_file = tmp_path / "recording.log"
    sent_signals: list[int] = []
    real_kill = os.kill

    def recording_kill(pid: int, sig: int) -> None:
        sent_signals.append(sig)
        real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", recording_kill)

    runtime._start_long_running_helper(["record"], pid_file, log_file)

    pid = runtime._stop_process_from_pid_file(pid_file)

    assert pid is not None
    assert signal.SIGINT in sent_signals
    assert signal.SIGKILL not in sent_signals
    assert marker.read_text(encoding="utf-8") == "stopped"
    assert not pid_file.exists()


def test_async_recording_start_preserves_helper_signal_handling(tmp_path: Path, monkeypatch) -> None:
    helper = tmp_path / "helper.py"
    marker = tmp_path / "stopped.txt"
    helper.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import signal
            import sys
            import time
            from pathlib import Path

            marker = Path({str(marker)!r})

            def stop(signum, frame):
                marker.write_text("stopped", encoding="utf-8")
                sys.exit(0)

            signal.signal(signal.SIGINT, stop)

            while True:
                time.sleep(0.05)
            """
        ),
        encoding="utf-8",
    )
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("MACOS_CAPTURE_STOP_TIMEOUT_SECONDS", "0.2")

    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    runtime.helper_bin = helper
    sent_signals: list[int] = []
    real_kill = os.kill

    def recording_kill(pid: int, sig: int) -> None:
        sent_signals.append(sig)
        real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", recording_kill)

    asyncio.run(
        runtime.start_recording(
            "job-123",
            str(tmp_path / "recording.mp4"),
            {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
        )
    )
    asyncio.run(
        runtime.stop_recording(
            "job-123",
            str(tmp_path / "recording.mp4"),
            {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
        )
    )

    assert signal.SIGKILL not in sent_signals
    assert marker.read_text(encoding="utf-8") == "stopped"


def test_stop_process_raises_when_started_helper_exits_with_error(tmp_path: Path, monkeypatch) -> None:
    helper = tmp_path / "helper.py"
    stop_file = tmp_path / "recording.stop"
    helper.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import sys
            import time
            from pathlib import Path

            stop_file = Path({str(stop_file)!r})

            while not stop_file.exists():
                time.sleep(0.05)

            print("recording finalization failed", file=sys.stderr)
            sys.exit(1)
            """
        ),
        encoding="utf-8",
    )
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("MACOS_CAPTURE_STOP_TIMEOUT_SECONDS", "1.0")

    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    runtime.helper_bin = helper
    pid_file = tmp_path / "recording.pid"
    log_file = tmp_path / "recording.log"

    runtime._start_long_running_helper(["record"], pid_file, log_file)

    with pytest.raises(MacOSCaptureRuntimeError, match="recording finalization failed"):
        runtime._stop_process_from_pid_file(pid_file)

    assert not pid_file.exists()
    assert not stop_file.exists()


def test_run_helper_json_times_out_and_stops_stuck_helper(tmp_path: Path, monkeypatch) -> None:
    helper = tmp_path / "helper.py"
    pid_file = tmp_path / "helper.pid"
    helper.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import os
            import time
            from pathlib import Path

            Path({str(pid_file)!r}).write_text(str(os.getpid()), encoding="utf-8")
            time.sleep(30)
            """
        ),
        encoding="utf-8",
    )
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("MACOS_CAPTURE_HELPER_TIMEOUT_SECONDS", "1.0")

    runtime = MacOSCaptureRuntime()
    runtime.helper_bin = helper

    with pytest.raises(MacOSCaptureRuntimeError, match="timed out"):
        runtime._run_helper_json(["targets"])

    helper_pid = int(pid_file.read_text(encoding="utf-8"))
    assert not runtime._pid_is_running(helper_pid)


def test_list_targets_keeps_displays_applications_and_windows(monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()

    monkeypatch.setattr(
        runtime,
        "_run_helper_json",
        lambda args: {
            "targets": [
                {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
                {
                    "id": "application:notes",
                    "kind": "application",
                    "label": "Notes",
                    "app_bundle_id": "com.apple.Notes",
                    "app_name": "Notes",
                    "app_pid": 4242,
                },
                {
                    "id": "window:notes-1",
                    "kind": "window",
                    "label": "Notes",
                    "app_bundle_id": "com.apple.Notes",
                    "app_name": "Notes",
                    "app_pid": 4242,
                    "window_id": "notes-1",
                },
            ]
        },
    )

    assert asyncio.run(runtime.list_targets()) == [
        {
            "id": "display:1",
            "kind": "display",
            "label": "Display 1",
            "app_bundle_id": None,
            "app_name": None,
            "app_pid": None,
            "window_id": None,
            "display_id": "1",
        },
        {
            "id": "application:notes",
            "kind": "application",
            "label": "Notes",
            "app_bundle_id": "com.apple.Notes",
            "app_name": "Notes",
            "app_pid": 4242,
            "window_id": None,
            "display_id": None,
        },
        {
            "id": "window:notes-1",
            "kind": "window",
            "label": "Notes",
            "app_bundle_id": "com.apple.Notes",
            "app_name": "Notes",
            "app_pid": 4242,
            "window_id": "notes-1",
            "display_id": None,
        },
    ]


def test_start_recording_uses_recording_helper(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    captured: dict[str, object] = {}

    def fake_start(
        args: list[str],
        pid_file: Path,
        log_file: Path,
        startup_grace_seconds: float | None = None,
    ) -> None:
        captured["args"] = args
        captured["pid_file"] = pid_file
        captured["log_file"] = log_file
        pid_file.write_text("1234", encoding="utf-8")

    monkeypatch.setattr(runtime, "_start_long_running_helper", fake_start)

    payload = asyncio.run(
        runtime.start_recording(
            "job-123",
            str(tmp_path / "recording.mp4"),
            {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
        )
    )

    assert captured["args"] == [
        "record",
        "--output-file",
        str(tmp_path / "recording.mp4"),
        "--fifo-path",
        str(tmp_path / "live_audio.pcm"),
        "--stop-file",
        str(tmp_path / "recording.stop"),
        "--mute-command-file",
        str(tmp_path / "recording.mute-command.json"),
        "--mute-state-file",
        str(tmp_path / "recording.mute-state.json"),
        "--target-json",
        '{"id":"display:1","kind":"display","label":"Display 1","app_bundle_id":null,"app_name":null,"app_pid":null,"window_id":null,"display_id":"1"}',
    ]
    assert captured["pid_file"] == tmp_path / "recording.pid"
    assert payload["pid"] == 1234


def test_start_recording_passes_muted_app_audio_flag_to_helper(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    captured: dict[str, object] = {}

    def fake_start(
        args: list[str],
        pid_file: Path,
        log_file: Path,
        startup_grace_seconds: float | None = None,
    ) -> None:
        captured["args"] = args
        pid_file.write_text("1234", encoding="utf-8")

    monkeypatch.setattr(runtime, "_start_long_running_helper", fake_start)

    asyncio.run(
        runtime.start_recording(
            "job-123",
            str(tmp_path / "recording.mp4"),
            {
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
            },
            mute_target_audio=True,
        )
    )

    assert "--mute-target-audio" in captured["args"]


def test_start_live_audio_reuses_recording_helper_fifo(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    recording_pid = os.getpid()
    (tmp_path / "recording.pid").write_text(str(recording_pid), encoding="utf-8")
    captured: list[object] = []

    def fake_start(
        args: list[str],
        pid_file: Path,
        log_file: Path,
        startup_grace_seconds: float | None = None,
    ) -> None:
        captured.append((args, pid_file, log_file, startup_grace_seconds))

    monkeypatch.setattr(runtime, "_start_long_running_helper", fake_start)

    payload = asyncio.run(
        runtime.start_live_audio(
            "job-123",
            {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
        )
    )

    assert captured == []
    assert payload == {"pid": recording_pid, "fifo_path": str(tmp_path / "live_audio.pcm"), "log_file": str(tmp_path / "recording.log")}
    assert (tmp_path / "live-audio.pid").read_text(encoding="utf-8") == str(recording_pid)
    assert (tmp_path / "live-audio.reused-recording").read_text(encoding="utf-8") == str(recording_pid)


def test_stop_live_audio_keeps_reused_recording_helper_running(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    recording_pid = os.getpid()
    (tmp_path / "recording.pid").write_text(str(recording_pid), encoding="utf-8")
    (tmp_path / "live-audio.pid").write_text(str(recording_pid), encoding="utf-8")
    (tmp_path / "live-audio.reused-recording").write_text(str(recording_pid), encoding="utf-8")
    killed: list[tuple[int, int]] = []

    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append((pid, sig)))

    payload = asyncio.run(
        runtime.stop_live_audio(
            "job-123",
            {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
        )
    )

    assert payload == {"pid": recording_pid}
    assert killed == []
    assert (tmp_path / "recording.pid").exists()
    assert not (tmp_path / "live-audio.pid").exists()
    assert not (tmp_path / "live-audio.reused-recording").exists()


def test_stop_recording_preserves_dedicated_live_audio_pid(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    recording_pid = os.getpid()
    (tmp_path / "recording.pid").write_text(str(recording_pid), encoding="utf-8")
    (tmp_path / "live-audio.pid").write_text("5678", encoding="utf-8")

    monkeypatch.setattr(runtime, "_stop_process_from_pid_file", lambda pid_file: recording_pid)

    payload = asyncio.run(
        runtime.stop_recording(
            "job-123",
            str(tmp_path / "recording.mp4"),
            {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
        )
    )

    assert payload == {"pid": recording_pid, "output_file": str(tmp_path / "recording.mp4")}
    assert (tmp_path / "live-audio.pid").read_text(encoding="utf-8") == "5678"


def test_start_live_audio_uses_dedicated_audio_helper_without_recording(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    captured: dict[str, object] = {}

    def fake_start(
        args: list[str],
        pid_file: Path,
        log_file: Path,
        startup_grace_seconds: float | None = None,
    ) -> None:
        captured["args"] = args
        captured["pid_file"] = pid_file
        captured["log_file"] = log_file
        pid_file.write_text("5678", encoding="utf-8")

    monkeypatch.setattr(runtime, "_start_long_running_helper", fake_start)

    payload = asyncio.run(
        runtime.start_live_audio(
            "job-123",
            {"id": "display:1", "kind": "display", "label": "Display 1", "display_id": "1"},
        )
    )

    assert captured["args"] == [
        "live-audio",
        "--fifo-path",
        str(tmp_path / "live_audio.pcm"),
        "--stop-file",
        str(tmp_path / "live-audio.stop"),
        "--mute-command-file",
        str(tmp_path / "live-audio.mute-command.json"),
        "--mute-state-file",
        str(tmp_path / "live-audio.mute-state.json"),
        "--target-json",
        '{"id":"display:1","kind":"display","label":"Display 1","app_bundle_id":null,"app_name":null,"app_pid":null,"window_id":null,"display_id":"1"}',
    ]
    assert captured["pid_file"] == tmp_path / "live-audio.pid"
    assert payload == {"pid": 5678, "fifo_path": str(tmp_path / "live_audio.pcm"), "log_file": str(tmp_path / "live-audio.log")}


def test_start_live_audio_passes_muted_app_audio_flag_to_helper(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    captured: dict[str, object] = {}

    def fake_start(
        args: list[str],
        pid_file: Path,
        log_file: Path,
        startup_grace_seconds: float | None = None,
    ) -> None:
        captured["args"] = args
        pid_file.write_text("5678", encoding="utf-8")

    monkeypatch.setattr(runtime, "_start_long_running_helper", fake_start)

    asyncio.run(
        runtime.start_live_audio(
            "job-123",
            {
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
            },
            mute_target_audio=True,
        )
    )

    assert "--mute-target-audio" in captured["args"]


def test_set_target_audio_muted_uses_recording_helper_when_recording_is_running(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    recording_pid = os.getpid()
    (tmp_path / "recording.pid").write_text(str(recording_pid), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_send_mute_command(pid_file: Path, mute_target_audio: bool) -> dict[str, object]:
        captured["pid_file"] = pid_file
        captured["mute_target_audio"] = mute_target_audio
        return {"pid": recording_pid, "mute_target_audio": mute_target_audio}

    monkeypatch.setattr(runtime, "_send_mute_command", fake_send_mute_command)

    payload = asyncio.run(
        runtime.set_target_audio_muted(
            "job-123",
            {"id": "application:chrome", "kind": "application", "label": "Google Chrome", "app_pid": 4242},
            True,
        )
    )

    assert payload == {"pid": recording_pid, "mute_target_audio": True}
    assert captured == {"pid_file": tmp_path / "recording.pid", "mute_target_audio": True}


def test_set_target_audio_muted_uses_dedicated_live_audio_helper_without_recording(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    live_audio_pid = os.getpid()
    (tmp_path / "live-audio.pid").write_text(str(live_audio_pid), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_send_mute_command(pid_file: Path, mute_target_audio: bool) -> dict[str, object]:
        captured["pid_file"] = pid_file
        captured["mute_target_audio"] = mute_target_audio
        return {"pid": live_audio_pid, "mute_target_audio": mute_target_audio}

    monkeypatch.setattr(runtime, "_send_mute_command", fake_send_mute_command)

    payload = asyncio.run(
        runtime.set_target_audio_muted(
            "job-123",
            {"id": "application:chrome", "kind": "application", "label": "Google Chrome", "app_pid": 4242},
            False,
        )
    )

    assert payload == {"pid": live_audio_pid, "mute_target_audio": False}
    assert captured == {"pid_file": tmp_path / "live-audio.pid", "mute_target_audio": False}


def test_set_target_audio_muted_writes_command_and_waits_for_matching_state(tmp_path: Path, monkeypatch) -> None:
    runtime = MacOSCaptureRuntime()
    runtime.runtime_dir = tmp_path
    pid_file = tmp_path / "recording.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    writes: list[dict[str, object]] = []

    def fake_wait_for_mute_state(state_file: Path, command_id: str) -> dict[str, object]:
        command = (tmp_path / "recording.mute-command.json").read_text(encoding="utf-8")
        writes.append({"state_file": state_file, "command_id": command_id, "command": command})
        return {"id": command_id, "ok": True, "mute_target_audio": True}

    monkeypatch.setattr(runtime, "_wait_for_mute_state", fake_wait_for_mute_state)

    payload = runtime._send_mute_command(pid_file, True)

    assert payload == {"pid": os.getpid(), "mute_target_audio": True}
    assert len(writes) == 1
    assert writes[0]["state_file"] == tmp_path / "recording.mute-state.json"
    assert f'"id": "{writes[0]["command_id"]}"' in str(writes[0]["command"])
    assert '"mute_target_audio": true' in str(writes[0]["command"])
