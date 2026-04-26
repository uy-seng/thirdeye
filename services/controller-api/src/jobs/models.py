from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.db import Base
from core.settings import OPENCLAW_SUMMARY_MODEL_DEFAULT
from jobs.state_machine import JobState
from core.utils import dump_json, isoformat, load_json


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(Text, nullable=False, default=JobState.IDLE.value)
    max_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    auto_stop_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    silence_timeout_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    deepgram_model: Mapped[str] = mapped_column(Text, nullable=False, default="nova-3")
    deepgram_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    diarize: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    smart_format: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    interim_results: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_email: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary_model: Mapped[str] = mapped_column(Text, nullable=False, default=OPENCLAW_SUMMARY_MODEL_DEFAULT)
    recording_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_events_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    ffmpeg_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    live_audio_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deepgram_request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class JobTransition(Base):
    __tablename__ = "job_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    from_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)


CaptureBackendName = Literal["docker_desktop", "macos_local"]
CaptureTargetKind = Literal["desktop", "display", "application", "window"]


class CaptureTarget(BaseModel):
    id: str
    kind: CaptureTargetKind
    label: str
    app_bundle_id: str | None = None
    app_name: str | None = None
    app_pid: int | None = None
    window_id: str | None = None
    display_id: str | None = None


class CaptureTargetsResponse(BaseModel):
    backend: CaptureBackendName
    targets: list[CaptureTarget]


def default_docker_capture_target() -> CaptureTarget:
    return CaptureTarget(
        id="desktop",
        kind="desktop",
        label="Isolated desktop",
    )


def resolve_capture_selection(
    backend: CaptureBackendName | str | None,
    target: CaptureTarget | dict[str, Any] | None,
) -> tuple[CaptureBackendName, CaptureTarget]:
    selected_backend = (backend or "docker_desktop")
    if selected_backend not in {"docker_desktop", "macos_local"}:
        raise ValueError("unsupported capture backend")

    if selected_backend == "docker_desktop":
        selected_target = default_docker_capture_target() if target is None else CaptureTarget.model_validate(target)
        expected = default_docker_capture_target()
        if selected_target.id != expected.id or selected_target.kind != expected.kind:
            raise ValueError("docker_desktop only supports the isolated desktop target")
        return "docker_desktop", selected_target

    if target is None:
        raise ValueError("capture_target is required for macos_local")
    return "macos_local", CaptureTarget.model_validate(target)


def capture_selection_from_metadata(metadata: dict[str, Any]) -> tuple[CaptureBackendName, dict[str, Any]]:
    raw_capture = metadata.get("capture")
    if not isinstance(raw_capture, dict):
        default_target = default_docker_capture_target().model_dump()
        return "docker_desktop", default_target

    backend, target = resolve_capture_selection(
        raw_capture.get("backend"),
        raw_capture.get("target"),
    )
    return backend, target.model_dump()


class JobCreate(BaseModel):
    title: str
    source_url: str | None = None
    max_duration_minutes: int | None = None
    auto_stop_enabled: bool | None = None
    silence_timeout_minutes: int | None = None
    deepgram_model: str | None = None
    deepgram_language: str | None = None
    diarize: bool | None = None
    smart_format: bool | None = None
    interim_results: bool | None = None
    notify_email: str | None = None
    summary_model: str | None = None
    record_screen: bool = True
    generate_summary: bool = True
    mute_target_audio: bool = False
    capture_backend: CaptureBackendName = "docker_desktop"
    capture_target: CaptureTarget | None = None

    @model_validator(mode="after")
    def validate_capture_selection(self) -> "JobCreate":
        resolve_capture_selection(self.capture_backend, self.capture_target)
        if self.mute_target_audio:
            if self.capture_backend != "macos_local":
                raise ValueError("mute_target_audio is only supported for This Mac capture")
            if self.capture_target is None or self.capture_target.kind not in {"application", "window"}:
                raise ValueError("mute_target_audio requires an app or window target")
        return self


class SessionCredentials(BaseModel):
    username: str
    password: str


class SessionResponse(BaseModel):
    authenticated: bool
    username: str | None


class TranscriptSummaryGenerateRequest(BaseModel):
    prompt: str


class TranscriptSummarySaveRequest(BaseModel):
    request_id: str


class JobStopRequest(BaseModel):
    skip_summary: bool = False


class JobMuteTargetAudioRequest(BaseModel):
    mute_target_audio: bool


class TranscriptSummarySource(BaseModel):
    final_block_count: int
    interim_included: bool


class TranscriptSummaryGenerateResponse(BaseModel):
    request_id: str
    markdown: str
    provider: str
    source: TranscriptSummarySource


class ArtifactFile(BaseModel):
    name: str
    path: str
    size_bytes: int
    download_url: str


class ArtifactListResponse(BaseModel):
    job_id: str
    files: list[ArtifactFile]


class ArtifactsOverviewItem(BaseModel):
    job: "JobResponse"
    artifacts: ArtifactListResponse


class ArtifactsOverviewResponse(BaseModel):
    jobs: list[ArtifactsOverviewItem]


class JobResponse(BaseModel):
    id: str
    title: str
    source_url: str | None
    created_at: str
    started_at: str | None
    stopped_at: str | None
    state: str
    max_duration_minutes: int
    auto_stop_enabled: bool
    silence_timeout_minutes: int
    deepgram_model: str
    deepgram_language: str | None
    diarize: bool
    smart_format: bool
    interim_results: bool
    notify_email: str
    summary_model: str
    recording_path: str | None
    audio_path: str | None
    transcript_text_path: str | None
    transcript_events_path: str | None
    summary_path: str | None
    ffmpeg_pid: int | None
    live_audio_pid: int | None
    deepgram_request_id: str | None
    error_message: str | None
    capture_backend: CaptureBackendName
    capture_target: dict[str, Any]
    metadata_json: dict[str, Any]

    @classmethod
    def from_orm_job(cls, job: Job) -> "JobResponse":
        metadata_json = load_json(job.metadata_json)
        capture_backend, capture_target = capture_selection_from_metadata(metadata_json)
        return cls(
            id=job.id,
            title=job.title,
            source_url=job.source_url,
            created_at=isoformat(job.created_at) or "",
            started_at=isoformat(job.started_at),
            stopped_at=isoformat(job.stopped_at),
            state=job.state,
            max_duration_minutes=job.max_duration_minutes,
            auto_stop_enabled=job.auto_stop_enabled,
            silence_timeout_minutes=job.silence_timeout_minutes,
            deepgram_model=job.deepgram_model,
            deepgram_language=job.deepgram_language,
            diarize=job.diarize,
            smart_format=job.smart_format,
            interim_results=job.interim_results,
            notify_email=job.notify_email,
            summary_model=job.summary_model,
            recording_path=job.recording_path,
            audio_path=job.audio_path,
            transcript_text_path=job.transcript_text_path,
            transcript_events_path=job.transcript_events_path,
            summary_path=job.summary_path,
            ffmpeg_pid=job.ffmpeg_pid,
            live_audio_pid=job.live_audio_pid,
            deepgram_request_id=job.deepgram_request_id,
            error_message=job.error_message,
            capture_backend=capture_backend,
            capture_target=capture_target,
            metadata_json=metadata_json,
        )


class JobTransitionResponse(BaseModel):
    from_state: str | None
    to_state: str
    occurred_at: str
    reason: str
    payload: dict[str, Any]


class LiveSnapshot(BaseModel):
    final_blocks: list[dict[str, Any]] = Field(default_factory=list)
    interim: str = ""


class HealthCheckResult(BaseModel):
    ok: bool
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class HealthStatusResponse(BaseModel):
    desktop: HealthCheckResult
    deepgram: HealthCheckResult
    openclaw: HealthCheckResult


def merge_metadata(job: Job, updates: dict[str, Any]) -> None:
    current = load_json(job.metadata_json)
    current.update(updates)
    job.metadata_json = dump_json(current)
