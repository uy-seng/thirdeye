from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from capture_contracts.agent import process_is_active
from capture_contracts.contracts import CaptureTarget


DEFAULT_HELPER_REPO_RELATIVE_PATH = "services/macos-capture-agent/bin/macos_capture_helper"
DEFAULT_HELPER_TIMEOUT_SECONDS = 4.0
REUSED_RECORDING_MARKER = "live-audio.reused-recording"


class MacOSCaptureRuntimeError(RuntimeError):
    pass


class ScreenCapturePermissionError(MacOSCaptureRuntimeError):
    pass


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    with contextlib.suppress(ValueError):
        return int(path.read_text(encoding="utf-8").strip())
    return None


class MacOSCaptureRuntime:
    def __init__(self) -> None:
        self.runtime_dir = Path(os.environ.get("MACOS_CAPTURE_RUNTIME_DIR", "/tmp/macos-capture-runtime"))
        self.helper_bin = Path(
            os.environ.get(
                "MACOS_CAPTURE_HELPER_BIN",
                str(Path.cwd() / DEFAULT_HELPER_REPO_RELATIVE_PATH),
            )
        )
        self.helper_source = Path.cwd() / "services/macos-capture-agent/helper/ScreenCaptureKitHelper.swift"
        self._processes: dict[Path, subprocess.Popen[bytes]] = {}

    async def list_targets(self) -> list[dict[str, Any]]:
        payload = await asyncio.to_thread(self._run_helper_json, ["targets"])
        targets = payload.get("targets", [])
        if not isinstance(targets, list):
            raise MacOSCaptureRuntimeError("helper returned an invalid targets payload")
        return [
            normalized
            for target in targets
            if (normalized := CaptureTarget.model_validate(target).model_dump())["kind"] in {"display", "application", "window"}
        ]

    async def start_recording(
        self,
        job_id: str,
        output_file: str | None,
        target: dict[str, Any],
        mute_target_audio: bool = False,
    ) -> dict[str, Any]:
        if not output_file:
            raise MacOSCaptureRuntimeError("output_file is required")
        target_payload = CaptureTarget.model_validate(target).model_dump_json()
        fifo_path = self.runtime_dir / "live_audio.pcm"
        pid_file = self.runtime_dir / "recording.pid"
        stop_file = self.runtime_dir / "recording.stop"
        log_file = self.runtime_dir / "recording.log"
        args = [
            "record",
            "--output-file",
            output_file,
            "--fifo-path",
            str(fifo_path),
            "--stop-file",
            str(stop_file),
            "--mute-command-file",
            str(self._mute_command_file("recording")),
            "--mute-state-file",
            str(self._mute_state_file("recording")),
            "--target-json",
            target_payload,
        ]
        if mute_target_audio:
            args.append("--mute-target-audio")
        self._start_long_running_helper(
            args,
            pid_file,
            log_file,
            startup_grace_seconds=float(os.environ.get("MACOS_CAPTURE_RECORDING_STARTUP_GRACE_SECONDS", "1.0")),
        )
        return {"pid": read_pid(pid_file), "output_file": output_file, "log_file": str(log_file)}

    async def stop_recording(self, job_id: str, output_file: str | None, target: dict[str, Any]) -> dict[str, Any]:
        pid_file = self.runtime_dir / "recording.pid"
        pid = self._stop_process_from_pid_file(pid_file)
        self._clear_reused_recording_live_audio()
        return {"pid": pid, "output_file": output_file}

    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
    ) -> dict[str, Any]:
        fifo_path = self.runtime_dir / "live_audio.pcm"
        target_payload = CaptureTarget.model_validate(target).model_dump_json()
        pid_file = self.runtime_dir / "live-audio.pid"
        stop_file = self.runtime_dir / "live-audio.stop"
        log_file = self.runtime_dir / "live-audio.log"
        recording_pid_file = self.runtime_dir / "recording.pid"
        recording_pid = read_pid(recording_pid_file)
        if recording_pid is not None and self._pid_file_process_is_running(recording_pid_file, recording_pid):
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(recording_pid), encoding="utf-8")
            self._reused_recording_marker().write_text(str(recording_pid), encoding="utf-8")
            return {
                "pid": recording_pid,
                "fifo_path": str(fifo_path),
                "log_file": str(self.runtime_dir / "recording.log"),
            }

        args = [
            "live-audio",
            "--fifo-path",
            str(fifo_path),
            "--stop-file",
            str(stop_file),
            "--mute-command-file",
            str(self._mute_command_file("live-audio")),
            "--mute-state-file",
            str(self._mute_state_file("live-audio")),
            "--target-json",
            target_payload,
        ]
        if mute_target_audio:
            args.append("--mute-target-audio")
        self._start_long_running_helper(
            args,
            pid_file,
            log_file,
            startup_grace_seconds=float(os.environ.get("MACOS_CAPTURE_LIVE_AUDIO_STARTUP_GRACE_SECONDS", "0.05")),
        )
        return {"pid": read_pid(pid_file), "fifo_path": str(fifo_path), "log_file": str(log_file)}

    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]:
        pid_file = self.runtime_dir / "live-audio.pid"
        if self._reused_recording_marker().exists():
            pid = read_pid(pid_file) or read_pid(self._reused_recording_marker())
            self._clear_reused_recording_live_audio()
            return {"pid": pid}

        pid = self._stop_process_from_pid_file(pid_file)
        return {"pid": pid}

    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._set_target_audio_muted_sync, mute_target_audio)

    async def status(self) -> dict[str, Any]:
        recording_pid = self._running_pid(self.runtime_dir / "recording.pid")
        live_audio_pid = self._running_pid(self.runtime_dir / "live-audio.pid")
        return {
            "recording": {"running": recording_pid is not None, "pid": recording_pid},
            "live_audio": {"running": live_audio_pid is not None, "pid": live_audio_pid},
        }

    def helper_health(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.helper_bin.exists() else "missing",
            "helper_bin": str(self.helper_bin),
            "helper_source": str(self.helper_source),
        }

    def _run_helper_json(self, args: list[str]) -> dict[str, Any]:
        command = self._helper_command(args)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._helper_timeout_seconds(),
            )
        except subprocess.TimeoutExpired as exc:
            raise MacOSCaptureRuntimeError(
                "macOS screen capture timed out while listing targets. Quit and reopen thirdeye, then refresh."
            ) from exc
        if result.returncode != 0:
            self._raise_helper_error(result.stderr.strip() or result.stdout.strip() or "helper failed")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MacOSCaptureRuntimeError("helper returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MacOSCaptureRuntimeError("helper returned an invalid response")
        return payload

    def _start_long_running_helper(
        self,
        args: list[str],
        pid_file: Path,
        log_file: Path,
        startup_grace_seconds: float | None = None,
    ) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        existing_pid = read_pid(pid_file)
        if existing_pid is not None and self._pid_is_running(existing_pid):
            raise MacOSCaptureRuntimeError("capture process already running")

        if pid_file.exists():
            pid_file.unlink()
        stop_file = self._stop_file_for_pid_file(pid_file)
        if stop_file.exists():
            stop_file.unlink()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("ab") as log_handle:
            process = subprocess.Popen(
                self._helper_command(args),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                preexec_fn=self._restore_child_signal_mask,
            )

        pid_file.write_text(str(process.pid), encoding="utf-8")
        self._processes[pid_file] = process
        try:
            self._verify_process_started(process, pid_file, log_file, startup_grace_seconds)
        except Exception:
            self._processes.pop(pid_file, None)
            raise

    def _verify_process_started(
        self,
        process: subprocess.Popen[bytes],
        pid_file: Path,
        log_file: Path,
        startup_grace_seconds: float | None = None,
    ) -> None:
        if startup_grace_seconds is None:
            startup_grace_seconds = float(os.environ.get("MACOS_CAPTURE_STARTUP_GRACE_SECONDS", "1.0"))
        time.sleep(startup_grace_seconds)
        if process.poll() is None:
            return
        if pid_file.exists():
            pid_file.unlink()
        raise MacOSCaptureRuntimeError(self._log_tail(log_file))

    def _stop_process_from_pid_file(self, pid_file: Path) -> int | None:
        pid = read_pid(pid_file)
        if pid is None:
            return None

        process = self._processes.pop(pid_file, None)
        stop_file = self._stop_file_for_pid_file(pid_file)
        stop_file.write_text("stop", encoding="utf-8")

        stopped = self._wait_for_process_stop(pid, process)
        killed = False
        try:
            if not stopped:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGINT)
                stopped = self._wait_for_process_stop(pid, process)
            if not stopped:
                killed = True
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
                stopped = self._wait_for_process_stop(pid, process)
        finally:
            if pid_file.exists():
                pid_file.unlink()
            if stop_file.exists():
                stop_file.unlink()

        if killed:
            raise MacOSCaptureRuntimeError(f"capture helper did not stop cleanly\n{self._log_tail(self._log_file_for_pid_file(pid_file))}")
        if process is not None and process.returncode not in (0, None):
            raise MacOSCaptureRuntimeError(self._log_tail(self._log_file_for_pid_file(pid_file)))
        return pid

    def _set_target_audio_muted_sync(self, mute_target_audio: bool) -> dict[str, Any]:
        for pid_file in (self.runtime_dir / "recording.pid", self.runtime_dir / "live-audio.pid"):
            pid = read_pid(pid_file)
            if pid is not None and self._pid_file_process_is_running(pid_file, pid):
                return self._send_mute_command(pid_file, mute_target_audio)
        raise MacOSCaptureRuntimeError("capture process is not running")

    def _send_mute_command(self, pid_file: Path, mute_target_audio: bool) -> dict[str, Any]:
        pid = read_pid(pid_file)
        if pid is None or not self._pid_file_process_is_running(pid_file, pid):
            raise MacOSCaptureRuntimeError("capture process is not running")

        command_id = uuid.uuid4().hex
        command_file = self._mute_command_file_for_pid_file(pid_file)
        state_file = self._mute_state_file_for_pid_file(pid_file)
        payload = {"id": command_id, "mute_target_audio": mute_target_audio}
        self._write_json_atomic(command_file, payload)
        state = self._wait_for_mute_state(state_file, command_id)
        if not state.get("ok"):
            raise MacOSCaptureRuntimeError(str(state.get("error") or "failed to update mute state"))
        return {"pid": pid, "mute_target_audio": bool(state.get("mute_target_audio"))}

    def _wait_for_mute_state(self, state_file: Path, command_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self._mute_command_timeout_seconds()
        while time.monotonic() < deadline:
            with contextlib.suppress(FileNotFoundError, json.JSONDecodeError):
                payload = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and payload.get("id") == command_id:
                    return payload
            time.sleep(0.05)
        raise MacOSCaptureRuntimeError("timed out changing mute state")

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload), encoding="utf-8")
        temp_path.replace(path)

    def _wait_for_process_stop(self, pid: int, process: subprocess.Popen[bytes] | None) -> bool:
        timeout = self._stop_timeout_seconds()
        if process is not None:
            try:
                process.wait(timeout=timeout)
                return True
            except subprocess.TimeoutExpired:
                return False

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._pid_is_running(pid):
                return True
            time.sleep(0.1)
        return False

    def _pid_file_process_is_running(self, pid_file: Path, pid: int) -> bool:
        process = self._processes.get(pid_file)
        if process is not None:
            return process.poll() is None
        return self._pid_is_running(pid)

    def _pid_is_running(self, pid: int) -> bool:
        return process_is_active(pid)

    def _running_pid(self, pid_file: Path) -> int | None:
        pid = read_pid(pid_file)
        if pid is None or not self._pid_file_process_is_running(pid_file, pid):
            return None
        return pid

    def _stop_timeout_seconds(self) -> float:
        return float(os.environ.get("MACOS_CAPTURE_STOP_TIMEOUT_SECONDS", "20.0"))

    def _mute_command_timeout_seconds(self) -> float:
        return float(os.environ.get("MACOS_CAPTURE_MUTE_COMMAND_TIMEOUT_SECONDS", "4.0"))

    def _helper_timeout_seconds(self) -> float:
        return float(os.environ.get("MACOS_CAPTURE_HELPER_TIMEOUT_SECONDS", str(DEFAULT_HELPER_TIMEOUT_SECONDS)))

    def _stop_file_for_pid_file(self, pid_file: Path) -> Path:
        return pid_file.with_suffix(".stop")

    def _log_file_for_pid_file(self, pid_file: Path) -> Path:
        return pid_file.with_suffix(".log")

    def _mute_command_file(self, prefix: str) -> Path:
        return self.runtime_dir / f"{prefix}.mute-command.json"

    def _mute_state_file(self, prefix: str) -> Path:
        return self.runtime_dir / f"{prefix}.mute-state.json"

    def _mute_command_file_for_pid_file(self, pid_file: Path) -> Path:
        prefix = "live-audio" if pid_file.name == "live-audio.pid" else "recording"
        return self._mute_command_file(prefix)

    def _mute_state_file_for_pid_file(self, pid_file: Path) -> Path:
        prefix = "live-audio" if pid_file.name == "live-audio.pid" else "recording"
        return self._mute_state_file(prefix)

    def _reused_recording_marker(self) -> Path:
        return self.runtime_dir / REUSED_RECORDING_MARKER

    def _clear_reused_recording_live_audio(self) -> None:
        if not self._reused_recording_marker().exists():
            return

        for path in (
            self.runtime_dir / "live-audio.pid",
            self.runtime_dir / "live-audio.stop",
            self._reused_recording_marker(),
        ):
            if path.exists():
                path.unlink()

    def _helper_command(self, args: list[str]) -> list[str]:
        if not self.helper_bin.exists():
            raise MacOSCaptureRuntimeError(
                "macOS capture helper is missing. Build it with scripts/build_macos_capture_helper.sh before starting the agent."
            )
        return [str(self.helper_bin), *args]

    @staticmethod
    def _restore_child_signal_mask() -> None:
        if hasattr(signal, "pthread_sigmask"):
            signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT, signal.SIGTERM})

    def _raise_helper_error(self, message: str) -> None:
        normalized = message.lower()
        if "screen_recording_permission_denied" in normalized or "screen recording permission" in normalized:
            raise ScreenCapturePermissionError(message)
        raise MacOSCaptureRuntimeError(message)

    def _log_tail(self, log_file: Path) -> str:
        if not log_file.exists():
            return "capture helper exited before startup completed"
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
        return "\n".join(lines) if lines else "capture helper exited before startup completed"
