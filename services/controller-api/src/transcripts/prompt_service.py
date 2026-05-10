from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jobs.artifacts import ArtifactManager
from jobs.models import ArtifactFile, TranscriptSummaryGenerateResponse, TranscriptSummarySource
from core.prompts import read_prompt
from core.settings import Settings
from transcripts.store import TranscriptStore
from transcripts.summary_cache import TranscriptSummaryCache
from core.utils import format_offset, isoformat, utcnow

CANONICAL_SUMMARY_PROMPT_FILE = "canonical_summary.txt"
TRANSCRIPT_PROMPT_SOURCE_ORDER = ("system", "microphone")
TRANSCRIPT_PROMPT_SOURCE_LABELS = {
    "system": "System Recording",
    "microphone": "Self",
}


def default_canonical_summary_prompt() -> str:
    return read_prompt(CANONICAL_SUMMARY_PROMPT_FILE)


@dataclass
class TranscriptPromptService:
    settings: Settings
    jobs: Any
    artifacts: ArtifactManager
    transcript_store: TranscriptStore
    openclaw: Any
    cache: TranscriptSummaryCache

    async def generate(self, *, job_id: str, prompt: str) -> TranscriptSummaryGenerateResponse:
        job, normalized_prompt, transcript_text, source = self._prepare_request(job_id=job_id, prompt=prompt)
        markdown, provider = await self._request_summary(
            prompt=normalized_prompt,
            transcript_text=transcript_text,
            title=job.title,
            model=job.summary_model,
        )

        cached = self.cache.store(job_id=job_id, prompt=normalized_prompt, markdown=markdown)
        self.artifacts.append_controller_event(
            job_id,
            {
                "type": "transcript_summary_generated",
                "job_id": job_id,
                "request_id": cached.request_id,
                "provider": provider,
                "timestamp": isoformat(utcnow()),
            },
        )
        return TranscriptSummaryGenerateResponse(
            request_id=cached.request_id,
            markdown=markdown,
            provider=provider,
            source=source,
        )

    async def rewrite_canonical_summary(
        self,
        *,
        job_id: str,
        prompt: str | None = None,
    ) -> str:
        job, normalized_prompt, transcript_text, source = self._prepare_request(
            job_id=job_id,
            prompt=prompt if prompt is not None else default_canonical_summary_prompt(),
            refresh_snapshot=True,
        )
        markdown, provider = await self._request_summary(
            prompt=normalized_prompt,
            transcript_text=transcript_text,
            title=job.title,
            model=job.summary_model,
        )
        summary_path = self.artifacts.job_paths(job_id).summary
        summary_path.write_text(self._normalize_markdown(markdown), encoding="utf-8")
        self.artifacts.register_file(job_id, summary_path, content_type="text/markdown")
        self.artifacts.append_controller_event(
            job_id,
            {
                "type": "summary_rerun_completed",
                "job_id": job_id,
                "provider": provider,
                "source": source.model_dump(),
                "timestamp": isoformat(utcnow()),
            },
        )
        return str(summary_path)

    def save(self, *, job_id: str, request_id: str) -> ArtifactFile:
        self.jobs.get_job(job_id)
        cached = self.cache.pop(job_id=job_id, request_id=request_id)
        artifact = self.artifacts.write_transcript_summary(
            job_id,
            prompt=cached.prompt,
            content=cached.markdown,
        )
        self.artifacts.append_controller_event(
            job_id,
            {
                "type": "transcript_summary_saved",
                "job_id": job_id,
                "request_id": request_id,
                "artifact_name": artifact.name,
                "timestamp": isoformat(utcnow()),
            },
        )
        return artifact

    def _prepare_request(self, *, job_id: str, prompt: str, refresh_snapshot: bool = False) -> tuple[Any, str, str, TranscriptSummarySource]:
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise ValueError("prompt is required")

        job = self.jobs.get_job(job_id)
        snapshot = self.transcript_store.refresh(job_id) if refresh_snapshot else self.transcript_store.snapshot(job_id)
        transcript_text, source = self._serialize_snapshot(snapshot)
        if not transcript_text:
            raise ValueError("transcript snapshot is empty")
        return job, normalized_prompt, transcript_text, source

    async def _request_summary(
        self,
        *,
        prompt: str,
        transcript_text: str,
        title: str,
        model: str | None = None,
    ) -> tuple[str, str]:
        response = await self.openclaw.generate_transcript_summary(
            prompt=prompt,
            transcript_text=transcript_text,
            title=title,
            model=self._effective_summary_model(model),
        )
        markdown = str(response.get("markdown", "")).strip()
        if not markdown:
            raise RuntimeError("OpenClaw LLM returned no text")
        return markdown, str(response.get("provider", "openclaw"))

    def _effective_summary_model(self, model: str | None) -> str:
        candidate = (model or "").strip()
        if not candidate:
            return self.settings.openclaw_summary_model
        return candidate

    @staticmethod
    def _normalize_markdown(markdown: str) -> str:
        return markdown if markdown.endswith("\n") else f"{markdown}\n"

    def _serialize_snapshot(self, snapshot: dict[str, Any]) -> tuple[str, TranscriptSummarySource]:
        sources = snapshot.get("sources")
        if isinstance(sources, dict):
            return self._serialize_source_snapshots(sources)

        final_blocks = snapshot.get("final_blocks") or []
        interim = str(snapshot.get("interim") or "").strip()
        lines, final_block_count, interim_included = self._serialize_lines(
            final_blocks=final_blocks,
            interim=interim,
            source=None,
        )
        source = TranscriptSummarySource(
            final_block_count=final_block_count,
            interim_included=interim_included,
        )
        return ("\n".join(lines).strip(), source)

    def _serialize_source_snapshots(self, sources: dict[str, Any]) -> tuple[str, TranscriptSummarySource]:
        lines: list[str] = []
        final_block_count = 0
        interim_included = False

        for source in TRANSCRIPT_PROMPT_SOURCE_ORDER:
            source_snapshot = sources.get(source)
            if not isinstance(source_snapshot, dict):
                continue

            source_lines, source_final_count, source_interim_included = self._serialize_lines(
                final_blocks=source_snapshot.get("final_blocks") or [],
                interim=str(source_snapshot.get("interim") or "").strip(),
                source=source,
            )
            if not source_lines:
                continue

            if lines:
                lines.append("")
            lines.append(f"{TRANSCRIPT_PROMPT_SOURCE_LABELS[source]}:")
            lines.extend(source_lines)
            final_block_count += source_final_count
            interim_included = interim_included or source_interim_included

        source = TranscriptSummarySource(
            final_block_count=final_block_count,
            interim_included=interim_included,
        )
        return ("\n".join(lines).strip(), source)

    def _serialize_lines(self, *, final_blocks: list[Any], interim: str, source: str | None) -> tuple[list[str], int, bool]:
        lines: list[str] = []
        final_block_count = 0
        for block in final_blocks:
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or "").strip()
            if not text:
                continue
            start = block.get("start")
            end = block.get("end")
            speaker = block.get("speaker")
            prefix = self._line_prefix(start=start, end=end, speaker=speaker, source=source)
            lines.append(f"{prefix}{text}")
            final_block_count += 1
        if interim:
            lines.append(f"[DRAFT] {self._speaker_label(speaker=None, source=source)}{interim}")
        return lines, final_block_count, bool(interim)

    @staticmethod
    def _line_prefix(*, start: Any, end: Any, speaker: Any, source: str | None) -> str:
        parts: list[str] = []
        if isinstance(start, (float, int)):
            label = format_offset(float(start))
            if isinstance(end, (float, int)):
                label = f"{label}-{format_offset(float(end))}"
            parts.append(f"[{label}]")
        speaker_label = TranscriptPromptService._speaker_label(speaker=speaker, source=source)
        if speaker_label:
            parts.append(speaker_label)
        if not parts:
            return ""
        return " ".join(parts) + " "

    @staticmethod
    def _speaker_label(*, speaker: Any, source: str | None) -> str:
        if source == "microphone":
            return "Self:"
        if speaker is not None:
            return f"Speaker {speaker}:"
        return ""
