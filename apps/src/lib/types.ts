export type ServiceReport = {
  name: string;
  running: boolean;
  detail: string;
};

export type ServiceStatus = {
  runtime_root: string;
  controller_api_url: string;
  reports: ServiceReport[];
};

export type CommandResult = {
  ok: boolean;
  detail: string;
  runtime_root: string;
};

export type SessionResponse = {
  authenticated: boolean;
  username: string | null;
  api_token?: string;
};

export type CaptureBackend = "docker_desktop" | "macos_local";

export type CaptureTarget = {
  id: string;
  kind: "desktop" | "display" | "application" | "window";
  label: string;
  app_bundle_id: string | null;
  app_name: string | null;
  app_pid: number | null;
  window_id: string | null;
  display_id: string | null;
};

export type CaptureTargetsResponse = {
  backend: CaptureBackend;
  targets: CaptureTarget[];
};

export type HealthCheckResult = {
  ok: boolean;
  status: string;
  details: Record<string, unknown>;
};

export type HealthStatusResponse = {
  desktop: HealthCheckResult;
  deepgram: HealthCheckResult;
  openclaw: HealthCheckResult;
};

export type ArtifactFile = {
  name: string;
  path: string;
  size_bytes: number;
  download_url: string;
};

export type ArtifactListResponse = {
  job_id: string;
  files: ArtifactFile[];
};

export type TranscriptSummarySource = {
  final_block_count: number;
  interim_included: boolean;
};

export type TranscriptSummaryGenerateResponse = {
  request_id: string;
  markdown: string;
  provider: string;
  source: TranscriptSummarySource;
};

export type LiveSnapshot = {
  final_blocks: TranscriptBlock[];
  interim: string;
};

export type TranscriptBlock = {
  type: "final" | "interim" | "status" | "warning" | "metadata" | "speech_started" | "utterance_end" | "complete";
  text?: string;
  speaker?: number | null;
  start?: number;
  end?: number;
  speech_final?: boolean;
  state?: string;
  message?: string;
  model?: string;
};

export type JobMetadataJson = Record<string, unknown> & {
  session_preferences?: {
    record_screen?: boolean;
    generate_summary?: boolean;
    mute_target_audio?: boolean;
  } | null;
  finalization_checkpoint?: string | null;
  summary_status?: string | null;
  summary_error?: string | null;
  summary_completed_at?: string | null;
  summary_rerun_status?: string | null;
  summary_rerun_error?: string | null;
  summary_rerun_completed_at?: string | null;
};

export type CompletedJobWarning = {
  kind: "summary";
  label: string;
  status: string;
  error: string;
};

export type JobResponse = {
  id: string;
  title: string;
  source_url: string | null;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
  state: string;
  max_duration_minutes: number;
  auto_stop_enabled: boolean;
  silence_timeout_minutes: number;
  recording_path: string | null;
  transcript_text_path: string | null;
  transcript_events_path: string | null;
  summary_path: string | null;
  error_message: string | null;
  capture_backend: CaptureBackend;
  capture_target: CaptureTarget;
  metadata_json: JobMetadataJson;
};

export type JobTransitionResponse = {
  from_state: string | null;
  to_state: string;
  occurred_at: string;
  reason: string;
  payload: Record<string, unknown>;
};

export type JobDetailResponse = JobResponse & {
  timeline: JobTransitionResponse[];
  live_snapshot: LiveSnapshot;
};

export type ArtifactsOverviewResponse = {
  jobs: Array<{
    job: JobResponse;
    artifacts: ArtifactListResponse;
  }>;
};
