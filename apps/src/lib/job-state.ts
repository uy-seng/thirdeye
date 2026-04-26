import type { CompletedJobWarning, JobMetadataJson } from "./types";

export const ACTIVE_STATES = new Set([
  "pending_start",
  "recording",
  "live_stream_connecting",
  "live_streaming",
  "stopping",
  "finalizing_deepgram",
  "compiling_transcript",
  "summarizing",
  "recovering",
]);

const STOPPABLE_STATES = new Set(["recording", "live_streaming"]);
const MUTE_TOGGLE_STATES = new Set(["recording", "live_streaming"]);
const WARNING_STATUSES = new Set(["failed", "warning", "retry_required", "needs_attention"]);

const STOP_PROGRESS_MESSAGES: Record<string, string> = {
  compiling_transcript: "Preparing transcript files.",
  finalizing_deepgram: "Finalizing the transcript.",
  recovering: "Recovering the session.",
  stopping: "Stopping capture and finalizing files.",
  summarizing: "Writing the recap.",
};

export function canStopCapture(state: string, stopPending = false) {
  return !stopPending && STOPPABLE_STATES.has(state);
}

export function canDeleteJob(state: string, deletePending = false) {
  return !deletePending && !ACTIVE_STATES.has(state);
}

export function targetAudioMuted(job: {
  metadata_json?: JobMetadataJson;
}) {
  const preferences = job.metadata_json?.session_preferences;
  return Boolean(preferences && preferences.mute_target_audio === true);
}

export function canToggleTargetAudioMute(job: {
  state: string;
  capture_backend: string;
  capture_target: { kind?: string };
}) {
  return (
    job.capture_backend === "macos_local" &&
    ["application", "window"].includes(job.capture_target.kind ?? "") &&
    MUTE_TOGGLE_STATES.has(job.state)
  );
}

export function readableState(value: string) {
  if (value === "completed") {
    return "completed";
  }
  return value.replaceAll("_", " ");
}

function metadataText(metadata: JobMetadataJson | undefined, ...keys: string[]) {
  for (const key of keys) {
    const value = metadata?.[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function warningFromMetadata(metadata: JobMetadataJson | undefined): CompletedJobWarning | null {
  const status = metadataText(metadata, "summary_status", "summary_rerun_status");
  const error = metadataText(metadata, "summary_error", "summary_rerun_error");
  if (!error && !WARNING_STATUSES.has(status)) {
    return null;
  }

  return {
    error: error || "The recap summary needs another pass.",
    kind: "summary",
    label: "Summary needs attention",
    status: status || "warning",
  };
}

export function completedJobWarnings(job: { state: string; metadata_json: JobMetadataJson }) {
  if (job.state !== "completed") {
    return [] as CompletedJobWarning[];
  }

  return [warningFromMetadata(job.metadata_json)].filter(
    (warning): warning is CompletedJobWarning => Boolean(warning),
  );
}

export function formatStateLabel(state: string, metadata?: JobMetadataJson) {
  if (state === "completed" && completedJobWarnings({ state, metadata_json: metadata ?? {} }).length > 0) {
    return "completed with warnings";
  }
  return readableState(state);
}

export function stateTone(state: string, metadata?: JobMetadataJson): "neutral" | "good" | "warn" | "bad" | "info" {
  if (state === "completed" && completedJobWarnings({ state, metadata_json: metadata ?? {} }).length > 0) return "warn";
  if (state === "completed") return "good";
  if (state === "failed" || state === "canceled") return "bad";
  if (ACTIVE_STATES.has(state)) return "info";
  return "neutral";
}

export function stopCaptureButtonLabel(state: string, stopPending = false) {
  if (stopPending || STOP_PROGRESS_MESSAGES[state]) {
    return "Stopping...";
  }
  return "Stop capture";
}

export function stopCaptureStatusMessage(state: string, stopPending = false) {
  if (stopPending) {
    return STOP_PROGRESS_MESSAGES.stopping;
  }
  return STOP_PROGRESS_MESSAGES[state] ?? "";
}
