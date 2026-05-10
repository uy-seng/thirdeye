from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import select
import subprocess
from pathlib import Path
from typing import AsyncIterator

from pydantic import BaseModel

from .contracts import CaptureTarget


class CaptureCommandRequest(BaseModel):
    job_id: str
    output_file: str | None = None
    target: CaptureTarget | None = None
    mute_target_audio: bool = False


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    with contextlib.suppress(ValueError):
        return int(path.read_text(encoding="utf-8").strip())
    return None


def process_is_active(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True

    state = result.stdout.strip()
    return result.returncode == 0 and not state.startswith("Z")


def running_pid(path: Path) -> int | None:
    pid = read_pid(path)
    if pid is None or not process_is_active(pid):
        return None
    return pid


def status_payload(runtime_dir: Path) -> dict[str, dict[str, int | bool | None]]:
    recording_pid = running_pid(runtime_dir / "recording.pid")
    live_audio_pid = running_pid(runtime_dir / "live-audio.pid")
    return {
        "recording": {"running": recording_pid is not None, "pid": recording_pid},
        "live_audio": {"running": live_audio_pid is not None, "pid": live_audio_pid},
    }


class FifoAudioFanout:
    def __init__(
        self,
        fifo_path: Path,
        *,
        silence_chunk_bytes: int | None = None,
        silence_interval_seconds: float = 3.0,
        read_timeout_seconds: float = 0.25,
    ) -> None:
        self.fifo_path = fifo_path
        self.queues: list[asyncio.Queue[bytes]] = []
        self.task: asyncio.Task[None] | None = None
        self.silence_chunk_bytes = silence_chunk_bytes
        self.silence_interval_seconds = silence_interval_seconds
        self.read_timeout_seconds = read_timeout_seconds

    def ensure_running(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._run())

    def reset(self) -> None:
        if self.task is not None:
            self.task.cancel()
            self.task = None
        self.queues.clear()

    async def _run(self) -> None:
        fd: int | None = None
        inode: int | None = None
        last_silence = asyncio.get_running_loop().time()
        try:
            while True:
                if fd is None:
                    opened = await asyncio.to_thread(self._open_fifo)
                    if opened is None:
                        await asyncio.sleep(0.1)
                        continue
                    fd, inode = opened

                if await asyncio.to_thread(self._fifo_was_replaced, fd, inode):
                    os.close(fd)
                    fd = None
                    inode = None
                    continue

                chunk = await asyncio.to_thread(self._read_chunk, fd)
                if chunk:
                    last_silence = asyncio.get_running_loop().time()
                    await self._broadcast(chunk)
                    continue

                now = asyncio.get_running_loop().time()
                if self.silence_chunk_bytes is not None and self.queues and now - last_silence >= self.silence_interval_seconds:
                    last_silence = now
                    await self._broadcast(b"\x00" * self.silence_chunk_bytes)
                await asyncio.sleep(0.02)
        finally:
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)

    def _open_fifo(self) -> tuple[int, int] | None:
        try:
            stat_result = self.fifo_path.stat()
            fd = os.open(self.fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno in {errno.ENXIO, errno.ENOENT}:
                return None
            raise
        return fd, stat_result.st_ino

    def _fifo_was_replaced(self, fd: int, inode: int | None) -> bool:
        if inode is None:
            return False
        try:
            return self.fifo_path.stat().st_ino != inode or os.fstat(fd).st_ino != inode
        except FileNotFoundError:
            return True

    def _read_chunk(self, fd: int) -> bytes:
        readable, _, _ = select.select([fd], [], [], self.read_timeout_seconds)
        if not readable:
            return b""
        try:
            return os.read(fd, 4096)
        except BlockingIOError:
            return b""

    async def _broadcast(self, chunk: bytes) -> None:
        for queue in list(self.queues):
            await queue.put(chunk)

    async def stream(self) -> AsyncIterator[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.queues.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            with contextlib.suppress(ValueError):
                self.queues.remove(queue)
