from __future__ import annotations

from pathlib import Path

import pytest

from jobs.artifacts import ArtifactManager


def test_copy_recording_raises_when_stage_recording_is_missing(settings) -> None:
    artifacts = ArtifactManager(settings)

    with pytest.raises(FileNotFoundError, match="recording stage file is missing"):
        artifacts.copy_recording("job-123")

    assert not (Path(settings.artifacts_root) / "jobs" / "job-123" / "recording.mp4").exists()


def test_debug_artifacts_are_registered_from_logs_root(settings) -> None:
    artifacts = ArtifactManager(settings)
    paths = artifacts.job_paths("job-debug")
    paths.transcript_json.write_text('{"segments":[]}\n', encoding="utf-8")

    registered = artifacts.register_file("job-debug", paths.transcript_json, content_type="application/json")

    assert registered.name == "transcript.json"
    assert registered.path == str(paths.logs_root / "transcript.json")


def test_job_paths_moves_legacy_debug_files_out_of_artifact_root(settings) -> None:
    artifacts = ArtifactManager(settings)
    job_id = "job-legacy-debug"
    root = artifacts.job_root(job_id)
    root.mkdir(parents=True)
    legacy_names = {
        "controller-events.jsonl",
        "deepgram-events.jsonl",
        "metadata.json",
        "transcript.json",
        "transcript.txt",
    }
    for name in legacy_names:
        (root / name).write_text(f"{name}\n", encoding="utf-8")

    paths = artifacts.job_paths(job_id)

    for name in legacy_names:
        assert not (paths.root / name).exists()
        assert (paths.logs_root / name).read_text(encoding="utf-8") == f"{name}\n"
