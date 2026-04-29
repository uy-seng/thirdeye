import type { JobResponse, TranscriptBlock } from "./types";

const MINUTE_MS = 60 * 1000;

export const SILENCE_NOTIFICATION_TIMEOUT_MINUTES = 2;
export const SILENCE_NOTIFICATION_TIMEOUT_MS = SILENCE_NOTIFICATION_TIMEOUT_MINUTES * MINUTE_MS;
export const EMPTY_TRANSCRIPT_NOTIFICATION_THRESHOLD = 3;
export const EMPTY_TRANSCRIPT_IDLE_TICK_MS = 1_000;
export const SILENCE_ALERT_START_FAILED_MESSAGE = "Unable to start silence alerts. Keep this window open and try again.";

export type SilenceNotificationState = {
  consecutiveEmptyTranscriptResults: number;
  timerStartedAt: number | null;
};

export function isTranscriptActivity(event: TranscriptBlock) {
  return (event.type === "final" || event.type === "interim") && Boolean(event.text?.trim());
}

export function isEmptyTranscriptResult(event: TranscriptBlock) {
  return (event.type === "final" || event.type === "interim") && !event.text?.trim();
}

export function notifyOnInactivityEnabled(job: Pick<JobResponse, "metadata_json">) {
  return job.metadata_json.session_preferences?.notify_on_inactivity !== false;
}

export function createSilenceNotificationState(): SilenceNotificationState {
  return {
    consecutiveEmptyTranscriptResults: 0,
    timerStartedAt: null,
  };
}

export function silenceNotificationTimeoutMsForJob(job: Pick<JobResponse, "silence_timeout_minutes">) {
  return job.silence_timeout_minutes > 0 ? job.silence_timeout_minutes * MINUTE_MS : SILENCE_NOTIFICATION_TIMEOUT_MS;
}

export function recordEmptyTranscriptResult(
  state: SilenceNotificationState,
  now: number,
  threshold = EMPTY_TRANSCRIPT_NOTIFICATION_THRESHOLD,
): SilenceNotificationState {
  const consecutiveEmptyTranscriptResults = state.consecutiveEmptyTranscriptResults + 1;
  const timerStartedAt =
    state.timerStartedAt ?? (consecutiveEmptyTranscriptResults >= threshold ? now : null);

  return {
    consecutiveEmptyTranscriptResults,
    timerStartedAt,
  };
}

export function recordTranscriptActivity(_state: SilenceNotificationState): SilenceNotificationState {
  return createSilenceNotificationState();
}

export function recordTranscriptIdleTick(state: SilenceNotificationState, now: number): SilenceNotificationState {
  return recordEmptyTranscriptResult(state, now);
}

export function recordEmptyTranscriptResultAndEvaluate(
  state: SilenceNotificationState,
  now: number,
  timeoutMs = SILENCE_NOTIFICATION_TIMEOUT_MS,
) {
  return evaluateSilenceNotification(recordEmptyTranscriptResult(state, now), now, timeoutMs);
}

export function recordTranscriptIdleTickAndEvaluate(
  state: SilenceNotificationState,
  now: number,
  timeoutMs = SILENCE_NOTIFICATION_TIMEOUT_MS,
) {
  return evaluateSilenceNotification(recordTranscriptIdleTick(state, now), now, timeoutMs);
}

export function evaluateSilenceNotification(
  state: SilenceNotificationState,
  now: number,
  timeoutMs = SILENCE_NOTIFICATION_TIMEOUT_MS,
) {
  if (state.timerStartedAt === null || now - state.timerStartedAt < timeoutMs) {
    return { state, shouldNotify: false };
  }

  return {
    state: createSilenceNotificationState(),
    shouldNotify: true,
  };
}
