from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from jobs.models import ArtifactFile, ArtifactListResponse, ArtifactManifest, JobResponse
from core.settings import Settings
from core.utils import ensure_directory, slugify, utcnow


LOG_ROOT_ARTIFACT_NAMES = {
    "controller-events.jsonl",
    "deepgram-events.jsonl",
    "metadata.json",
    "transcript.json",
    "transcript.txt",
}
MEDIA_COMMAND_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class JobArtifactPaths:
    root: Path
    logs_root: Path
    recording: Path
    transcript_markdown: Path
    transcript_json: Path
    summary: Path
    deepgram_events: Path
    controller_events: Path
    metadata: Path


class ArtifactManager:
    def __init__(self, settings: Settings, session_factory: sessionmaker | None = None) -> None:
        self.settings = settings
        self.session_factory = session_factory
        ensure_directory(settings.artifacts_root)
        ensure_directory(settings.debug_logs_root)
        ensure_directory(settings.recordings_root)
        ensure_directory(settings.controller_events_root)

    def job_root(self, job_id: str) -> Path:
        return self.settings.artifacts_root / "jobs" / job_id

    def recording_root(self, job_id: str) -> Path:
        return self.settings.recordings_root / "jobs" / job_id

    def job_logs_root(self, job_id: str) -> Path:
        return self.settings.debug_logs_root / "jobs" / job_id

    def job_paths(self, job_id: str) -> JobArtifactPaths:
        root = ensure_directory(self.job_root(job_id))
        logs_root = ensure_directory(self.job_logs_root(job_id))
        self._migrate_legacy_log_files(job_id, root, logs_root)
        return JobArtifactPaths(
            root=root,
            logs_root=logs_root,
            recording=root / "recording.mp4",
            transcript_markdown=root / "transcript.md",
            transcript_json=logs_root / "transcript.json",
            summary=root / "summary.md",
            deepgram_events=logs_root / "deepgram-events.jsonl",
            controller_events=logs_root / "controller-events.jsonl",
            metadata=logs_root / "metadata.json",
        )

    def recording_stage_path(self, job_id: str) -> Path:
        return ensure_directory(self.recording_root(job_id)) / "recording.mp4"

    def live_audio_stage_path(self, job_id: str) -> Path:
        return ensure_directory(self.recording_root(job_id)) / "live_audio.pcm"

    def microphone_stage_path(self, job_id: str) -> Path:
        return ensure_directory(self.recording_root(job_id)) / "microphone_audio.pcm"

    def mixed_recording_stage_path(self, job_id: str) -> Path:
        return ensure_directory(self.recording_root(job_id)) / "recording.mixed.mp4"

    def mix_recording_with_microphone(self, job_id: str) -> Path:
        recording_path = self.recording_stage_path(job_id)
        microphone_path = self.microphone_stage_path(job_id)
        mixed_path = self.mixed_recording_stage_path(job_id)
        if not recording_path.exists():
            raise FileNotFoundError(f"recording stage file is missing: {recording_path}")
        if not microphone_path.exists() or microphone_path.stat().st_size == 0:
            raise FileNotFoundError(f"processed microphone stage file is missing: {microphone_path}")

        ffmpeg = os.environ.get("FFMPEG_BIN", "ffmpeg")
        has_audio = self._recording_has_audio(recording_path)
        if mixed_path.exists():
            mixed_path.unlink()
        command = self._mix_command(ffmpeg, recording_path, microphone_path, mixed_path, has_audio=has_audio)
        result = self._run_media_command(command)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "ffmpeg failed to mix processed microphone audio").strip()
            raise RuntimeError(f"failed to mix processed microphone audio: {detail}")
        if not mixed_path.exists():
            raise RuntimeError("failed to mix processed microphone audio: mixed recording was not created")
        shutil.move(str(mixed_path), str(recording_path))
        return recording_path

    def _recording_has_audio(self, recording_path: Path) -> bool:
        ffprobe = os.environ.get("FFPROBE_BIN", "ffprobe")
        command = [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(recording_path),
        ]
        result = self._run_media_command(command)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "ffprobe could not inspect the recording").strip()
            raise RuntimeError(f"failed to inspect recording audio streams: {detail}")
        return bool(result.stdout.strip())

    @staticmethod
    def _run_media_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=MEDIA_COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"{command[0]} is unavailable; configure FFMPEG_BIN and FFPROBE_BIN") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{command[0]} timed out after {MEDIA_COMMAND_TIMEOUT_SECONDS}s") from exc

    @staticmethod
    def _mix_command(ffmpeg: str, recording_path: Path, microphone_path: Path, mixed_path: Path, *, has_audio: bool) -> list[str]:
        base = [
            ffmpeg,
            "-nostdin",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(recording_path),
            "-f",
            "s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-i",
            str(microphone_path),
        ]
        if has_audio:
            return [
                *base,
                "-filter_complex",
                "[1:a]aresample=48000[mic];[0:a][mic]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(mixed_path),
            ]
        return [
            *base,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(mixed_path),
        ]

    def append_controller_event(self, job_id: str, event: dict[str, Any]) -> None:
        paths = self.job_paths(job_id)
        with paths.controller_events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        self.register_file(job_id, paths.controller_events, content_type="application/x-ndjson")

    def write_metadata(self, job: JobResponse) -> None:
        paths = self.job_paths(job.id)
        paths.metadata.write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def copy_recording(self, job_id: str) -> str:
        source = self.recording_stage_path(job_id)
        destination = self.job_paths(job_id).recording
        if not source.exists():
            raise FileNotFoundError(f"recording stage file is missing: {source}")
        shutil.copy2(source, destination)
        self.register_file(job_id, destination, content_type="video/mp4")
        return str(destination)

    def list_files(self, job_id: str, controller_base_url: str) -> ArtifactListResponse:
        if self.session_factory is not None:
            files = self._list_manifest_files(job_id, controller_base_url)
            return ArtifactListResponse(job_id=job_id, files=files)

        root = self.job_root(job_id)
        files: list[ArtifactFile] = []
        if root.exists():
            for path in sorted(root.iterdir()):
                if path.is_file() and not self._is_internal_artifact_name(path.name):
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
        return self.register_file(job_id, path, content_type="text/markdown")

    def register_file(self, job_id: str, path: Path, content_type: str | None = None) -> ArtifactFile:
        path = path.resolve()
        root = self._download_root_for_path(job_id, path)
        if not path.exists():
            raise FileNotFoundError(f"artifact file is missing: {path}")
        if root is None:
            raise ValueError("artifact path must be inside the job artifact or debug log directory")
        if path.name != path.relative_to(root).as_posix():
            raise ValueError("nested artifact paths are not downloadable")

        now = utcnow()
        size_bytes = path.stat().st_size
        if self.session_factory is not None:
            with self.session_factory() as session:
                existing = session.execute(
                    select(ArtifactManifest).where(
                        ArtifactManifest.job_id == job_id,
                        ArtifactManifest.name == path.name,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        ArtifactManifest(
                            job_id=job_id,
                            name=path.name,
                            path=str(path),
                            content_type=content_type,
                            size_bytes=size_bytes,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    existing.path = str(path)
                    existing.content_type = content_type
                    existing.size_bytes = size_bytes
                    existing.updated_at = now
                    session.add(existing)
                session.commit()

        return ArtifactFile(
            name=path.name,
            path=str(path),
            size_bytes=size_bytes,
            download_url=f"{self.settings.controller_base_url}/artifacts/{job_id}/{path.name}",
        )

    def path_for_download(self, job_id: str, filename: str) -> Path | None:
        if Path(filename).name != filename:
            return None
        if self._is_internal_artifact_name(filename):
            return None
        if self.session_factory is None:
            return None
        with self.session_factory() as session:
            row = session.execute(
                select(ArtifactManifest).where(
                    ArtifactManifest.job_id == job_id,
                    ArtifactManifest.name == filename,
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        path = Path(row.path).resolve()
        if self._download_root_for_path(job_id, path) is None or not path.exists():
            return None
        return path

    def _download_root_for_path(self, job_id: str, path: Path) -> Path | None:
        for root in (self.job_root(job_id).resolve(), self.job_logs_root(job_id).resolve()):
            if path == root or root in path.parents:
                return root
        return None

    def _list_manifest_files(self, job_id: str, controller_base_url: str) -> list[ArtifactFile]:
        assert self.session_factory is not None
        files: list[ArtifactFile] = []
        with self.session_factory() as session:
            rows = session.execute(
                select(ArtifactManifest).where(ArtifactManifest.job_id == job_id).order_by(ArtifactManifest.name)
            ).scalars().all()
        for row in rows:
            if self._is_internal_artifact_name(row.name):
                continue
            path = Path(row.path)
            if not path.exists() or not path.is_file():
                continue
            files.append(
                ArtifactFile(
                    name=row.name,
                    path=str(path),
                    size_bytes=path.stat().st_size,
                    download_url=f"{controller_base_url}/artifacts/{job_id}/{row.name}",
                )
            )
        return files

    @staticmethod
    def _is_internal_artifact_name(name: str) -> bool:
        return name in {"metadata.json", "transcript.txt"}

    def _migrate_legacy_log_files(self, job_id: str, root: Path, logs_root: Path) -> None:
        for name in LOG_ROOT_ARTIFACT_NAMES:
            legacy_path = root / name
            if not legacy_path.is_file():
                continue

            log_path = logs_root / name
            if log_path.exists() and legacy_path.stat().st_mtime <= log_path.stat().st_mtime:
                legacy_path.unlink()
            else:
                if log_path.exists():
                    log_path.unlink()
                shutil.move(str(legacy_path), str(log_path))

            self._update_manifest_path(job_id, name, log_path)

    def _update_manifest_path(self, job_id: str, name: str, path: Path) -> None:
        if self.session_factory is None:
            return
        now = utcnow()
        with self.session_factory() as session:
            existing = session.execute(
                select(ArtifactManifest).where(
                    ArtifactManifest.job_id == job_id,
                    ArtifactManifest.name == name,
                )
            ).scalar_one_or_none()
            if existing is None:
                return
            existing.path = str(path)
            existing.size_bytes = path.stat().st_size
            existing.updated_at = now
            session.add(existing)
            session.commit()

    def cleanup_job(self, job_id: str) -> None:
        for root in (self.job_root(job_id), self.recording_root(job_id), self.job_logs_root(job_id)):
            if root.exists():
                shutil.rmtree(root)
