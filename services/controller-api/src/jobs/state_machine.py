from __future__ import annotations

from enum import Enum


class JobState(str, Enum):
    IDLE = "idle"
    PENDING_START = "pending_start"
    RECORDING = "recording"
    LIVE_STREAM_CONNECTING = "live_stream_connecting"
    LIVE_STREAMING = "live_streaming"
    STOPPING = "stopping"
    FINALIZING_DEEPGRAM = "finalizing_deepgram"
    COMPILING_TRANSCRIPT = "compiling_transcript"
    SUMMARIZING = "summarizing"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TransitionError(ValueError):
    pass


ACTIVE_JOB_STATES = {
    JobState.PENDING_START,
    JobState.RECORDING,
    JobState.LIVE_STREAM_CONNECTING,
    JobState.LIVE_STREAMING,
    JobState.STOPPING,
    JobState.FINALIZING_DEEPGRAM,
    JobState.COMPILING_TRANSCRIPT,
    JobState.SUMMARIZING,
    JobState.RECOVERING,
}


RECOVERABLE_POST_STOP_STATES = {
    JobState.COMPILING_TRANSCRIPT,
    JobState.SUMMARIZING,
    JobState.RECOVERING,
}


class JobStateMachine:
    def __init__(self) -> None:
        self._allowed: dict[JobState, set[JobState]] = {
            JobState.IDLE: {JobState.PENDING_START},
            JobState.PENDING_START: {JobState.RECORDING, JobState.LIVE_STREAM_CONNECTING},
            JobState.RECORDING: {JobState.LIVE_STREAM_CONNECTING, JobState.CANCELED},
            JobState.LIVE_STREAM_CONNECTING: {JobState.LIVE_STREAMING, JobState.CANCELED},
            JobState.LIVE_STREAMING: {JobState.STOPPING, JobState.CANCELED},
            JobState.STOPPING: {JobState.FINALIZING_DEEPGRAM},
            JobState.FINALIZING_DEEPGRAM: {JobState.COMPILING_TRANSCRIPT},
            JobState.COMPILING_TRANSCRIPT: {JobState.SUMMARIZING, JobState.COMPLETED},
            JobState.SUMMARIZING: {JobState.RECOVERING, JobState.COMPLETED},
            JobState.RECOVERING: {JobState.SUMMARIZING, JobState.COMPLETED},
            JobState.COMPLETED: {JobState.RECOVERING},
            JobState.FAILED: {JobState.RECOVERING},
            JobState.CANCELED: set(),
        }

    def can_transition(self, current: JobState, target: JobState) -> bool:
        if target == JobState.FAILED:
            return True
        return target in self._allowed[current]

    def assert_transition(self, current: JobState, target: JobState) -> None:
        if not self.can_transition(current, target):
            raise TransitionError(f"invalid transition: {current.value} -> {target.value}")
