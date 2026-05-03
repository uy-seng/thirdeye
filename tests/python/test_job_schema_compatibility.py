from __future__ import annotations

import sqlite3

from api.runtime import create_runtime
from jobs.models import JobCreate


def test_startup_migrations_record_schema_version(settings) -> None:
    runtime = create_runtime(settings)

    job = runtime.jobs.create_job(JobCreate(title="Migrated schema capture"))

    assert job.title == "Migrated schema capture"
    with sqlite3.connect(settings.controller_db_path) as connection:
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    assert "0001_rebuild_jobs_schema" in versions
    assert "0002_add_operations_and_artifact_manifest" in versions
    assert "0003_add_voice_notes" in versions


def test_job_creation_migrates_obsolete_job_columns(settings) -> None:
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
                legacy_contact TEXT NOT NULL,
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
    assert not hasattr(job, "legacy_contact")
    with sqlite3.connect(settings.controller_db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
    assert "legacy_contact" not in columns


def test_job_creation_uses_canonical_job_schema(settings) -> None:
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

    assert job.title == "Missing column capture"
    assert not hasattr(job, "legacy_contact")
    with sqlite3.connect(settings.controller_db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "legacy_contact" not in columns
    assert {"operations", "artifact_manifest", "voice_notes"}.issubset(tables)
