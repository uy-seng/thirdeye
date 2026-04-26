from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jobs.models import ArtifactFile, ArtifactListResponse, JobResponse
from core.settings import Settings
from core.utils import ensure_directory, slugify, utcnow


@dataclass(frozen=True)
class JobArtifactPaths:
    root: Path
    recording: Path
    transcript_text: Path
    transcript_markdown: Path
    transcript_json: Path
    summary: Path
    deepgram_events: Path
    controller_events: Path
    metadata: Path


class ArtifactManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        ensure_directory(settings.artifacts_root)
        ensure_directory(settings.recordings_root)
        ensure_directory(settings.controller_events_root)

    def job_root(self, job_id: str) -> Path:
        return self.settings.artifacts_root / "jobs" / job_id

    def recording_root(self, job_id: str) -> Path:
        return self.settings.recordings_root / "jobs" / job_id

    def job_paths(self, job_id: str) -> JobArtifactPaths:
        root = ensure_directory(self.job_root(job_id))
        return JobArtifactPaths(
            root=root,
            recording=root / "recording.mp4",
            transcript_text=root / "transcript.txt",
            transcript_markdown=root / "transcript.md",
            transcript_json=root / "transcript.json",
            summary=root / "summary.md",
            deepgram_events=root / "deepgram-events.jsonl",
            controller_events=root / "controller-events.jsonl",
            metadata=root / "metadata.json",
        )

    def recording_stage_path(self, job_id: str) -> Path:
        return ensure_directory(self.recording_root(job_id)) / "recording.mp4"

    def live_audio_stage_path(self, job_id: str) -> Path:
        return ensure_directory(self.recording_root(job_id)) / "live_audio.pcm"

    def append_controller_event(self, job_id: str, event: dict[str, Any]) -> None:
        paths = self.job_paths(job_id)
        with paths.controller_events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def write_metadata(self, job: JobResponse) -> None:
        paths = self.job_paths(job.id)
        paths.metadata.write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def copy_recording(self, job_id: str) -> str:
        source = self.recording_stage_path(job_id)
        destination = self.job_paths(job_id).recording
        if not source.exists():
            raise FileNotFoundError(f"recording stage file is missing: {source}")
        shutil.copy2(source, destination)
        return str(destination)

    def list_files(self, job_id: str, controller_base_url: str) -> ArtifactListResponse:
        root = self.job_root(job_id)
        files: list[ArtifactFile] = []
        if root.exists():
            for path in sorted(root.iterdir()):
                if path.is_file():
                    files.append(
                        ArtifactFile(
                            name=path.name,
                            path=str(path),
                            size_bytes=path.stat().st_size,
                            download_url=f"{controller_base_url}/artifacts/{job_id}/{path.name}",
                        )
                    )
        return ArtifactListResponse(job_id=job_id, files=files)

    def write_transcript_summary(self, job_id: str, *, prompt: str, content: str) -> ArtifactFile:
        root = ensure_directory(self.job_root(job_id))
        timestamp = utcnow().strftime("%Y%m%d-%H%M%S")
        slug = slugify(prompt)
        filename = f"transcript-summary-{timestamp}-{slug}.md"
        path = root / filename
        suffix = 2
        while path.exists():
            filename = f"transcript-summary-{timestamp}-{slug}-{suffix}.md"
            path = root / filename
            suffix += 1
        normalized_content = content if content.endswith("\n") else f"{content}\n"
        path.write_text(normalized_content, encoding="utf-8")
        return ArtifactFile(
            name=filename,
            path=str(path),
            size_bytes=path.stat().st_size,
            download_url=f"{self.settings.controller_base_url}/artifacts/{job_id}/{filename}",
        )

    def cleanup_job(self, job_id: str) -> None:
        for root in (self.job_root(job_id), self.recording_root(job_id)):
            if root.exists():
                shutil.rmtree(root)
