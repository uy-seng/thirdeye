from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_AGENT_ROOT = ROOT / "services" / "desktop-agent"


def run_script(name: str, tmp_path: Path) -> dict[str, object]:
    env = os.environ | {
        "DRY_RUN": "1",
        "JOB_ID": "job-123",
        "OUTPUT_DIR": str(tmp_path),
        "CAPTURE_RUNTIME_DIR": str(tmp_path / "runtime"),
        "PULSE_SOURCE_OVERRIDE": "speaker.monitor",
        "DISPLAY": ":99",
        "RECORDING_WIDTH": "1280",
        "RECORDING_HEIGHT": "720",
        "RECORDING_FPS": "15",
    }
    result = subprocess.run(
        ["/bin/bash", str(DESKTOP_AGENT_ROOT / "scripts" / name)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_start_recording_script_builds_x11_and_pulse_command(tmp_path: Path) -> None:
    payload = run_script("start_recording.sh", tmp_path)

    assert payload["mode"] == "dry-run"
    command = payload["command"]
    assert "ffmpeg" in command[0]
    assert "x11grab" in command
    assert "pulse" in command
    assert "speaker.monitor" in command
    assert str(tmp_path / "jobs" / "job-123" / "recording.mp4") == payload["output_file"]


def test_start_recording_script_prefers_available_x_socket_over_stale_display_env(tmp_path: Path) -> None:
    x11_socket_dir = Path(tempfile.mkdtemp(prefix="x11-"))
    probe_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe_socket.bind(str(x11_socket_dir / "X0"))
        probe_socket.close()

        env = os.environ | {
            "DRY_RUN": "1",
            "JOB_ID": "job-123",
            "OUTPUT_DIR": str(tmp_path),
            "CAPTURE_RUNTIME_DIR": str(tmp_path / "runtime"),
            "PULSE_SOURCE_OVERRIDE": "speaker.monitor",
            "DISPLAY": ":1",
            "X11_SOCKET_DIR": str(x11_socket_dir),
        }
        result = subprocess.run(
            ["/bin/bash", str(DESKTOP_AGENT_ROOT / "scripts" / "start_recording.sh")],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        command = payload["command"]
        assert command[command.index("-i") + 1] == ":0"
    finally:
        with contextlib.suppress(FileNotFoundError):
            (x11_socket_dir / "X0").unlink()
        with contextlib.suppress(OSError):
            x11_socket_dir.rmdir()


def test_start_recording_script_fails_fast_when_ffmpeg_exits_immediately(tmp_path: Path) -> None:
    fake_ffmpeg = tmp_path / "fake-ffmpeg.sh"
    fake_ffmpeg.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'simulated ffmpeg startup failure' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_ffmpeg.chmod(0o755)

    result = subprocess.run(
        ["/bin/bash", str(DESKTOP_AGENT_ROOT / "scripts" / "start_recording.sh")],
        env=os.environ
        | {
            "JOB_ID": "job-123",
            "OUTPUT_DIR": str(tmp_path),
            "CAPTURE_RUNTIME_DIR": str(tmp_path / "runtime"),
            "PULSE_SOURCE_OVERRIDE": "speaker.monitor",
            "DISPLAY": ":0",
            "FFMPEG_BIN": str(fake_ffmpeg),
            "X11_SOCKET_DIR": str(tmp_path / "missing-x11"),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["error"] == "recording_start_failed"
    assert payload["exit_code"] == 1
    assert "simulated ffmpeg startup failure" in payload["log_tail"]


def test_start_live_audio_script_builds_linear16_command(tmp_path: Path) -> None:
    payload = run_script("start_live_audio.sh", tmp_path)

    assert payload["mode"] == "dry-run"
    command = payload["command"]
    assert "ffmpeg" in command[0]
    assert "pulse" in command
    assert "16000" in command
    assert "s16le" in command
    assert payload["fifo_path"].endswith("live_audio.pcm")


def test_prepare_pulse_runtime_script_bridges_xdg_socket_and_exports_env(
    tmp_path: Path,
) -> None:
    xdg_runtime_dir = tmp_path / "xdg"
    container_env_dir = tmp_path / "container-env"
    result = subprocess.run(
        ["/bin/bash", str(DESKTOP_AGENT_ROOT / "scripts" / "prepare_pulse_runtime.sh")],
        env=os.environ
        | {
            "XDG_RUNTIME_DIR": str(xdg_runtime_dir),
            "CONTAINER_ENV_DIR": str(container_env_dir),
            "ABC_USER": "nobody",
            "ABC_GROUP": "nogroup",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    pulse_dir = xdg_runtime_dir / "pulse"
    native_socket = pulse_dir / "native"
    assert pulse_dir.is_dir()
    assert native_socket.is_symlink()
    assert os.readlink(native_socket) == "/defaults/native"
    assert (container_env_dir / "PULSE_SERVER").read_text() == "unix:/defaults/native"
    assert (container_env_dir / "PULSE_RUNTIME_PATH").read_text() == "/defaults"


def test_prepare_pulse_runtime_script_tolerates_unwritable_container_env_dir(tmp_path: Path) -> None:
    xdg_runtime_dir = tmp_path / "xdg"
    container_env_dir = tmp_path / "container-env"
    container_env_dir.mkdir()
    container_env_dir.chmod(0o555)

    result = subprocess.run(
        ["/bin/bash", str(DESKTOP_AGENT_ROOT / "scripts" / "prepare_pulse_runtime.sh")],
        env=os.environ
        | {
            "XDG_RUNTIME_DIR": str(xdg_runtime_dir),
            "CONTAINER_ENV_DIR": str(container_env_dir),
            "ABC_USER": os.environ.get("USER", "nobody"),
            "ABC_GROUP": "staff",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    pulse_dir = xdg_runtime_dir / "pulse"
    native_socket = pulse_dir / "native"
    assert pulse_dir.is_dir()
    assert native_socket.is_symlink()
    assert os.readlink(native_socket) == "/defaults/native"
    assert not (container_env_dir / "PULSE_SERVER").exists()
    assert not (container_env_dir / "PULSE_RUNTIME_PATH").exists()


def test_desktop_agent_service_runs_as_desktop_user() -> None:
    run_script = ROOT / "infra" / "docker" / "desktop" / "s6-rc.d" / "svc-desktop-agent" / "run"
    contents = run_script.read_text(encoding="utf-8")

    assert "s6-setuidgid" in contents
    assert "${ABC_USER:-abc}" in contents
