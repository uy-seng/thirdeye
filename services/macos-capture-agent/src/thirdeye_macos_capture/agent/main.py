from __future__ import annotations

import asyncio
import contextlib
import os
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from capture_contracts.agent import CaptureCommandRequest as CommandRequest
from capture_contracts.agent import FifoAudioFanout, status_payload

from .runtime import MacOSCaptureRuntime, ScreenCapturePermissionError


class AudioFanout(FifoAudioFanout):
    SILENCE_CHUNK_BYTES = 640
    SILENCE_INTERVAL_SECONDS = 3.0
    READ_TIMEOUT_SECONDS = 0.25

    def __init__(self, fifo_path: Path) -> None:
        super().__init__(
            fifo_path,
            silence_chunk_bytes=self.SILENCE_CHUNK_BYTES,
            silence_interval_seconds=self.SILENCE_INTERVAL_SECONDS,
            read_timeout_seconds=self.READ_TIMEOUT_SECONDS,
        )

    def ensure_running(self) -> None:
        self.silence_chunk_bytes = self.SILENCE_CHUNK_BYTES
        self.silence_interval_seconds = self.SILENCE_INTERVAL_SECONDS
        self.read_timeout_seconds = self.READ_TIMEOUT_SECONDS
        super().ensure_running()


app = FastAPI(title="macOS Capture Agent")
runtime = MacOSCaptureRuntime()
fanout = AudioFanout(Path(os.environ.get("MACOS_CAPTURE_RUNTIME_DIR", "/tmp/macos-capture-runtime")) / "live_audio.pcm")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ScreenCapturePermissionError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(runtime.helper_health())


@app.get("/status")
async def status() -> JSONResponse:
    runtime_dir = Path(os.environ.get("MACOS_CAPTURE_RUNTIME_DIR", "/tmp/macos-capture-runtime"))
    return JSONResponse(status_payload(runtime_dir))


@app.get("/targets")
async def targets() -> JSONResponse:
    try:
        payload = await runtime.list_targets()
    except Exception as exc:
        raise _http_error(exc) from exc
    return JSONResponse({"targets": payload})


@app.post("/recording/start")
async def start_recording(request: CommandRequest) -> JSONResponse:
    if request.target is None:
        raise HTTPException(status_code=422, detail="target is required")
    try:
        payload = await runtime.start_recording(
            request.job_id,
            request.output_file,
            request.target.model_dump(),
            request.mute_target_audio,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return JSONResponse(payload)


@app.post("/recording/stop")
async def stop_recording(request: CommandRequest) -> JSONResponse:
    if request.target is None:
        raise HTTPException(status_code=422, detail="target is required")
    try:
        payload = await runtime.stop_recording(request.job_id, request.output_file, request.target.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc
    return JSONResponse(payload)


@app.post("/live-audio/start")
async def start_live_audio(request: CommandRequest) -> JSONResponse:
    if request.target is None:
        raise HTTPException(status_code=422, detail="target is required")
    try:
        payload = await runtime.start_live_audio(
            request.job_id,
            request.target.model_dump(),
            request.mute_target_audio,
        )
        fanout.reset()
        fanout.ensure_running()
    except Exception as exc:
        raise _http_error(exc) from exc
    return JSONResponse(payload)


@app.post("/live-audio/stop")
async def stop_live_audio(request: CommandRequest) -> JSONResponse:
    if request.target is None:
        raise HTTPException(status_code=422, detail="target is required")
    try:
        payload = await runtime.stop_live_audio(request.job_id, request.target.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc
    fanout.reset()
    return JSONResponse(payload)


@app.post("/target-audio/mute")
async def set_target_audio_muted(request: CommandRequest) -> JSONResponse:
    if request.target is None:
        raise HTTPException(status_code=422, detail="target is required")
    try:
        payload = await runtime.set_target_audio_muted(
            request.job_id,
            request.target.model_dump(),
            request.mute_target_audio,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return JSONResponse(payload)


@app.get("/live-audio/stream")
async def stream_live_audio(job_id: str) -> StreamingResponse:
    fanout.ensure_running()
    return StreamingResponse(fanout.stream(), media_type="application/octet-stream")
