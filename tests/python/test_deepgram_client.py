from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from transcripts.deepgram_client import normalize_deepgram_message
from core.settings import Settings


def test_websocket_url_includes_vad_events_when_enabled(tmp_path) -> None:
    settings = Settings(
        controller_username="operator",
        controller_password="secret-pass",
        session_secret="session-secret",
        controller_db_path=tmp_path / "controller.db",
        artifacts_root=tmp_path / "artifacts",
        recordings_root=tmp_path / "recordings",
        controller_events_root=tmp_path / "events",
        deepgram_vad_events=True,
    )

    from transcripts.deepgram_client import DeepgramClient

    url = DeepgramClient(settings).websocket_url(
        model="nova-3",
        language="en",
        diarize=True,
        smart_format=True,
        interim_results=True,
        vad_events=True,
    )

    query = parse_qs(urlparse(url).query)
    assert query["vad_events"] == ["true"]


def test_results_event_becomes_interim_message() -> None:
    raw = {
        "type": "Results",
        "is_final": False,
        "speech_final": False,
        "start": 0.0,
        "duration": 1.2,
        "channel": {
            "alternatives": [
                {
                    "transcript": "hello world",
                    "words": [
                        {"speaker": 1, "start": 0.0, "end": 0.5},
                        {"speaker": 1, "start": 0.5, "end": 1.0},
                    ],
                }
            ]
        },
    }

    normalized = normalize_deepgram_message(raw)

    assert normalized["type"] == "interim"
    assert normalized["text"] == "hello world"
    assert normalized["speaker"] == 1
    assert normalized["start"] == 0.0
    assert normalized["end"] == 1.2
    assert normalized["speech_final"] is False


def test_results_event_becomes_final_message() -> None:
    raw = {
        "type": "Results",
        "is_final": True,
        "speech_final": True,
        "start": 3.0,
        "duration": 2.0,
        "channel": {
            "alternatives": [
                {
                    "transcript": "final words",
                    "words": [{"speaker": 2, "start": 3.0, "end": 5.0}],
                }
            ]
        },
    }

    normalized = normalize_deepgram_message(raw)

    assert normalized["type"] == "final"
    assert normalized["speaker"] == 2
    assert normalized["end"] == 5.0
    assert normalized["speech_final"] is True


def test_metadata_event_keeps_request_context() -> None:
    raw = {"type": "Metadata", "request_id": "req-123", "model_info": {"name": "nova-3"}}

    normalized = normalize_deepgram_message(raw)

    assert normalized == {
        "type": "metadata",
        "request_id": "req-123",
        "model": "nova-3",
    }


def test_speech_events_map_to_live_event_types() -> None:
    assert normalize_deepgram_message({"type": "SpeechStarted", "timestamp": 4.2}) == {
        "type": "speech_started",
        "timestamp": 4.2,
    }
    assert normalize_deepgram_message({"type": "UtteranceEnd", "last_word_end": 9.1}) == {
        "type": "utterance_end",
        "timestamp": 9.1,
    }
