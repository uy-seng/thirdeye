from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from jobs.artifacts import ArtifactManager
from transcripts.deepgram_client import normalize_deepgram_message, promote_interim_block, should_promote_interim


TRANSCRIPT_SOURCES = ("system", "microphone")


@dataclass
class TranscriptSnapshotState:
    final_blocks: list[dict[str, Any]] = field(default_factory=list)
    interim: str = ""
    interim_block: dict[str, Any] | None = None


@dataclass(frozen=True)
class TranscriptAppendResult:
    event: dict[str, Any]
    promoted: dict[str, Any] | None = None


class TranscriptStore:
    def __init__(self, artifacts: ArtifactManager) -> None:
        self.artifacts = artifacts
        self._snapshots: dict[str, dict[str, TranscriptSnapshotState] | TranscriptSnapshotState] = {}

    def append(self, job_id: str, raw_event: dict[str, Any]) -> TranscriptAppendResult:
        paths = self.artifacts.job_paths(job_id)
        with paths.deepgram_events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(raw_event, sort_keys=True) + "\n")
        self.artifacts.register_file(job_id, paths.deepgram_events, content_type="application/x-ndjson")
        normalized = normalize_deepgram_message(raw_event)
        snapshot = self._source_snapshots(job_id)[self._source_for_event(normalized)]
        promoted = self._apply_normalized_event(snapshot, normalized)
        return TranscriptAppendResult(event=normalized, promoted=promoted)

    def _apply_normalized_event(self, snapshot: TranscriptSnapshotState, normalized: dict[str, Any]) -> dict[str, Any] | None:
        if normalized["type"] == "final" and normalized.get("text"):
            snapshot.final_blocks.append(normalized)
            snapshot.interim = ""
            snapshot.interim_block = None
        elif normalized["type"] == "interim":
            snapshot.interim = normalized.get("text", "")
            snapshot.interim_block = normalized if snapshot.interim.strip() else None
        elif should_promote_interim(normalized):
            promoted = promote_interim_block(snapshot.interim_block or {"type": "interim", "text": snapshot.interim}, normalized)
            if promoted is not None:
                if "source" in normalized and "source" not in promoted:
                    promoted["source"] = normalized["source"]
                snapshot.final_blocks.append(promoted)
                snapshot.interim = ""
                snapshot.interim_block = None
            return promoted
        return None

    def snapshot(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._snapshots:
            self._snapshots[job_id] = self._rebuild(job_id)
        else:
            snapshots = self._source_snapshots(job_id)
            if self._snapshots_need_rebuild(snapshots):
                rebuilt = self._rebuild(job_id)
                if self._snapshots_have_transcript_text(rebuilt) or not self._snapshots_have_transcript_text(snapshots):
                    self._snapshots[job_id] = rebuilt
        snapshots = self._source_snapshots(job_id)
        system_snapshot = snapshots["system"]
        return {
            "final_blocks": system_snapshot.final_blocks,
            "interim": system_snapshot.interim,
            "sources": {
                source: {"final_blocks": snapshots[source].final_blocks, "interim": snapshots[source].interim}
                for source in TRANSCRIPT_SOURCES
            },
        }

    def refresh(self, job_id: str) -> dict[str, Any]:
        self._snapshots[job_id] = self._rebuild(job_id)
        return self.snapshot(job_id)

    def _snapshot_needs_rebuild(self, snapshot: TranscriptSnapshotState) -> bool:
        return any(
            block.get("type") == "final" and block.get("text") and "speech_final" not in block
            for block in snapshot.final_blocks
        )

    def _snapshots_need_rebuild(self, snapshots: dict[str, TranscriptSnapshotState]) -> bool:
        return any(self._snapshot_needs_rebuild(snapshot) for snapshot in snapshots.values())

    def _snapshots_have_transcript_text(self, snapshots: dict[str, TranscriptSnapshotState]) -> bool:
        return any(self._snapshot_has_transcript_text(snapshot) for snapshot in snapshots.values())

    @staticmethod
    def _snapshot_has_transcript_text(snapshot: TranscriptSnapshotState) -> bool:
        if snapshot.interim.strip():
            return True
        return any(str(block.get("text") or "").strip() for block in snapshot.final_blocks)

    def _rebuild(self, job_id: str) -> dict[str, TranscriptSnapshotState]:
        snapshots = self._empty_source_snapshots()
        path = self.artifacts.job_paths(job_id).deepgram_events
        if not path.exists():
            return snapshots
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            normalized = normalize_deepgram_message(json.loads(line))
            self._apply_normalized_event(snapshots[self._source_for_event(normalized)], normalized)
        return snapshots

    def _source_snapshots(self, job_id: str) -> dict[str, TranscriptSnapshotState]:
        snapshot = self._snapshots.get(job_id)
        if snapshot is None:
            snapshots = self._empty_source_snapshots()
            self._snapshots[job_id] = snapshots
            return snapshots
        if isinstance(snapshot, TranscriptSnapshotState):
            snapshots = self._empty_source_snapshots()
            snapshots["system"] = snapshot
            self._snapshots[job_id] = snapshots
            return snapshots
        for source in TRANSCRIPT_SOURCES:
            snapshot.setdefault(source, TranscriptSnapshotState())
        return snapshot

    @staticmethod
    def _empty_source_snapshots() -> dict[str, TranscriptSnapshotState]:
        return {source: TranscriptSnapshotState() for source in TRANSCRIPT_SOURCES}

    @staticmethod
    def _source_for_event(event: dict[str, Any]) -> str:
        return "microphone" if event.get("source") == "microphone" else "system"
