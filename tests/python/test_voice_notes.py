from __future__ import annotations

import sqlite3


def test_voice_notes_are_persisted_in_controller_storage(client, settings) -> None:
    response = client.post(
        "/api/voice-notes",
        json={
            "id": "note-1",
            "title": "Launch checklist",
            "transcript": "Call Morgan about the launch checklist.",
            "createdAt": "2026-04-30T16:00:00.000Z",
            "durationMs": 22_000,
            "audioDataUrl": "data:audio/webm;base64,YXVkaW8=",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "note-1"
    assert payload["audioDataUrl"] == "data:audio/webm;base64,YXVkaW8="
    assert (settings.artifacts_root / "voice-notes" / "note-1" / "audio.webm").read_bytes() == b"audio"
    with sqlite3.connect(settings.controller_db_path) as connection:
        rows = list(connection.execute("SELECT id, title, duration_ms FROM voice_notes"))
    assert rows == [("note-1", "Launch checklist", 22_000)]


def test_voice_note_import_is_idempotent_and_keeps_newest_first(client) -> None:
    first = client.post(
        "/api/voice-notes/import",
        json={
            "notes": [
                {
                    "id": "note-older",
                    "title": "Older",
                    "transcript": "Older note",
                    "createdAt": "2026-04-30T16:00:00.000Z",
                    "durationMs": 10_000,
                },
                {
                    "id": "note-newer",
                    "title": "Newer",
                    "transcript": "Newer note",
                    "createdAt": "2026-04-30T16:05:00.000Z",
                    "durationMs": 12_000,
                },
            ]
        },
    )
    second = client.post(
        "/api/voice-notes/import",
        json={
            "notes": [
                {
                    "id": "note-older",
                    "title": "Older updated",
                    "transcript": "Older note",
                    "createdAt": "2026-04-30T16:00:00.000Z",
                    "durationMs": 10_000,
                }
            ]
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    listed = client.get("/api/voice-notes")

    assert listed.status_code == 200
    assert [(note["id"], note["title"]) for note in listed.json()] == [
        ("note-newer", "Newer"),
        ("note-older", "Older updated"),
    ]


def test_voice_note_update_summary_and_delete(client, settings) -> None:
    create = client.post(
        "/api/voice-notes",
        json={
            "id": "note-summary",
            "title": "Needs summary",
            "transcript": "Summarize this note.",
            "createdAt": "2026-04-30T16:00:00.000Z",
            "durationMs": 22_000,
        },
    )
    update = client.patch(
        "/api/voice-notes/note-summary",
        json={
            "summary": {
                "markdown": "# Summary\n\n- Done",
                "provider": "openclaw/test",
                "generatedAt": "2026-04-30T16:01:00.000Z",
            }
        },
    )
    delete = client.delete("/api/voice-notes/note-summary")

    assert create.status_code == 200
    assert update.status_code == 200
    assert update.json()["summary"]["markdown"] == "# Summary\n\n- Done"
    assert delete.status_code == 200
    assert client.get("/api/voice-notes").json() == []
    with sqlite3.connect(settings.controller_db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM voice_notes").fetchone()[0]
    assert count == 0
