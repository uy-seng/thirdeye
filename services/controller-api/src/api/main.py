from __future__ import annotations

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from capture.desktop_sessions import (
    DesktopSessionCreateRequest,
    DesktopSessionError,
    DesktopSessionLimitError,
    DesktopSessionNotFoundError,
    DesktopSessionsResponse,
)
from jobs.jobs import (
    CaptureEchoCancellationError,
    CaptureEchoCancellationStateError,
    CaptureEchoCancellationUnsupportedError,
    CaptureConflictError,
    CaptureMicrophoneError,
    CaptureMicrophoneStateError,
    CaptureMicrophoneUnsupportedError,
    CaptureMuteError,
    CaptureMuteStateError,
    CaptureMuteUnsupportedError,
    CaptureStartupError,
)
from jobs.models import (
    ArtifactsOverviewItem,
    ArtifactsOverviewResponse,
    CaptureTargetsResponse,
    JobCreate,
    JobEchoCancellationRequest,
    JobMuteTargetAudioRequest,
    JobRecordMicrophoneRequest,
    JobResponse,
    JobStopRequest,
    TranscriptSummaryGenerateRequest,
    TranscriptSummarySaveRequest,
    VoiceNoteSummaryGenerateRequest,
    VoiceNoteSummaryGenerateResponse,
    VoiceNoteImportRequest,
    VoiceNoteUpdateRequest,
    VoiceNoteUpsertRequest,
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
    sources = snapshot.get("sources")
    if isinstance(sources, dict):
        for source in ("system", "microphone"):
            source_snapshot = sources.get(source)
            if not isinstance(source_snapshot, dict):
                continue
            for block in source_snapshot.get("final_blocks", []):
                yield block
            interim = source_snapshot.get("interim")
            if interim:
                payload = {"type": "interim", "text": interim}
                if source == "microphone":
                    payload["source"] = source
                yield payload
    else:
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


async def handle_voice_note_stream(runtime: AppRuntime, websocket: WebSocket) -> None:
    await websocket.accept()

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
    app.state.runtime = runtime

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

    @app.get("/api/jobs")
    async def list_jobs() -> JSONResponse:
        return JSONResponse([job.model_dump() for job in runtime.jobs.list_jobs()])

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> JSONResponse:
        payload = runtime.jobs.get_job(job_id).model_dump()
        payload["timeline"] = [item.model_dump() for item in runtime.jobs.list_transitions(job_id)]
        payload["live_snapshot"] = runtime.transcript_store.snapshot(job_id)
        return JSONResponse(payload)

    @app.post("/api/jobs/start")
    async def start_job(payload: JobCreate) -> JSONResponse:
        try:
            job = await runtime.capture.start_capture(payload)
        except CaptureConflictError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except CaptureStartupError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(job.model_dump())

    def active_docker_jobs_by_target() -> dict[str, JobResponse]:
        return {
            str(job.capture_target.get("id")): job
            for job in runtime.jobs.active_jobs()
            if job.capture_backend == "docker_desktop"
        }

    def active_job_fields_by_target(active_jobs: dict[str, JobResponse], target_id: object) -> dict[str, str | None]:
        active_job = active_jobs.get(str(target_id))
        return {
            "active_job_id": active_job.id if active_job else None,
            "active_job_state": active_job.state if active_job else None,
        }

    @app.get("/api/desktops")
    async def list_desktops() -> JSONResponse:
        active_job_by_target = active_docker_jobs_by_target()
        desktops = [
            desktop.model_copy(update=active_job_fields_by_target(active_job_by_target, desktop.target_id))
            for desktop in runtime.desktop_sessions.list_sessions()
        ]
        payload = DesktopSessionsResponse(desktops=desktops)
        return JSONResponse(payload.model_dump())

    @app.post("/api/desktops")
    async def create_desktop(payload: DesktopSessionCreateRequest) -> JSONResponse:
        try:
            desktop = runtime.desktop_sessions.create_session(payload.label)
        except DesktopSessionLimitError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except DesktopSessionError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(desktop.model_dump())

    @app.post("/api/desktops/{desktop_id}/destroy")
    async def destroy_desktop(desktop_id: str) -> JSONResponse:
        active_job_by_target = active_docker_jobs_by_target()
        try:
            desktop = next((session for session in runtime.desktop_sessions.list_sessions() if session.id == desktop_id), None)
            if desktop is None:
                raise DesktopSessionNotFoundError("isolated desktop not found")
            if desktop.target_id in active_job_by_target:
                return JSONResponse({"detail": "stop the recording before destroying this desktop"}, status_code=409)
            destroyed = runtime.desktop_sessions.destroy_session(desktop_id)
        except DesktopSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse(destroyed.model_dump())

    @app.get("/api/capture/targets")
    async def capture_targets(backend: str) -> JSONResponse:
        active_job = runtime.jobs.active_job()
        if active_job is not None and active_job.capture_backend == backend and backend != "docker_desktop":
            payload = CaptureTargetsResponse(backend=backend, targets=[active_job.capture_target])
            return JSONResponse(payload.model_dump())

        try:
            capture_backend = runtime.capture_backends.require(backend)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="capture backend not found") from exc
        try:
            targets = await capture_backend.list_targets()
            if backend == "docker_desktop":
                active_job_by_target = active_docker_jobs_by_target()
                targets = [
                    target
                    | {
                        "available": str(target.get("id")) not in active_job_by_target,
                    }
                    | active_job_fields_by_target(active_job_by_target, target.get("id"))
                    for target in targets
                ]
                return JSONResponse({"backend": backend, "targets": targets})
            payload = CaptureTargetsResponse(backend=backend, targets=targets)
        except Exception as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(payload.model_dump())

    @app.post("/api/jobs/{job_id}/stop")
    async def stop_job(job_id: str, payload: JobStopRequest | None = None) -> JSONResponse:
        try:
            job = await runtime.capture.dispatch_stop_capture(job_id, skip_summary=bool(payload and payload.skip_summary))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return JSONResponse(job.model_dump(), status_code=202)

    @app.post("/api/jobs/{job_id}/mute-target-audio")
    async def mute_target_audio(
        job_id: str,
        payload: JobMuteTargetAudioRequest,
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

    @app.post("/api/jobs/{job_id}/record-microphone")
    async def record_microphone(
        job_id: str,
        payload: JobRecordMicrophoneRequest,
    ) -> JSONResponse:
        try:
            job = await runtime.capture.set_record_microphone_enabled(
                job_id,
                payload.record_microphone,
                payload.echo_cancellation_enabled,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except CaptureMicrophoneUnsupportedError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CaptureMicrophoneStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CaptureMicrophoneError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(job.model_dump())

    @app.post("/api/jobs/{job_id}/echo-cancellation")
    async def echo_cancellation(
        job_id: str,
        payload: JobEchoCancellationRequest,
    ) -> JSONResponse:
        try:
            job = await runtime.capture.set_echo_cancellation_enabled(job_id, payload.echo_cancellation_enabled)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except CaptureEchoCancellationUnsupportedError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CaptureEchoCancellationStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CaptureEchoCancellationError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)
        return JSONResponse(job.model_dump())

    @app.post("/api/jobs/{job_id}/summary/rerun")
    async def rerun_summary(job_id: str) -> JSONResponse:
        try:
            job = await runtime.capture.dispatch_summary_rerun(job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return JSONResponse(job.model_dump(), status_code=202)

    @app.post("/api/jobs/{job_id}/recover")
    async def recover_job(job_id: str) -> JSONResponse:
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

    def voice_note_payload(note) -> dict[str, Any]:
        payload = note.model_dump()
        payload["createdAt"] = payload.pop("created_at")
        payload["durationMs"] = payload.pop("duration_ms")
        payload["audioDataUrl"] = payload.pop("audio_data_url")
        if payload.get("summary"):
            payload["summary"]["generatedAt"] = payload["summary"].pop("generated_at")
        return payload

    @app.get("/api/voice-notes")
    async def list_voice_notes() -> JSONResponse:
        return JSONResponse([voice_note_payload(note) for note in runtime.voice_notes.list_notes()])

    @app.post("/api/voice-notes")
    async def upsert_voice_note(payload: VoiceNoteUpsertRequest) -> JSONResponse:
        try:
            note = runtime.voice_notes.upsert_note(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(voice_note_payload(note))

    @app.patch("/api/voice-notes/{note_id}")
    async def update_voice_note(note_id: str, payload: VoiceNoteUpdateRequest) -> JSONResponse:
        try:
            note = runtime.voice_notes.update_note(note_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="voice note not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(voice_note_payload(note))

    @app.post("/api/voice-notes/import")
    async def import_voice_notes(payload: VoiceNoteImportRequest) -> JSONResponse:
        try:
            notes = runtime.voice_notes.import_notes(payload.notes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse([voice_note_payload(note) for note in notes])

    @app.delete("/api/voice-notes/{note_id}")
    async def delete_voice_note(note_id: str) -> JSONResponse:
        try:
            note = runtime.voice_notes.delete_note(note_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="voice note not found") from exc
        return JSONResponse(voice_note_payload(note))

    @app.post("/api/jobs/{job_id}/cleanup")
    async def cleanup_job(job_id: str) -> JSONResponse:
        try:
            job = runtime.jobs.cleanup_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(job.model_dump())

    @app.post("/api/jobs/{job_id}/delete")
    async def delete_job(job_id: str) -> JSONResponse:
        try:
            job = runtime.jobs.delete_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return JSONResponse(job.model_dump())

    @app.get("/api/jobs/{job_id}/artifacts")
    async def list_artifacts(job_id: str) -> JSONResponse:
        artifacts = runtime.artifacts.list_files(job_id, app_settings.controller_base_url)
        return JSONResponse(artifacts.model_dump())

    @app.get("/api/artifacts")
    async def artifacts_overview() -> JSONResponse:
        return JSONResponse(artifacts_overview_payload().model_dump())

    @app.get("/api/jobs/{job_id}/live/stream")
    async def live_stream(job_id: str) -> StreamingResponse:
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

    @app.get("/artifacts/{job_id}/{filename}")
    async def artifact_download(job_id: str, filename: str) -> FileResponse:
        path = runtime.artifacts.path_for_download(job_id, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(path)

    return app
