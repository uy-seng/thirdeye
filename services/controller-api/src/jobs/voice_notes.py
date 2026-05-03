from __future__ import annotations

import base64
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from core.settings import Settings
from core.utils import ensure_directory, isoformat
from jobs.models import VoiceNoteResponse, VoiceNoteRow, VoiceNoteSummary, VoiceNoteUpdateRequest, VoiceNoteUpsertRequest


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _audio_extension(content_type: str) -> str:
    if content_type == "audio/webm":
        return "webm"
    if content_type == "audio/wav":
        return "wav"
    if content_type == "audio/mpeg":
        return "mp3"
    if content_type == "audio/mp4":
        return "m4a"
    return "bin"


@dataclass
class VoiceNoteRepository:
    settings: Settings
    session_factory: sessionmaker

    def list_notes(self) -> list[VoiceNoteResponse]:
        with self.session_factory() as session:
            rows = session.execute(select(VoiceNoteRow).order_by(VoiceNoteRow.created_at.desc())).scalars().all()
            return [self._response(row) for row in rows]

    def get_note(self, note_id: str) -> VoiceNoteResponse:
        with self.session_factory() as session:
            row = session.get(VoiceNoteRow, note_id)
            if row is None:
                raise KeyError(note_id)
            return self._response(row)

    def upsert_note(self, payload: VoiceNoteUpsertRequest) -> VoiceNoteResponse:
        with self.session_factory() as session:
            row = session.get(VoiceNoteRow, payload.id)
            if row is None:
                row = VoiceNoteRow(
                    id=payload.id,
                    title=payload.title,
                    transcript=payload.transcript,
                    created_at=_parse_iso_datetime(payload.created_at),
                    duration_ms=max(0, payload.duration_ms),
                )
            else:
                row.title = payload.title
                row.transcript = payload.transcript
                row.created_at = _parse_iso_datetime(payload.created_at)
                row.duration_ms = max(0, payload.duration_ms)
            if payload.audio_data_url is not None:
                audio_path, content_type = self._write_audio_data_url(payload.id, payload.audio_data_url)
                row.audio_path = str(audio_path)
                row.audio_content_type = content_type
            self._apply_summary(row, payload.summary)
            session.add(row)
            session.commit()
            return self._response(row)

    def update_note(self, note_id: str, payload: VoiceNoteUpdateRequest) -> VoiceNoteResponse:
        with self.session_factory() as session:
            row = session.get(VoiceNoteRow, note_id)
            if row is None:
                raise KeyError(note_id)
            if payload.title is not None:
                row.title = payload.title
            if payload.transcript is not None:
                row.transcript = payload.transcript
            if payload.duration_ms is not None:
                row.duration_ms = max(0, payload.duration_ms)
            if payload.audio_data_url is not None:
                audio_path, content_type = self._write_audio_data_url(note_id, payload.audio_data_url)
                row.audio_path = str(audio_path)
                row.audio_content_type = content_type
            if payload.summary is not None:
                self._apply_summary(row, payload.summary)
            session.add(row)
            session.commit()
            return self._response(row)

    def import_notes(self, notes: list[VoiceNoteUpsertRequest]) -> list[VoiceNoteResponse]:
        for note in notes:
            self.upsert_note(note)
        return self.list_notes()

    def delete_note(self, note_id: str) -> VoiceNoteResponse:
        with self.session_factory() as session:
            row = session.get(VoiceNoteRow, note_id)
            if row is None:
                raise KeyError(note_id)
            response = self._response(row)
            session.delete(row)
            session.commit()
        audio_root = self._note_root(note_id)
        if audio_root.exists():
            for path in audio_root.iterdir():
                if path.is_file():
                    path.unlink()
            with contextlib.suppress(OSError):
                audio_root.rmdir()
        return response

    def _write_audio_data_url(self, note_id: str, audio_data_url: str) -> tuple[Path, str]:
        header, separator, encoded = audio_data_url.partition(",")
        if separator != "," or ";base64" not in header:
            raise ValueError("audioDataUrl must be a base64 data URL")
        content_type = header.removeprefix("data:").split(";", 1)[0] or "application/octet-stream"
        audio_bytes = base64.b64decode(encoded)
        root = ensure_directory(self._note_root(note_id))
        path = root / f"audio.{_audio_extension(content_type)}"
        path.write_bytes(audio_bytes)
        return path, content_type

    def _note_root(self, note_id: str) -> Path:
        return self.settings.artifacts_root / "voice-notes" / note_id

    @staticmethod
    def _apply_summary(row: VoiceNoteRow, summary: VoiceNoteSummary | None) -> None:
        if summary is None:
            return
        row.summary_markdown = summary.markdown
        row.summary_provider = summary.provider
        row.summary_generated_at = _parse_iso_datetime(summary.generated_at)

    def _response(self, row: VoiceNoteRow) -> VoiceNoteResponse:
        audio_data_url = None
        if row.audio_path and row.audio_content_type:
            path = Path(row.audio_path)
            if path.exists():
                audio_data_url = f"data:{row.audio_content_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        summary = None
        if row.summary_markdown and row.summary_provider and row.summary_generated_at:
            summary = VoiceNoteSummary(
                markdown=row.summary_markdown,
                provider=row.summary_provider,
                generated_at=isoformat(row.summary_generated_at) or "",
            )
        return VoiceNoteResponse(
            id=row.id,
            title=row.title,
            transcript=row.transcript,
            created_at=isoformat(row.created_at) or "",
            duration_ms=row.duration_ms,
            audio_data_url=audio_data_url,
            summary=summary,
        )
