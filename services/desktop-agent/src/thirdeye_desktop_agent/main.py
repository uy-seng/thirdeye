from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from capture_contracts.agent import CaptureCommandRequest as CommandRequest
from capture_contracts.agent import FifoAudioFanout, status_payload
from capture_contracts.contracts import default_docker_capture_target


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


def build_env(job_id: str, output_file: str | None = None) -> dict[str, str]:
    # The controller may run on the host and pass host-only recording paths.
    # The desktop agent must always write to its own mounted recordings root.
    output_dir = os.environ.get("OUTPUT_DIR", "/recordings")
    env = os.environ | {
        "JOB_ID": job_id,
        "OUTPUT_DIR": output_dir,
        "CAPTURE_RUNTIME_DIR": os.environ.get("CAPTURE_RUNTIME_DIR", "/tmp/capture-runtime"),
        "PULSE_RUNTIME_PATH": os.environ.get("PULSE_RUNTIME_PATH", "/defaults"),
        "PULSE_SERVER": os.environ.get("PULSE_SERVER", "unix:/defaults/native"),
    }
    return env


def run_script(name: str, *, env: dict[str, str]) -> dict[str, object]:
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT_DIR / name)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


async def run_script_async(name: str, *, env: dict[str, str]) -> dict[str, object]:
    return await asyncio.to_thread(run_script, name, env=env)


async def prepare_pulse_runtime(request: CommandRequest) -> None:
    env = build_env(request.job_id, request.output_file) | {"ENABLE_BROWSER_AUDIO_RECOVERY": "1"}
    await run_script_async("prepare_pulse_runtime.sh", env=env)


app = FastAPI(title="Desktop Control Agent")
fanout = FifoAudioFanout(Path(os.environ.get("CAPTURE_RUNTIME_DIR", "/tmp/capture-runtime")) / "live_audio.pcm")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/status")
async def status() -> JSONResponse:
    runtime_dir = Path(os.environ.get("CAPTURE_RUNTIME_DIR", "/tmp/capture-runtime"))
    return JSONResponse(status_payload(runtime_dir))


@app.get("/targets")
async def targets() -> JSONResponse:
    return JSONResponse({"targets": [default_docker_capture_target().model_dump()]})


@app.post("/recording/start")
async def start_recording(request: CommandRequest) -> JSONResponse:
    await prepare_pulse_runtime(request)
    payload = await run_script_async(
        "start_recording.sh",
        env=build_env(request.job_id, request.output_file),
    )
    return JSONResponse(payload)


@app.post("/recording/stop")
async def stop_recording(request: CommandRequest) -> JSONResponse:
    payload = await run_script_async("stop_recording.sh", env=build_env(request.job_id, request.output_file))
    return JSONResponse(payload)


@app.post("/live-audio/start")
async def start_live_audio(request: CommandRequest) -> JSONResponse:
    await prepare_pulse_runtime(request)
    fanout.reset()
    fanout.ensure_running()
    # Start the FIFO reader before ffmpeg opens the pipe for writing.
    payload = await run_script_async("start_live_audio.sh", env=build_env(request.job_id, request.output_file))
    return JSONResponse(payload)


@app.post("/live-audio/stop")
async def stop_live_audio(request: CommandRequest) -> JSONResponse:
    payload = await run_script_async("stop_live_audio.sh", env=build_env(request.job_id, request.output_file))
    fanout.reset()
    return JSONResponse(payload)


@app.get("/live-audio/stream")
async def stream_live_audio(job_id: str) -> StreamingResponse:
    fanout.ensure_running()
    return StreamingResponse(fanout.stream(), media_type="application/octet-stream")
