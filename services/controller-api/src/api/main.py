from __future__ import annotations

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware

from core.auth import authenticated_api_user, current_api_user, issue_api_token, native_client_requested, revoke_api_token
from jobs.jobs import (
    CaptureConflictError,
    CaptureMuteError,
    CaptureMuteStateError,
    CaptureMuteUnsupportedError,
    CaptureStartupError,
)
from jobs.models import (
    ArtifactsOverviewItem,
    ArtifactsOverviewResponse,
    CaptureTargetsResponse,
    HealthCheckResult,
    HealthStatusResponse,
    JobCreate,
    JobMuteTargetAudioRequest,
    JobStopRequest,
    SessionCredentials,
    SessionResponse,
    TranscriptSummaryGenerateRequest,
    TranscriptSummarySaveRequest,
    VoiceNoteSummaryGenerateRequest,
    VoiceNoteSummaryGenerateResponse,
)
from api.runtime import AppRuntime, create_runtime
from core.settings import Settings
from transcripts.deepgram_client import DeepgramClient, normalize_deepgram_message
from transcripts.summary_cache import TranscriptSummaryRequestNotFoundError


def sse_payload(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def iter_live_stream_events(runtime: AppRuntime, job_id: str) -> AsyncIterator[dict[str, Any]]:
    job = runtime.jobs.get_job(job_id)
    snapshot = runtime.transcript_store.snapshot(job_id)
    yield {"type": "status", "state": job.state}
    for block in snapshot["final_blocks"]:
        yield block
    if snapshot["interim"]:
        yield {"type": "interim", "text": snapshot["interim"]}
    queue = runtime.transcript_hub.subscribe(job_id)
    try:
        while True:
            event = await queue.get()
            yield event
    finally:
        runtime.transcript_hub.unsubscribe(job_id, queue)


async def handle_fake_voice_note_stream(websocket: WebSocket) -> None:
    sent_interim = False
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes") and not sent_interim:
            sent_interim = True
            await websocket.send_json({"type": "interim", "text": "voice note draft"})
            continue
        if message.get("text"):
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(message["text"])
                if payload.get("type") == "Finalize":
                    await websocket.send_json({"type": "final", "text": "voice note captured"})
                    await websocket.send_json({"type": "complete"})
                    return


async def handle_voice_note_stream(runtime: AppRuntime, websocket: WebSocket) -> None:
    await websocket.accept()
    if runtime.settings.fake_mode:
        await handle_fake_voice_note_stream(websocket)
        return

    deepgram = DeepgramClient(runtime.settings)
    try:
        deepgram_socket = await deepgram.connect(
            model=runtime.settings.deepgram_model,
            language=runtime.settings.deepgram_language,
            diarize=False,
            smart_format=runtime.settings.deepgram_smart_format,
            interim_results=True,
            vad_events=runtime.settings.deepgram_vad_events,
            encoding="linear16",
            sample_rate=16000,
            channels=1,
        )
    except Exception as exc:  # pragma: no cover - network
        await websocket.send_json({"type": "warning", "message": str(exc) or "Unable to start live note."})
        await websocket.send_json({"type": "complete"})
        return

    async def send_microphone_audio() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes"):
                await deepgram_socket.send(message["bytes"])
                continue
            if message.get("text"):
                with contextlib.suppress(json.JSONDecodeError):
                    payload = json.loads(message["text"])
                    if payload.get("type") == "Finalize":
                        await deepgram_socket.send(json.dumps({"type": "Finalize"}))
                        await deepgram_socket.send(json.dumps({"type": "CloseStream"}))
                        break

    async def receive_transcript_events() -> None:
        async for message in deepgram_socket:
            if isinstance(message, bytes):
                continue
            await websocket.send_json(normalize_deepgram_message(json.loads(message)))
        await websocket.send_json({"type": "complete"})

    sender = asyncio.create_task(send_microphone_audio())
    receiver = asyncio.create_task(receive_transcript_events())
    with contextlib.suppress(Exception):
        await sender
    with contextlib.suppress(Exception, asyncio.TimeoutError):
        await asyncio.wait_for(receiver, timeout=5.0)
    if not receiver.done():
        receiver.cancel()
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "complete"})
    with contextlib.suppress(Exception):
        await deepgram_socket.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    runtime = create_runtime(app_settings)
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.recovery.areconcile()
        yield

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    cors_origins = [
        app_settings.controller_base_url,
        "http://127.0.0.1:1420",
        "tauri://localhost",
        *app_settings.controller_cors_origins,
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(dict.fromkeys(cors_origins)),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SessionMiddleware, secret_key=app_settings.session_secret)
    app.state.runtime = runtime
    app.state.api_tokens = {}
    def session_payload(request: Request) -> SessionResponse:
        user = authenticated_api_user(request)
        return SessionResponse(authenticated=bool(user), username=user)

    async def desktop_health_payload() -> HealthCheckResult:
        try:
            details = await runtime.desktop.health()
            return HealthCheckResult(ok=True, status=str(details.get("status", "ok")), details=details)
        except Exception as exc:
            return HealthCheckResult(ok=False, status="unavailable", details={"detail": str(exc)})

    async def deepgram_health_payload() -> HealthCheckResult:
        details = {"ok": bool(app_settings.deepgram_api_key or app_settings.fake_mode), "provider": "fake" if app_settings.fake_mode else "deepgram"}
        return HealthCheckResult(ok=details["ok"], status="configured" if details["ok"] else "missing", details=details)

    async def openclaw_health_payload() -> HealthCheckResult:
        try:
            details = await runtime.openclaw.health()
            return HealthCheckResult(ok=True, status=str(details.get("status", "ok")), details=details)
        except Exception as exc:
            return HealthCheckResult(ok=False, status="unavailable", details={"detail": str(exc)})

    async def health_status_payload() -> HealthStatusResponse:
        return HealthStatusResponse(
            desktop=await desktop_health_payload(),
            deepgram=await deepgram_health_payload(),
            openclaw=await openclaw_health_payload(),
        )

    def artifacts_overview_payload() -> ArtifactsOverviewResponse:
        jobs = runtime.jobs.list_jobs()
        return ArtifactsOverviewResponse(
            jobs=[
                ArtifactsOverviewItem(
                    job=job,
                    artifacts=runtime.artifacts.list_files(job.id, app_settings.controller_base_url),
                )
                for job in jobs
            ]
        )

    @app.get("/api/session")
    async def session_status(request: Request) -> JSONResponse:
        return JSONResponse(session_payload(request).model_dump())

    @app.post("/api/session/login")
    async def login_json(request: Request, payload: SessionCredentials) -> JSONResponse:
        if payload.username != app_settings.controller_username or payload.password != app_settings.controller_password:
            return JSONResponse({"detail": "invalid credentials"}, status_code=401)
        request.session["user"] = payload.username
        response_payload = session_payload(request).model_dump()
        if native_client_requested(request):
            response_payload["api_token"] = issue_api_token(request, payload.username)
        return JSONResponse(response_payload)

    @app.post("/api/session/logout")
    async def logout_json(request: Request) -> JSONResponse:
        revoke_api_token(request)
        request.session.clear()
        return JSONResponse(session_payload(request).model_dump())

    @app.get("/api/jobs")
    async def list_jobs(_: str = Depends(current_api_user)) -> JSONResponse:
        return JSONResponse([job.model_dump() for job in runtime.jobs.list_jobs()])

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, _: str = Depends(current_api_user)) -> JSONResponse:
        payload = runtime.jobs.get_job(job_id).model_dump()
        payload["timeline"] = [item.model_dump() for item in runtime.jobs.list_transitions(job_id)]
        payload["live_snapshot"] = runtime.transcript_store.snapshot(job_id)
        return JSONResponse(payload)

    @app.post("/api/jobs/start")
    async def start_job(payload: JobCreate, _: str = Depends(current_api_user)) -> JSONResponse:
        try:
            job = await runtime.capture.start_capture(payload)
        except CaptureConflictError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except CaptureStartupError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(job.model_dump())

    @app.get("/api/capture/targets")
    async def capture_targets(backend: str, _: str = Depends(current_api_user)) -> JSONResponse:
        active_job = runtime.jobs.active_job()
        if active_job is not None and active_job.capture_backend == backend:
            payload = CaptureTargetsResponse(backend=backend, targets=[active_job.capture_target])
            return JSONResponse(payload.model_dump())

        try:
            capture_backend = runtime.capture_backends.require(backend)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="capture backend not found") from exc
        try:
            payload = CaptureTargetsResponse(backend=backend, targets=await capture_backend.list_targets())
        except Exception as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(payload.model_dump())

    @app.post("/api/jobs/{job_id}/stop")
    async def stop_job(job_id: str, payload: JobStopRequest | None = None, _: str = Depends(current_api_user)) -> JSONResponse:
        try:
            job = await runtime.capture.dispatch_stop_capture(job_id, skip_summary=bool(payload and payload.skip_summary))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return JSONResponse(job.model_dump(), status_code=202)

    @app.post("/api/jobs/{job_id}/mute-target-audio")
    async def mute_target_audio(
        job_id: str,
        payload: JobMuteTargetAudioRequest,
        _: str = Depends(current_api_user),
    ) -> JSONResponse:
        try:
            job = await runtime.capture.set_target_audio_muted(job_id, payload.mute_target_audio)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except CaptureMuteUnsupportedError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CaptureMuteStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CaptureMuteError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(job.model_dump())

    @app.post("/api/jobs/{job_id}/summary/rerun")
    async def rerun_summary(job_id: str, _: str = Depends(current_api_user)) -> JSONResponse:
        try:
            job = await runtime.capture.dispatch_summary_rerun(job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return JSONResponse(job.model_dump(), status_code=202)

    @app.post("/api/jobs/{job_id}/recover")
    async def recover_job(job_id: str, _: str = Depends(current_api_user)) -> JSONResponse:
        try:
            job = await runtime.capture.dispatch_recover_capture(job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(job.model_dump(), status_code=202)

    @app.post("/api/jobs/{job_id}/transcript-summary/generate")
    async def generate_transcript_summary(
        job_id: str,
        payload: TranscriptSummaryGenerateRequest,
        _: str = Depends(current_api_user),
    ) -> JSONResponse:
        try:
            result = await runtime.transcript_prompts.generate(job_id=job_id, prompt=payload.prompt)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(result.model_dump())

    @app.post("/api/jobs/{job_id}/transcript-summary/save")
    async def save_transcript_summary(
        job_id: str,
        payload: TranscriptSummarySaveRequest,
        _: str = Depends(current_api_user),
    ) -> JSONResponse:
        try:
            artifact = runtime.transcript_prompts.save(job_id=job_id, request_id=payload.request_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except TranscriptSummaryRequestNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse(artifact.model_dump())

    @app.post("/api/voice-notes/summary/generate")
    async def generate_voice_note_summary(
        payload: VoiceNoteSummaryGenerateRequest,
        _: str = Depends(current_api_user),
    ) -> JSONResponse:
        transcript = payload.transcript.strip()
        prompt = payload.prompt.strip()
        if not transcript:
            raise HTTPException(status_code=400, detail="transcript is required")
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")
        try:
            result = await runtime.openclaw.generate_transcript_summary(
                prompt=prompt,
                transcript_text=transcript,
                title=payload.title.strip() or "Voice note",
            )
        except RuntimeError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        response = VoiceNoteSummaryGenerateResponse(
            markdown=str(result.get("markdown", "")).strip(),
            provider=str(result.get("provider", "openclaw")),
        )
        if not response.markdown:
            return JSONResponse({"detail": "OpenClaw LLM returned no text"}, status_code=502)
        return JSONResponse(response.model_dump())

    @app.post("/api/jobs/{job_id}/cleanup")
    async def cleanup_job(job_id: str, _: str = Depends(current_api_user)) -> JSONResponse:
        try:
            job = runtime.jobs.cleanup_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(job.model_dump())

    @app.post("/api/jobs/{job_id}/delete")
    async def delete_job(job_id: str, _: str = Depends(current_api_user)) -> JSONResponse:
        try:
            job = runtime.jobs.delete_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(job.model_dump())

    @app.get("/api/jobs/{job_id}/artifacts")
    async def list_artifacts(job_id: str, _: str = Depends(current_api_user)) -> JSONResponse:
        artifacts = runtime.artifacts.list_files(job_id, app_settings.controller_base_url)
        return JSONResponse(artifacts.model_dump())

    @app.get("/api/artifacts")
    async def artifacts_overview(_: str = Depends(current_api_user)) -> JSONResponse:
        return JSONResponse(artifacts_overview_payload().model_dump())

    @app.get("/api/jobs/{job_id}/live/stream")
    async def live_stream(job_id: str, _: str = Depends(current_api_user)) -> StreamingResponse:
        try:
            runtime.jobs.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc

        async def event_stream():
            async for event in iter_live_stream_events(runtime, job_id):
                yield sse_payload(event)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.websocket("/ws/jobs/{job_id}/live")
    async def live_socket(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        snapshot = runtime.transcript_store.snapshot(job_id)
        await websocket.send_json({"type": "status", "state": runtime.jobs.get_job(job_id).state})
        for block in snapshot["final_blocks"]:
            await websocket.send_json(block)
        if snapshot["interim"]:
            await websocket.send_json({"type": "interim", "text": snapshot["interim"]})
        queue = runtime.transcript_hub.subscribe(job_id)
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            runtime.transcript_hub.unsubscribe(job_id, queue)

    @app.websocket("/ws/voice-notes/live")
    async def voice_note_live_socket(websocket: WebSocket) -> None:
        try:
            await handle_voice_note_stream(runtime, websocket)
        except WebSocketDisconnect:
            return

    @app.get("/api/health")
    async def api_health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.get("/api/settings/health")
    async def settings_health(_: str = Depends(current_api_user)) -> JSONResponse:
        return JSONResponse((await health_status_payload()).model_dump())

    @app.get("/api/settings/test/deepgram")
    async def deepgram_test(_: str = Depends(current_api_user)) -> JSONResponse:
        return JSONResponse((await deepgram_health_payload()).details)

    @app.get("/api/settings/test/desktop")
    async def desktop_test(_: str = Depends(current_api_user)) -> JSONResponse:
        try:
            return JSONResponse(await runtime.desktop.health())
        except RuntimeError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.get("/api/settings/test/openclaw")
    async def openclaw_test(_: str = Depends(current_api_user)) -> JSONResponse:
        try:
            return JSONResponse(await runtime.openclaw.health())
        except Exception as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.get("/artifacts/{job_id}/{filename}")
    async def artifact_download(job_id: str, filename: str, _: str = Depends(current_api_user)) -> FileResponse:
        path = runtime.artifacts.job_paths(job_id).root / filename
        return FileResponse(path)

    return app
