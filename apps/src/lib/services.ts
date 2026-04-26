import { invoke } from "@tauri-apps/api/core";

import type { CommandResult, ServiceStatus } from "./types";

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

export function openLogsFolder() {
  return invoke("open_logs_folder");
}

export function openIsolatedDesktop() {
  return invoke("open_isolated_desktop");
}

export function openArtifactInFinder(path: string) {
  return invoke("open_artifact_in_finder", { path });
}
