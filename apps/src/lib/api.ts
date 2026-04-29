import type {
  ArtifactFile,
  ArtifactListResponse,
  ArtifactsOverviewResponse,
  CaptureBackend,
  CaptureTarget,
  CaptureTargetsResponse,
  HealthStatusResponse,
  JobDetailResponse,
  JobResponse,
  SessionResponse,
  TranscriptSummaryGenerateResponse,
} from "./types";

export const API_BASE = "http://127.0.0.1:8788";
const API_ORIGIN = new URL(API_BASE).origin;
const NATIVE_CLIENT_HEADER = "x-thirdeye-client";
const NATIVE_CLIENT_VALUE = "macos";
const API_TOKEN_QUERY_PARAM = "auth_token";

let apiToken: string | null = null;

export function apiUrl(path: string) {
  return new URL(path, API_BASE).toString();
}

export function authenticatedApiUrl(path: string) {
  const url = new URL(path, API_BASE);
  if (apiToken) {
    url.searchParams.set(API_TOKEN_QUERY_PARAM, apiToken);
  }
  return url.toString();
}

async function readPayload(response: Response) {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set(NATIVE_CLIENT_HEADER, NATIVE_CLIENT_VALUE);
  if (apiToken && !headers.has("authorization")) {
    headers.set("authorization", `Bearer ${apiToken}`);
  }
  if (init?.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    credentials: "include",
  });
  const payload = await readPayload(response);
  if (!response.ok) {
    if (typeof payload === "object" && payload && "detail" in payload) {
      throw new Error(String(payload.detail));
    }
    throw new Error(typeof payload === "string" && payload ? payload : "Request failed.");
  }
  return payload as T;
}

export function getSession() {
  return apiJson<SessionResponse>("/api/session");
}

export async function login(username: string, password: string) {
  const session = await apiJson<SessionResponse>("/api/session/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  apiToken = session.api_token ?? null;
  return session;
}

export async function logout() {
  try {
    return await apiJson<SessionResponse>("/api/session/logout", { method: "POST" });
  } finally {
    apiToken = null;
  }
}

export function getJobs() {
  return apiJson<JobResponse[]>("/api/jobs");
}

export function getJob(jobId: string) {
  return apiJson<JobDetailResponse>(`/api/jobs/${jobId}`);
}

export function getHealth() {
  return apiJson<HealthStatusResponse>("/api/settings/health");
}

export function getArtifactsOverview() {
  return apiJson<ArtifactsOverviewResponse>("/api/artifacts");
}

export function getJobArtifacts(jobId: string) {
  return apiJson<ArtifactListResponse>(`/api/jobs/${jobId}/artifacts`);
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

export function getCaptureTargets(backend: CaptureBackend) {
  return apiJson<CaptureTargetsResponse>(`/api/capture/targets?backend=${backend}`);
}

export function startCapture(payload: {
  title: string;
  capture_backend: CaptureBackend;
  capture_target?: CaptureTarget;
  record_screen: boolean;
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

export function deleteJob(jobId: string) {
  return apiJson<JobResponse>(`/api/jobs/${jobId}/delete`, { method: "POST" });
}

export function artifactHref(downloadUrl: string) {
  const url = new URL(downloadUrl, API_BASE);
  if (apiToken && url.origin === API_ORIGIN) {
    url.searchParams.set(API_TOKEN_QUERY_PARAM, apiToken);
  }
  return url.toString();
}
