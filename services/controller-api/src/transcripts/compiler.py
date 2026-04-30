from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcripts.deepgram_client import normalize_deepgram_message, promote_interim_block, should_promote_interim
from core.utils import format_offset


@dataclass(frozen=True)
class TranscriptCompileResult:
    text_path: Path
    markdown_path: Path
    json_path: Path


class TranscriptCompiler:
    def compile(
        self,
        *,
        job_id: str,
        title: str,
        started_at: str | None,
        stopped_at: str | None,
        model: str,
        language: str | None,
        events_path: Path,
        output_dir: Path,
    ) -> TranscriptCompileResult:
        metadata: dict[str, Any] = {
            "job_id": job_id,
            "title": title,
            "started_at": started_at,
            "stopped_at": stopped_at,
            "model": model,
            "language": language,
            "request_id": None,
        }
        segments: list[dict[str, Any]] = []
        raw_lines: list[str] = []
        if events_path.exists():
            raw_lines = events_path.read_text(encoding="utf-8").splitlines()
        pending_interim: dict[str, Any] | None = None
        for line in raw_lines:
            if not line.strip():
                continue
            raw = json.loads(line)
            normalized = normalize_deepgram_message(raw)
            if normalized["type"] == "metadata":
                metadata["request_id"] = normalized.get("request_id")
            if normalized["type"] == "final" and normalized.get("text"):
                segments.append(normalized)
                pending_interim = None
            elif normalized["type"] == "interim":
                pending_interim = normalized if str(normalized.get("text") or "").strip() else None
            elif should_promote_interim(normalized):
                promoted = promote_interim_block(pending_interim, normalized)
                if promoted is not None:
                    segments.append(promoted)
                    pending_interim = None
        promoted = promote_interim_block(pending_interim, {"type": "stream_end"})
        if promoted is not None:
            segments.append(promoted)

        text_lines = [
            f"Job ID: {metadata['job_id']}",
            f"Title: {metadata['title']}",
            f"Start Time: {metadata['started_at'] or 'unknown'}",
            f"Stop Time: {metadata['stopped_at'] or 'unknown'}",
            f"Deepgram Request ID: {metadata['request_id'] or 'unknown'}",
            f"Model: {metadata['model']}",
            f"Language: {metadata['language'] or 'auto'}",
            "",
        ]
        markdown_lines = [f"# {title}", "", "## Metadata", ""]
        markdown_lines.extend(
            [
                f"- Job ID: {metadata['job_id']}",
                f"- Start Time: {metadata['started_at'] or 'unknown'}",
                f"- Stop Time: {metadata['stopped_at'] or 'unknown'}",
                f"- Deepgram Request ID: {metadata['request_id'] or 'unknown'}",
                f"- Model: {metadata['model']}",
                f"- Language: {metadata['language'] or 'auto'}",
                "",
                "## Transcript",
                "",
            ]
        )
        for segment in segments:
            speaker_label = f"Speaker {segment['speaker']}" if segment.get("speaker") is not None else "Speaker ?"
            line = f"[{format_offset(segment['start'])} - {format_offset(segment['end'])}] {speaker_label}: {segment['text']}"
            text_lines.append(line)
            markdown_lines.append(f"- {line}")

        output_dir.mkdir(parents=True, exist_ok=True)
        text_path = output_dir / "transcript.txt"
        markdown_path = output_dir / "transcript.md"
        json_path = output_dir / "transcript.json"
        text_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")
        markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
        json_path.write_text(
            json.dumps({"metadata": metadata, "segments": segments}, indent=2),
            encoding="utf-8",
        )
        return TranscriptCompileResult(
            text_path=text_path,
            markdown_path=markdown_path,
            json_path=json_path,
        )
