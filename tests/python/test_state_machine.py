from __future__ import annotations

import pytest

from jobs.state_machine import JobState, JobStateMachine, TransitionError


def test_state_machine_accepts_happy_path() -> None:
    machine = JobStateMachine()

    current = JobState.IDLE
    for target in (
        JobState.PENDING_START,
        JobState.RECORDING,
        JobState.LIVE_STREAM_CONNECTING,
        JobState.LIVE_STREAMING,
        JobState.STOPPING,
        JobState.FINALIZING_DEEPGRAM,
        JobState.COMPILING_TRANSCRIPT,
        JobState.COMPLETED,
    ):
        machine.assert_transition(current, target)
        current = target


def test_state_machine_accepts_live_only_capture_path() -> None:
    machine = JobStateMachine()

    current = JobState.IDLE
    for target in (
        JobState.PENDING_START,
        JobState.LIVE_STREAM_CONNECTING,
        JobState.LIVE_STREAMING,
        JobState.STOPPING,
        JobState.FINALIZING_DEEPGRAM,
        JobState.COMPILING_TRANSCRIPT,
        JobState.COMPLETED,
    ):
        machine.assert_transition(current, target)
        current = target


def test_state_machine_rejects_invalid_transition() -> None:
    machine = JobStateMachine()

    with pytest.raises(TransitionError):
        machine.assert_transition(JobState.IDLE, JobState.LIVE_STREAMING)


def test_state_machine_allows_failure_from_any_state() -> None:
    machine = JobStateMachine()

    for state in JobState:
        machine.assert_transition(state, JobState.FAILED)


def test_state_machine_allows_recovery_loop_for_post_stop_finalization() -> None:
    machine = JobStateMachine()

    machine.assert_transition(JobState.FAILED, JobState.RECOVERING)
    machine.assert_transition(JobState.SUMMARIZING, JobState.RECOVERING)
    machine.assert_transition(JobState.RECOVERING, JobState.SUMMARIZING)
    machine.assert_transition(JobState.RECOVERING, JobState.COMPLETED)
