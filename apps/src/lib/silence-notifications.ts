import type { JobResponse, TranscriptBlock } from "./types";

const MINUTE_MS = 60 * 1000;

export const SILENCE_NOTIFICATION_TIMEOUT_MINUTES = 2;
export const SILENCE_NOTIFICATION_TIMEOUT_MS = SILENCE_NOTIFICATION_TIMEOUT_MINUTES * MINUTE_MS;
export const SILENCE_ALERT_START_FAILED_MESSAGE = "Unable to start silence alerts. Keep this window open and try again.";

export function isTranscriptActivity(event: TranscriptBlock) {
  return (event.type === "final" || event.type === "interim") && Boolean(event.text?.trim());
}

export function isEmptyTranscriptResult(event: TranscriptBlock) {
  return (event.type === "final" || event.type === "interim") && !event.text?.trim();
}

export function notifyOnInactivityEnabled(job: Pick<JobResponse, "metadata_json">) {
  return job.metadata_json.session_preferences?.notify_on_inactivity !== false;
}

export function silenceNotificationTimeoutMsForJob(job: Pick<JobResponse, "silence_timeout_minutes">) {
  return job.silence_timeout_minutes > 0 ? job.silence_timeout_minutes * MINUTE_MS : SILENCE_NOTIFICATION_TIMEOUT_MS;
}

export function silenceNotificationRecordingLabel(job: Pick<JobResponse, "title" | "capture_target">) {
  const title = job.title.trim() || "Untitled capture";
  const targetLabel = job.capture_target.label.trim();
  if (!targetLabel || targetLabel.toLocaleLowerCase() === title.toLocaleLowerCase()) {
    return title;
  }
  return `${title} - ${targetLabel}`;
}
