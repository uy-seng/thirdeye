from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from jobs.artifacts import ArtifactManager
from transcripts.deepgram_client import normalize_deepgram_message, promote_interim_block, should_promote_interim


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
        self._snapshots: dict[str, TranscriptSnapshotState] = defaultdict(TranscriptSnapshotState)

    def append(self, job_id: str, raw_event: dict[str, Any]) -> TranscriptAppendResult:
        paths = self.artifacts.job_paths(job_id)
        with paths.deepgram_events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(raw_event, sort_keys=True) + "\n")
        normalized = normalize_deepgram_message(raw_event)
        snapshot = self._snapshots[job_id]
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
                snapshot.final_blocks.append(promoted)
                snapshot.interim = ""
                snapshot.interim_block = None
            return promoted
        return None

    def snapshot(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._snapshots:
            self._snapshots[job_id] = self._rebuild(job_id)
        elif self._snapshot_needs_rebuild(self._snapshots[job_id]):
            self._snapshots[job_id] = self._rebuild(job_id)
        snapshot = self._snapshots[job_id]
        return {"final_blocks": snapshot.final_blocks, "interim": snapshot.interim}

    def _snapshot_needs_rebuild(self, snapshot: TranscriptSnapshotState) -> bool:
        return any(
            block.get("type") == "final" and block.get("text") and "speech_final" not in block
            for block in snapshot.final_blocks
        )

    def _rebuild(self, job_id: str) -> TranscriptSnapshotState:
        snapshot = TranscriptSnapshotState()
        path = self.artifacts.job_paths(job_id).deepgram_events
        if not path.exists():
            return snapshot
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            normalized = normalize_deepgram_message(json.loads(line))
            self._apply_normalized_event(snapshot, normalized)
        return snapshot
