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


def test_store_promotes_pending_interim_when_terminal_metadata_arrives(settings) -> None:
    store = TranscriptStore(ArtifactManager(settings))
    job_id = "job-terminal-interim"

    store.append(
        job_id,
        {
            "type": "Results",
            "is_final": False,
            "start": 16.24,
            "duration": 2.05,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "And I hide out in the stall.",
                        "words": [{"speaker": 0, "start": 16.24, "end": 17.44}],
                    }
                ]
            },
        },
    )
    store.append(
        job_id,
        {
            "type": "Metadata",
            "request_id": "request-123",
            "duration": 18.29,
            "model_info": {"model-id": {"name": "general-nova-3"}},
        },
    )

    snapshot = store.snapshot(job_id)

    assert snapshot["interim"] == ""
    assert snapshot["final_blocks"] == [
        {
            "type": "final",
            "text": "And I hide out in the stall.",
            "speaker": 0,
            "start": 16.24,
            "end": 18.29,
            "speech_final": True,
            "promoted_from_interim": True,
            "promotion_reason": "metadata",
        }
    ]
