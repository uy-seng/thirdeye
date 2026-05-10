from __future__ import annotations

import sqlite3

from api.runtime import create_runtime
from jobs.models import JobCreate


def create_legacy_jobs_schema(database_path) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version TEXT NOT NULL PRIMARY KEY,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_migrations (version) VALUES
                ('0001_rebuild_jobs_schema'),
                ('0002_add_operations_and_artifact_manifest'),
                ('0003_add_voice_notes');

            CREATE TABLE jobs (
                id TEXT NOT NULL,
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
                metadata_json TEXT NOT NULL,
                PRIMARY KEY (id)
            );
            """
        )


def test_startup_migration_repairs_legacy_jobs_schema_marked_applied(settings) -> None:
    create_legacy_jobs_schema(settings.controller_db_path)

    runtime = create_runtime(settings)
    job = runtime.jobs.create_job(JobCreate(title="Legacy database capture"))

    columns = [row[1] for row in sqlite3.connect(settings.controller_db_path).execute("PRAGMA table_info(jobs)")]
    assert "max_duration_minutes" not in columns
    assert "auto_stop_enabled" not in columns
    assert job.title == "Legacy database capture"
