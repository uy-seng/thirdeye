import type { CaptureTarget } from "../../lib/types";

export type CaptureTargetGroup = { key: string; label: string; targets: CaptureTarget[] };

export function targetLabel(target: CaptureTarget) {
  return target.label;
}

export function targetGroups(targets: CaptureTarget[]) {
  const groups: CaptureTargetGroup[] = [];
  const displays = targets.filter((target) => target.kind === "display");
  if (displays.length > 0) {
    groups.push({ key: "display", label: "Displays", targets: displays });
  }

  const applications = targets.filter((target) => target.kind === "application");
  if (applications.length > 0) {
    groups.push({
      key: "application",
      label: "Applications",
      targets: [...applications].sort((first, second) => first.label.localeCompare(second.label)),
    });
  }

  const windowsByApp = new Map<string, CaptureTarget[]>();
  for (const target of targets.filter((target) => target.kind === "window")) {
    const appName = target.app_name?.trim() || "Other";
    windowsByApp.set(appName, [...(windowsByApp.get(appName) ?? []), target]);
  }

  for (const appName of [...windowsByApp.keys()].sort((first, second) => first.localeCompare(second))) {
    groups.push({
      key: `window:${appName}`,
      label: `${appName} windows`,
      targets: [...(windowsByApp.get(appName) ?? [])].sort((first, second) => first.label.localeCompare(second.label)),
    });
  }

  return groups;
}

export function isScreenRecordingPermissionError(message: string) {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("screen_recording_permission_denied") ||
    normalized.includes("system_audio_recording_permission_denied") ||
    normalized.includes("screen recording permission") ||
    normalized.includes("screen & system audio recording")
  );
}
