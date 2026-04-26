from __future__ import annotations

import os
from pathlib import Path


def test_capture_command_request_normalizes_targets() -> None:
    from capture_contracts.agent import CaptureCommandRequest

    request = CaptureCommandRequest.model_validate(
        {
            "job_id": "job-123",
            "output_file": "/tmp/recording.mp4",
            "target": {
                "id": "window:notes",
                "kind": "window",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "window_id": "notes",
            },
        }
    )

    assert request.target is not None
    assert request.target.model_dump() == {
        "id": "window:notes",
        "kind": "window",
        "label": "Notes",
        "app_bundle_id": "com.apple.Notes",
        "app_name": "Notes",
        "app_pid": None,
        "window_id": "notes",
        "display_id": None,
    }


def test_status_payload_reads_shared_pid_files(tmp_path: Path) -> None:
    from capture_contracts.agent import status_payload

    current_pid = os.getpid()
    (tmp_path / "recording.pid").write_text(str(current_pid), encoding="utf-8")
    (tmp_path / "live-audio.pid").write_text(str(current_pid), encoding="utf-8")

    assert status_payload(tmp_path) == {
        "recording": {"running": True, "pid": current_pid},
        "live_audio": {"running": True, "pid": current_pid},
    }


def test_status_payload_treats_missing_or_invalid_pid_as_stopped(tmp_path: Path) -> None:
    from capture_contracts.agent import status_payload

    (tmp_path / "recording.pid").write_text("not-a-pid", encoding="utf-8")

    assert status_payload(tmp_path) == {
        "recording": {"running": False, "pid": None},
        "live_audio": {"running": False, "pid": None},
    }


def test_status_payload_treats_inactive_pid_as_stopped(tmp_path: Path, monkeypatch) -> None:
    from capture_contracts import agent as capture_agent

    (tmp_path / "recording.pid").write_text("1111", encoding="utf-8")
    monkeypatch.setattr(capture_agent, "process_is_active", lambda pid: False)

    assert capture_agent.status_payload(tmp_path) == {
        "recording": {"running": False, "pid": None},
        "live_audio": {"running": False, "pid": None},
    }
