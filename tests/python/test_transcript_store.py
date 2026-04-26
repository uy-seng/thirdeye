from __future__ import annotations

import json

from jobs.artifacts import ArtifactManager
from transcripts.store import TranscriptSnapshotState, TranscriptStore


def test_snapshot_rebuilds_cached_blocks_missing_speech_final(settings) -> None:
    store = TranscriptStore(ArtifactManager(settings))
    job_id = "job-rehydrate"
    raw_event = {
        "type": "Results",
        "is_final": True,
        "speech_final": False,
        "start": 1307.69,
        "duration": 3.7700195,
        "channel": {
            "alternatives": [
                {
                    "transcript": "We can have",
                    "words": [
                        {"speaker": 1, "start": 1310.33, "end": 1310.6499, "word": "we"},
                        {"speaker": 1, "start": 1310.6499, "end": 1310.8899, "word": "can"},
                        {"speaker": 1, "start": 1310.8899, "end": 1311.1299, "word": "have"},
                    ],
                }
            ]
        },
    }
    paths = store.artifacts.job_paths(job_id)
    paths.deepgram_events.write_text(f"{json.dumps(raw_event, sort_keys=True)}\n", encoding="utf-8")
    store._snapshots[job_id] = TranscriptSnapshotState(
        final_blocks=[
            {
                "type": "final",
                "text": "We can have",
                "speaker": 1,
                "start": 1307.69,
                "end": 1311.4600195,
            }
        ],
        interim="",
    )

    snapshot = store.snapshot(job_id)

    assert snapshot["final_blocks"] == [
        {
            "type": "final",
            "text": "We can have",
            "speaker": 1,
            "start": 1307.69,
            "end": 1311.4600195,
            "speech_final": False,
        }
    ]
