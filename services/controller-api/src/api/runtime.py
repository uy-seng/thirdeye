from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from jobs.artifacts import ArtifactManager
from capture.backends import CaptureBackendRegistry, build_capture_backends
from db.db import Base, create_session_factory, ensure_schema_compatibility
from transcripts.deepgram_client import DeepgramClient
from transcripts.deepgram_relay import RelayManager
from jobs.jobs import CaptureRuntime, JobRepository
from transcripts.live_transcript import TranscriptHub
from core.logging import configure_logging
from integrations.openclaw_client import OpenClawClient
from jobs.recovery import RecoveryService
from core.settings import Settings
from jobs.state_machine import JobStateMachine
from transcripts.compiler import TranscriptCompiler
from transcripts.prompt_service import TranscriptPromptService
from transcripts.store import TranscriptStore
from transcripts.summary_cache import TranscriptSummaryCache
from core.utils import ensure_directory


@dataclass
class AppRuntime:
    settings: Settings
    session_factory: sessionmaker
    artifacts: ArtifactManager
    jobs: JobRepository
    capture: CaptureRuntime
    transcript_hub: TranscriptHub
    transcript_store: TranscriptStore
    recovery: RecoveryService
    capture_backends: CaptureBackendRegistry
    desktop: object
    openclaw: OpenClawClient
    transcript_summary_cache: TranscriptSummaryCache
    transcript_prompts: TranscriptPromptService


def create_runtime(settings: Settings) -> AppRuntime:
    configure_logging(settings.log_level)
    ensure_directory(settings.artifacts_root)
    ensure_directory(settings.recordings_root)
    session_factory = create_session_factory(settings.controller_db_path)
    Base.metadata.create_all(session_factory.kw["bind"])
    ensure_schema_compatibility(session_factory.kw["bind"])
    artifacts = ArtifactManager(settings)
    transcript_hub = TranscriptHub()
    transcript_store = TranscriptStore(artifacts)
    state_machine = JobStateMachine()
    jobs = JobRepository(session_factory, settings, artifacts, state_machine)
    capture_backends = build_capture_backends(settings)
    desktop = capture_backends.require("docker_desktop")
    openclaw = OpenClawClient(settings)
    transcript_summary_cache = TranscriptSummaryCache()
    transcript_prompts = TranscriptPromptService(
        settings=settings,
        jobs=jobs,
        artifacts=artifacts,
        transcript_store=transcript_store,
        openclaw=openclaw,
        cache=transcript_summary_cache,
    )
    relay_manager = RelayManager(
        settings=settings,
        deepgram_client=DeepgramClient(settings),
        on_event=None,  # type: ignore[arg-type]
        on_degraded=None,  # type: ignore[arg-type]
    )
    capture = CaptureRuntime(
        settings=settings,
        jobs=jobs,
        artifacts=artifacts,
        transcript_store=transcript_store,
        transcript_compiler=TranscriptCompiler(),
        transcript_prompts=transcript_prompts,
        relay_manager=relay_manager,
        capture_backends=capture_backends,
        transcript_hub=transcript_hub,
    )
    relay_manager.on_event = capture.handle_deepgram_event  # type: ignore[assignment]
    relay_manager.on_degraded = capture.mark_degraded  # type: ignore[assignment]
    recovery = RecoveryService(jobs, capture_backends, capture)
    return AppRuntime(
        settings=settings,
        session_factory=session_factory,
        artifacts=artifacts,
        jobs=jobs,
        capture=capture,
        transcript_hub=transcript_hub,
        transcript_store=transcript_store,
        recovery=recovery,
        capture_backends=capture_backends,
        desktop=desktop,
        openclaw=openclaw,
        transcript_summary_cache=transcript_summary_cache,
        transcript_prompts=transcript_prompts,
    )
