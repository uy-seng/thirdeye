from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import websockets

from core.settings import Settings


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, (float, int)):
        return float(value)
    return None


def normalize_deepgram_message(message: dict[str, Any]) -> dict[str, Any]:
    event_type = message.get("type")
    if event_type == "Results":
        alternative = ((message.get("channel") or {}).get("alternatives") or [{}])[0]
        words = alternative.get("words") or []
        speaker = words[0].get("speaker") if words else None
        start = float(message.get("start", 0.0))
        duration = float(message.get("duration", 0.0))
        normalized = {
            "type": "final" if message.get("is_final") else "interim",
            "text": alternative.get("transcript", ""),
            "speaker": speaker,
            "start": start,
            "end": start + duration,
        }
        speech_final = message.get("speech_final")
        if isinstance(speech_final, bool):
            normalized["speech_final"] = speech_final
        return normalized
    if event_type == "Metadata":
        model_info = message.get("model_info") or {}
        normalized = {
            "type": "metadata",
            "request_id": message.get("request_id"),
            "model": model_info.get("name"),
        }
        duration = _float_or_none(message.get("duration"))
        if duration is not None:
            normalized["duration"] = duration
        return normalized
    if event_type == "SpeechStarted":
        return {"type": "speech_started", "timestamp": float(message.get("timestamp", 0.0))}
    if event_type == "UtteranceEnd":
        return {"type": "utterance_end", "timestamp": float(message.get("last_word_end", 0.0))}
    return {"type": "warning", "message": "unknown_event", "raw_type": event_type}


def should_promote_interim(trigger: dict[str, Any]) -> bool:
    if trigger.get("type") == "utterance_end":
        return True
    return trigger.get("type") == "metadata" and _float_or_none(trigger.get("duration")) is not None


def promote_interim_block(interim: dict[str, Any] | None, trigger: dict[str, Any]) -> dict[str, Any] | None:
    if not interim:
        return None
    text = str(interim.get("text") or "").strip()
    if not text:
        return None

    promoted = dict(interim)
    promoted["type"] = "final"
    promoted["text"] = text
    promoted["speech_final"] = True
    promoted["promoted_from_interim"] = True
    promoted["promotion_reason"] = str(trigger.get("type") or "stream_end")

    terminal_time = _float_or_none(trigger.get("duration"))
    if terminal_time is None:
        terminal_time = _float_or_none(trigger.get("timestamp"))
    start = _float_or_none(promoted.get("start"))
    if terminal_time is not None and (start is None or terminal_time >= start):
        promoted["end"] = terminal_time

    return promoted


@dataclass
class DeepgramClient:
    settings: Settings

    def websocket_url(
        self,
        *,
        model: str,
        language: str | None,
        diarize: bool,
        smart_format: bool,
        interim_results: bool,
        vad_events: bool,
        encoding: str = "linear16",
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> str:
        query = urlencode(
            {
                "model": model,
                "interim_results": str(interim_results).lower(),
                "vad_events": str(vad_events).lower(),
                "endpointing": self.settings.deepgram_endpointing_ms,
                "utterance_end_ms": self.settings.deepgram_utterance_end_ms,
                "smart_format": str(smart_format).lower(),
                "diarize": str(diarize).lower(),
                "encoding": encoding,
                "sample_rate": sample_rate,
                "channels": channels,
                **({"language": language} if language else {}),
            }
        )
        return f"wss://api.deepgram.com/v1/listen?{query}"

    async def connect(
        self,
        *,
        model: str,
        language: str | None,
        diarize: bool,
        smart_format: bool,
        interim_results: bool,
        vad_events: bool,
        encoding: str = "linear16",
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        return await websockets.connect(
            self.websocket_url(
                model=model,
                language=language,
                diarize=diarize,
                smart_format=smart_format,
                interim_results=interim_results,
                vad_events=vad_events,
                encoding=encoding,
                sample_rate=sample_rate,
                channels=channels,
            ),
            additional_headers={"Authorization": f"Token {self.settings.deepgram_api_key}"},
        )
