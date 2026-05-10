import type {
  ArtifactFile,
  ArtifactsOverviewResponse,
  CaptureBackend,
  CaptureTarget,
  CaptureTargetsResponse,
  DesktopSession,
  DesktopSessionsResponse,
  JobDetailResponse,
  JobResponse,
  TranscriptSummaryGenerateResponse,
  VoiceNoteSummaryGenerateResponse,
  VoiceNote,
} from "./types";

export const API_BASE = "http://127.0.0.1:8788";
const API_WS_BASE = API_BASE.replace(/^http/, "ws");

export function apiUrl(path: string) {
  return new URL(path, API_BASE).toString();
}

export function voiceNoteLiveUrl() {
  return new URL("/ws/voice-notes/live", API_WS_BASE).toString();
}

export function captureMicrophoneLiveUrl(jobId: string) {
  return new URL(`/ws/jobs/${jobId}/microphone`, API_WS_BASE).toString();
}

async function readPayload(response: Response) {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function validationLocationText(value: unknown) {
  if (!Array.isArray(value)) {
    return "";
  }
  return value
    .filter((item): item is string | number => typeof item === "string" || typeof item === "number")
    .filter((item) => item !== "body" && item !== "query" && item !== "path")
    .join(".");
}

function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (typeof item === "object" && item) {
          const record = item as Record<string, unknown>;
          const message = typeof record.msg === "string" ? record.msg : typeof record.message === "string" ? record.message : "";
          if (!message) {
            return "";
          }
          const location = validationLocationText(record.loc);
          return location ? `${location}: ${message}` : message;
        }
        return "";
      })
      .filter(Boolean);
    return messages.join("; ");
  }
  if (typeof detail === "object" && detail) {
    const record = detail as Record<string, unknown>;
    if (typeof record.msg === "string") {
      return record.msg;
    }
    if (typeof record.message === "string") {
      return record.message;
    }
    return JSON.stringify(detail);
  }
  return "";
}

function localServiceConnectionMessage() {
  return "Could not connect to the local app service. Restart the app and try again.";
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...init,
      headers,
    });
  } catch {
    throw new Error(localServiceConnectionMessage());
  }
  const payload = await readPayload(response);
  if (!response.ok) {
    if (typeof payload === "object" && payload && "detail" in payload) {
      throw new Error(formatApiErrorDetail(payload.detail) || "Request failed.");
    }
    throw new Error(typeof payload === "string" && payload ? payload : "Request failed.");
  }
  return payload as T;
}

export function getJobs() {
  return apiJson<JobResponse[]>("/api/jobs");
}

export function getJob(jobId: string) {
  return apiJson<JobDetailResponse>(`/api/jobs/${jobId}`);
}

export function getArtifactsOverview() {
  return apiJson<ArtifactsOverviewResponse>("/api/artifacts");
}

export function generateTranscriptSummary(jobId: string, prompt: string) {
  return apiJson<TranscriptSummaryGenerateResponse>(`/api/jobs/${jobId}/transcript-summary/generate`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

export function saveTranscriptSummary(jobId: string, requestId: string) {
  return apiJson<ArtifactFile>(`/api/jobs/${jobId}/transcript-summary/save`, {
    method: "POST",
    body: JSON.stringify({ request_id: requestId }),
  });
}

export function generateVoiceNoteSummary(payload: { title: string; transcript: string; prompt: string }) {
  return apiJson<VoiceNoteSummaryGenerateResponse>("/api/voice-notes/summary/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getVoiceNotes() {
  return apiJson<VoiceNote[]>("/api/voice-notes");
}

export function saveVoiceNote(note: VoiceNote) {
  return apiJson<VoiceNote>("/api/voice-notes", {
    method: "POST",
    body: JSON.stringify(note),
  });
}

export function updateVoiceNote(noteId: string, updates: Partial<Pick<VoiceNote, "title" | "transcript" | "durationMs" | "audioDataUrl" | "summary">>) {
  return apiJson<VoiceNote>(`/api/voice-notes/${noteId}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export function importVoiceNotes(notes: VoiceNote[]) {
  return apiJson<VoiceNote[]>("/api/voice-notes/import", {
    method: "POST",
    body: JSON.stringify({ notes }),
  });
}

export function deleteVoiceNote(noteId: string) {
  return apiJson<VoiceNote>(`/api/voice-notes/${noteId}`, { method: "DELETE" });
}

export function getCaptureTargets(backend: CaptureBackend) {
  return apiJson<CaptureTargetsResponse>(`/api/capture/targets?backend=${backend}`);
}

export function getDesktops() {
  return apiJson<DesktopSessionsResponse>("/api/desktops");
}

export function createDesktop(label: string) {
  return apiJson<DesktopSession>("/api/desktops", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export function destroyDesktop(desktopId: string) {
  return apiJson<DesktopSession>(`/api/desktops/${desktopId}/destroy`, { method: "POST" });
}

export function startCapture(payload: {
  title: string;
  capture_backend: CaptureBackend;
  capture_target?: CaptureTarget;
  record_screen: boolean;
  record_microphone: boolean;
  generate_summary: boolean;
  mute_target_audio: boolean;
  notify_on_inactivity: boolean;
  silence_timeout_minutes: number;
}) {
  return apiJson<JobResponse>("/api/jobs/start", {
    method: "POST",
    body: JSON.stringify({
      title: payload.title,
      source_url: null,
      capture_backend: payload.capture_backend,
      capture_target: payload.capture_target,
      record_screen: payload.record_screen,
      record_microphone: payload.record_microphone,
      generate_summary: payload.generate_summary,
      mute_target_audio: payload.mute_target_audio,
      notify_on_inactivity: payload.notify_on_inactivity,
      silence_timeout_minutes: payload.silence_timeout_minutes,
    }),
  });
}

export function stopCapture(jobId: string) {
  return apiJson<JobResponse>(`/api/jobs/${jobId}/stop`, { method: "POST" });
}

export function setTargetAudioMuted(jobId: string, muteTargetAudio: boolean) {
  return apiJson<JobResponse>(`/api/jobs/${jobId}/mute-target-audio`, {
    method: "POST",
    body: JSON.stringify({ mute_target_audio: muteTargetAudio }),
  });
}

export function setRecordMicrophoneEnabled(jobId: string, recordMicrophone: boolean) {
  const payload = {
    record_microphone: recordMicrophone,
  };
  return apiJson<JobResponse>(`/api/jobs/${jobId}/record-microphone`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteJob(jobId: string) {
  return apiJson<JobResponse>(`/api/jobs/${jobId}/delete`, { method: "POST" });
}
