from __future__ import annotations

import json
from pathlib import Path

from transcripts.compiler import TranscriptCompiler


def test_compiler_emits_text_markdown_and_json(tmp_path: Path) -> None:
    events_path = tmp_path / "deepgram-events.jsonl"
    raw_events = [
        {"type": "Metadata", "request_id": "req-123", "model_info": {"name": "nova-3"}},
        {
            "type": "Results",
            "is_final": True,
            "start": 0.0,
            "duration": 1.5,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "Opening remarks",
                        "words": [{"speaker": 1, "start": 0.0, "end": 1.5}],
                    }
                ]
            },
        },
        {
            "type": "Results",
            "is_final": True,
            "start": 2.0,
            "duration": 1.0,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "Follow up question",
                        "words": [{"speaker": 2, "start": 2.0, "end": 3.0}],
                    }
                ]
            },
        },
    ]
    events_path.write_text(
        "\n".join(json.dumps(item) for item in raw_events) + "\n",
        encoding="utf-8",
    )

    compiler = TranscriptCompiler()
    result = compiler.compile(
        job_id="job-123",
        title="Authorized public stream",
        started_at="2026-04-17T18:00:00Z",
        stopped_at="2026-04-17T18:05:00Z",
        model="nova-3",
        language="en",
        events_path=events_path,
        output_dir=tmp_path,
    )

    assert result.text_path.exists()
    assert result.markdown_path.exists()
    assert result.json_path.exists()
    text = result.text_path.read_text(encoding="utf-8")
    assert "Job ID: job-123" in text
    assert "[00:00.000 - 00:01.500] Speaker 1: Opening remarks" in text
    assert "[00:02.000 - 00:03.000] Speaker 2: Follow up question" in text

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["request_id"] == "req-123"
    assert payload["segments"][0]["speaker"] == 1


def test_compiler_handles_missing_events_file(tmp_path: Path) -> None:
    compiler = TranscriptCompiler()
    result = compiler.compile(
        job_id="job-456",
        title="Authorized public stream",
        started_at="2026-04-17T18:00:00Z",
        stopped_at="2026-04-17T18:05:00Z",
        model="nova-3",
        language="en",
        events_path=tmp_path / "missing-events.jsonl",
        output_dir=tmp_path,
    )

    text = result.text_path.read_text(encoding="utf-8")
    assert "Job ID: job-456" in text

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["request_id"] is None
    assert payload["segments"] == []


def test_compiler_keeps_unfinalized_interim_when_stream_ends(tmp_path: Path) -> None:
    events_path = tmp_path / "deepgram-events.jsonl"
    raw_events = [
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
        {
            "type": "Metadata",
            "request_id": "request-123",
            "duration": 18.29,
            "model_info": {"model-id": {"name": "general-nova-3"}},
        },
    ]
    events_path.write_text(
        "\n".join(json.dumps(item) for item in raw_events) + "\n",
        encoding="utf-8",
    )

    compiler = TranscriptCompiler()
    result = compiler.compile(
        job_id="job-terminal-interim",
        title="Authorized public stream",
        started_at="2026-04-17T18:00:00Z",
        stopped_at="2026-04-17T18:05:00Z",
        model="nova-3",
        language="en",
        events_path=events_path,
        output_dir=tmp_path,
    )

    text = result.text_path.read_text(encoding="utf-8")
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))

    assert "[00:16.240 - 00:18.290] Speaker 0: And I hide out in the stall." in text
    assert payload["segments"] == [
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
