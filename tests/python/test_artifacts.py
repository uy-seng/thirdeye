from __future__ import annotations

from pathlib import Path

import pytest

from jobs.artifacts import ArtifactManager


def test_copy_recording_raises_when_stage_recording_is_missing(settings) -> None:
    artifacts = ArtifactManager(settings)

    with pytest.raises(FileNotFoundError, match="recording stage file is missing"):
        artifacts.copy_recording("job-123")

    assert not (Path(settings.artifacts_root) / "jobs" / "job-123" / "recording.mp4").exists()
