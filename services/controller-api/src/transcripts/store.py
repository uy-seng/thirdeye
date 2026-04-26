from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from jobs.artifacts import ArtifactManager
from transcripts.deepgram_client import normalize_deepgram_message


@dataclass
class TranscriptSnapshotState:
    final_blocks: list[dict[str, Any]] = field(default_factory=list)
    interim: str = ""


class TranscriptStore:
    def __init__(self, artifacts: ArtifactManager) -> None:
        self.artifacts = artifacts
        self._snapshots: dict[str, TranscriptSnapshotState] = defaultdict(TranscriptSnapshotState)

    def append(self, job_id: str, raw_event: dict[str, Any]) -> dict[str, Any]:
        paths = self.artifacts.job_paths(job_id)
        with paths.deepgram_events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(raw_event, sort_keys=True) + "\n")
        normalized = normalize_deepgram_message(raw_event)
        snapshot = self._snapshots[job_id]
        if normalized["type"] == "final" and normalized.get("text"):
            snapshot.final_blocks.append(normalized)
            snapshot.interim = ""
        elif normalized["type"] == "interim":
            snapshot.interim = normalized.get("text", "")
        return normalized

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
            if normalized["type"] == "final" and normalized.get("text"):
                snapshot.final_blocks.append(normalized)
            elif normalized["type"] == "interim":
                snapshot.interim = normalized.get("text", "")
        return snapshot
