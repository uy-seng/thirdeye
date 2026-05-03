from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcripts.deepgram_client import normalize_deepgram_message, promote_interim_block, should_promote_interim
from core.utils import format_offset


TRANSCRIPT_SOURCE_ORDER = ("system", "microphone")
TRANSCRIPT_SOURCE_HEADINGS = {
    "system": "System Recording",
    "microphone": "Self",
}


@dataclass(frozen=True)
class TranscriptCompileResult:
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
        debug_output_dir: Path | None = None,
    ) -> TranscriptCompileResult:
        metadata: dict[str, Any] = {
            "job_id": job_id,
            "title": title,
            "started_at": started_at,
            "stopped_at": stopped_at,
            "model": model,
            "language": language,
            "request_id": None,
            "request_ids": {},
        }
        segments: list[dict[str, Any]] = []
        raw_lines: list[str] = []
        if events_path.exists():
            raw_lines = events_path.read_text(encoding="utf-8").splitlines()
        pending_interim: dict[str, dict[str, Any] | None] = {source: None for source in TRANSCRIPT_SOURCE_ORDER}
        for line in raw_lines:
            if not line.strip():
                continue
            raw = json.loads(line)
            normalized = normalize_deepgram_message(raw)
            source = self._source_for_segment(normalized)
            if normalized["type"] == "metadata":
                request_id = normalized.get("request_id")
                if request_id and metadata["request_id"] is None:
                    metadata["request_id"] = request_id
                if request_id:
                    metadata["request_ids"][source] = request_id
            if normalized["type"] == "final" and normalized.get("text"):
                segments.append(normalized)
                pending_interim[source] = None
            elif normalized["type"] == "interim":
                pending_interim[source] = normalized if str(normalized.get("text") or "").strip() else None
            elif should_promote_interim(normalized):
                promoted = promote_interim_block(pending_interim[source], normalized)
                if promoted is not None:
                    segments.append(promoted)
                    pending_interim[source] = None
        for source, interim in pending_interim.items():
            promoted = promote_interim_block(interim, {"type": "stream_end", "source": source})
            if promoted is not None:
                segments.append(promoted)

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
            ]
        )
        segments_by_source = self._segments_by_source(segments)
        for source in TRANSCRIPT_SOURCE_ORDER:
            heading = TRANSCRIPT_SOURCE_HEADINGS[source]
            source_segments = segments_by_source[source]
            markdown_lines.extend([f"## {heading}", ""])
            if not source_segments:
                markdown_lines.extend(["No transcript captured.", ""])
                continue
            for segment in source_segments:
                line = self._segment_line(segment)
                markdown_lines.append(f"- {line}")
            markdown_lines.append("")

        output_dir.mkdir(parents=True, exist_ok=True)
        debug_output_dir = debug_output_dir or output_dir
        debug_output_dir.mkdir(parents=True, exist_ok=True)
        markdown_path = output_dir / "transcript.md"
        json_path = debug_output_dir / "transcript.json"
        markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
        json_path.write_text(
            json.dumps({"metadata": metadata, "segments": segments}, indent=2),
            encoding="utf-8",
        )
        return TranscriptCompileResult(
            markdown_path=markdown_path,
            json_path=json_path,
        )

    @staticmethod
    def _source_for_segment(segment: dict[str, Any]) -> str:
        return "microphone" if segment.get("source") == "microphone" else "system"

    def _segments_by_source(self, segments: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped = {source: [] for source in TRANSCRIPT_SOURCE_ORDER}
        for segment in segments:
            grouped[self._source_for_segment(segment)].append(segment)
        return grouped

    def _segment_line(self, segment: dict[str, Any]) -> str:
        speaker_label = self._speaker_label(segment)
        return f"[{format_offset(segment['start'])} - {format_offset(segment['end'])}] {speaker_label}: {segment['text']}"

    def _speaker_label(self, segment: dict[str, Any]) -> str:
        if self._source_for_segment(segment) == "microphone":
            return TRANSCRIPT_SOURCE_HEADINGS["microphone"]
        if segment.get("speaker") is not None:
            return f"Speaker {segment['speaker']}"
        return "Speaker ?"
