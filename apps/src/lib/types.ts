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
  browser_url?: string | null;
  available?: boolean | null;
  active_job_id?: string | null;
  active_job_state?: string | null;
};

export type CaptureTargetsResponse = {
  backend: CaptureBackend;
  targets: CaptureTarget[];
};

export type DesktopSession = {
  id: string;
  target_id: string;
  label: string;
  container_id: string | null;
  container_name: string;
  browser_url: string;
  agent_url: string;
  status: "starting" | "ready" | "stopped" | "destroyed" | "error";
  created_at: string;
  active_job_id: string | null;
  active_job_state: string | null;
  error_message: string | null;
};

export type DesktopSessionsResponse = {
  desktops: DesktopSession[];
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

export type VoiceNoteSummaryGenerateResponse = {
  markdown: string;
  provider: string;
};

export type VoiceNoteSummary = {
  markdown: string;
  provider: string;
  generatedAt: string;
};

export type VoiceNote = {
  id: string;
  title: string;
  transcript: string;
  createdAt: string;
  durationMs: number;
  audioDataUrl?: string | null;
  summary?: VoiceNoteSummary | null;
};

export type LiveTranscriptSource = "system" | "microphone";

export type LiveSourceSnapshot = {
  final_blocks: TranscriptBlock[];
  interim: string;
};

export type LiveSnapshot = LiveSourceSnapshot & {
  sources?: Record<LiveTranscriptSource, LiveSourceSnapshot>;
};

export type TranscriptBlock = {
  type: "final" | "interim" | "status" | "warning" | "metadata" | "speech_started" | "utterance_end" | "complete";
  text?: string;
  source?: LiveTranscriptSource;
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
    record_microphone?: boolean;
    echo_cancellation_enabled?: boolean;
    generate_summary?: boolean;
    mute_target_audio?: boolean;
    notify_on_inactivity?: boolean;
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
