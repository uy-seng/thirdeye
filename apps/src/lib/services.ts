import { invoke } from "@tauri-apps/api/core";

import type { CommandResult, ServiceStatus } from "./types";

export type SilenceAlertPayload = {
  title: string;
  body: string;
};

export type SilenceNotificationMonitorPayload = {
  jobId: string;
  title: string;
  timeoutMs: number;
  elapsedMs?: number;
  alert?: SilenceAlertPayload;
  oneShot?: boolean;
};

export function startLocalServices() {
  return invoke<CommandResult>("start_services");
}

export function stopLocalServices() {
  return invoke<CommandResult>("stop_services");
}

export function getServiceStatus() {
  return invoke<ServiceStatus>("service_status");
}

export function openScreenRecordingSettings() {
  return invoke("open_screen_recording_settings");
}

export function startSilenceNotificationMonitor(payload: SilenceNotificationMonitorPayload) {
  return invoke("start_silence_notification_monitor", { payload });
}

export function recordSilenceNotificationActivity(jobId: string) {
  return invoke("record_silence_notification_activity", { jobId });
}

export function stopSilenceNotificationMonitor(jobId: string) {
  return invoke("stop_silence_notification_monitor", { jobId });
}

export function openLogsFolder() {
  return invoke("open_logs_folder");
}

export function openIsolatedDesktop() {
  return invoke("open_isolated_desktop");
}

export function openArtifactInFinder(path: string) {
  return invoke("open_artifact_in_finder", { path });
}
