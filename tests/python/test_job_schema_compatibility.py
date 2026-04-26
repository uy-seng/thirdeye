from __future__ import annotations

import sqlite3

from api.runtime import create_runtime
from jobs.models import JobCreate


def test_job_creation_supports_existing_notify_email_column(settings) -> None:
    settings.controller_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.controller_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE jobs (
                id TEXT NOT NULL PRIMARY KEY,
                title TEXT NOT NULL,
                source_url TEXT,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                stopped_at DATETIME,
                state TEXT NOT NULL,
                max_duration_minutes INTEGER NOT NULL,
                auto_stop_enabled BOOLEAN NOT NULL,
                silence_timeout_minutes INTEGER NOT NULL,
                deepgram_model TEXT NOT NULL,
                deepgram_language TEXT,
                diarize BOOLEAN NOT NULL,
                smart_format BOOLEAN NOT NULL,
                interim_results BOOLEAN NOT NULL,
                notify_email TEXT NOT NULL,
                summary_model TEXT NOT NULL,
                recording_path TEXT,
                audio_path TEXT,
                transcript_text_path TEXT,
                transcript_events_path TEXT,
                summary_path TEXT,
                ffmpeg_pid INTEGER,
                live_audio_pid INTEGER,
                deepgram_request_id TEXT,
                error_message TEXT,
                metadata_json TEXT NOT NULL
            )
            """
        )

    runtime = create_runtime(settings)

    job = runtime.jobs.create_job(JobCreate(title="Legacy schema capture"))

    assert job.title == "Legacy schema capture"


def test_job_creation_adds_missing_notify_email_column(settings) -> None:
    settings.controller_db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.controller_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE jobs (
                id TEXT NOT NULL PRIMARY KEY,
                title TEXT NOT NULL,
                source_url TEXT,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                stopped_at DATETIME,
                state TEXT NOT NULL,
                max_duration_minutes INTEGER NOT NULL,
                auto_stop_enabled BOOLEAN NOT NULL,
                silence_timeout_minutes INTEGER NOT NULL,
                deepgram_model TEXT NOT NULL,
                deepgram_language TEXT,
                diarize BOOLEAN NOT NULL,
                smart_format BOOLEAN NOT NULL,
                interim_results BOOLEAN NOT NULL,
                summary_model TEXT NOT NULL,
                recording_path TEXT,
                audio_path TEXT,
                transcript_text_path TEXT,
                transcript_events_path TEXT,
                summary_path TEXT,
                ffmpeg_pid INTEGER,
                live_audio_pid INTEGER,
                deepgram_request_id TEXT,
                error_message TEXT,
                metadata_json TEXT NOT NULL
            )
            """
        )

    runtime = create_runtime(settings)

    job = runtime.jobs.create_job(JobCreate(title="Missing column capture"))

    assert job.notify_email == ""
    with sqlite3.connect(settings.controller_db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
    assert "notify_email" in columns
