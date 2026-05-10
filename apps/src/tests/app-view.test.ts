import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(join(testDir, "../app/App.tsx"), "utf8");
const stylesSource = readFileSync(join(testDir, "../styles.css"), "utf8");
const navigationSource = readFileSync(join(testDir, "../components/navigation/Navigation.tsx"), "utf8");
const serviceStripSource = readFileSync(join(testDir, "../components/services/ServiceStrip.tsx"), "utf8");
const captureSource = readFileSync(join(testDir, "../features/capture/StartCapturePanel.tsx"), "utf8");
const captureTargetsSource = readFileSync(join(testDir, "../features/capture/captureTargets.ts"), "utf8");
const desktopSessionsPath = join(testDir, "../features/capture/DesktopSessionsPanel.tsx");
const desktopSessionsSource = existsSync(desktopSessionsPath) ? readFileSync(desktopSessionsPath, "utf8") : "";
const permissionNoticeSource = readFileSync(join(testDir, "../features/capture/ScreenRecordingPermissionNotice.tsx"), "utf8");
const jobDetailSource = readFileSync(join(testDir, "../features/jobs/JobDetail.tsx"), "utf8");
const liveControlsSource = readFileSync(join(testDir, "../features/live/LiveCaptureControls.tsx"), "utf8");
const liveJobSelectorPath = join(testDir, "../features/live/LiveJobSelector.tsx");
const liveJobSelectorSource = existsSync(liveJobSelectorPath) ? readFileSync(liveJobSelectorPath, "utf8") : "";
const liveTranscriptSource = readFileSync(join(testDir, "../features/live/LiveTranscript.tsx"), "utf8");
const liveSummarySource = readFileSync(join(testDir, "../features/live/LiveSummaryPanel.tsx"), "utf8");
const voiceNotesSource = readFileSync(join(testDir, "../features/voice-notes/VoiceNotesPanel.tsx"), "utf8");
const promptModulePath = join(testDir, "../lib/prompts.ts");
const promptModuleSource = existsSync(promptModulePath) ? readFileSync(promptModulePath, "utf8") : "";
const source = [
  appSource,
  navigationSource,
  serviceStripSource,
  captureSource,
  captureTargetsSource,
  desktopSessionsSource,
  permissionNoticeSource,
  jobDetailSource,
  liveControlsSource,
  liveSummarySource,
  voiceNotesSource,
].join("\n");
const servicesSource = readFileSync(join(testDir, "../lib/services.ts"), "utf8");
const notificationSource = readFileSync(join(testDir, "../lib/silence-notifications.ts"), "utf8");
const silenceHookSource = readFileSync(join(testDir, "../lib/use-silence-notification.ts"), "utf8");
const devScriptSource = readFileSync(join(testDir, "../../scripts/dev.sh"), "utf8");
const tauriCargoSource = readFileSync(join(testDir, "../../tauri/Cargo.toml"), "utf8");
const tauriBuildSource = readFileSync(join(testDir, "../../tauri/build.rs"), "utf8");
const macosNotificationPath = join(testDir, "../../tauri/native/macos_notification.m");
const tauriSource = [
  "lib.rs",
  "app_commands.rs",
  "local_services.rs",
  "runtime.rs",
  "silence_notifications.rs",
]
  .map((fileName) => readFileSync(join(testDir, "../../tauri/src", fileName), "utf8"))
  .join("\n");
const tauriCapabilities = JSON.parse(readFileSync(join(testDir, "../../tauri/capabilities/default.json"), "utf8")) as {
  permissions: string[];
};
const liveSummaryPromptFile = join(testDir, "../../../prompts/live_summary_default.txt");
const voiceNoteSummaryPromptFile = join(testDir, "../../../prompts/voice_note_summary_default.txt");
const liveSummaryPrompt = existsSync(liveSummaryPromptFile) ? readFileSync(liveSummaryPromptFile, "utf8").trim() : "";
const voiceNoteSummaryPrompt = existsSync(voiceNoteSummaryPromptFile) ? readFileSync(voiceNoteSummaryPromptFile, "utf8").trim() : "";

function literalPattern(value: string) {
  return new RegExp(value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
}

test("shows the live view only when an active capture exists", () => {
  assert.match(navigationSource, /function Navigation\(\{ view, setView, liveAvailable \}/);
  assert.match(navigationSource, /liveAvailable \? \[\{ view: "live"(?: as const)?, label: "Live"/);
  assert.match(appSource, /const activeJobs = useMemo\(\(\) => jobs\.filter\(\(job\) => ACTIVE_STATES\.has\(job\.state\)\), \[jobs\]\);/);
  assert.match(appSource, /const visibleView = view === "live" && activeJobs\.length === 0 \? "capture" : view/);
  assert.match(appSource, /<Navigation setView=\{setView\} view=\{visibleView\} liveAvailable=\{activeJobs\.length > 0\} \/>/);
  assert.match(appSource, /\{visibleView === "live" && liveJobListItem \? \(/);
});

test("live view follows the selected active capture when multiple jobs run", () => {
  assert.match(appSource, /const selectedActiveListJob = selectedJobId \? activeJobs\.find\(\(job\) => job\.id === selectedJobId\) \?\? null : null;/);
  assert.match(appSource, /const selectedActiveJob = selectedJob && selectedJob\.id === selectedJobId && ACTIVE_STATES\.has\(selectedJob\.state\) \? selectedJob : null;/);
  assert.match(appSource, /const liveJobListItem = selectedActiveListJob \?\? activeJobs\[0\] \?\? null;/);
  assert.match(appSource, /const liveJob = selectedActiveJob\?\.id === liveJobListItem\?\.id \? selectedActiveJob : null;/);
  assert.match(appSource, /if \(visibleView !== "live" \|\| !liveJobListItem \|\| selectedJobId === liveJobListItem\.id\) \{/);
  assert.match(appSource, /selectJob\(liveJobListItem\.id\);/);
  assert.match(appSource, /void loadSelectedJob\(liveJobListItem\.id\);/);
  assert.match(appSource, /<LiveTranscript job=\{liveJob\} \/>/);
  assert.match(appSource, /<LiveSummaryPanel job=\{liveJob\} onSaved=\{\(\) => liveJob \? void loadSelectedJob\(liveJob\.id\) : undefined\} \/>/);
});

test("live view lets users switch between active captures from the live tab", () => {
  assert.match(appSource, /const selectedActiveListJob = selectedJobId \? activeJobs\.find\(\(job\) => job\.id === selectedJobId\) \?\? null : null;/);
  assert.match(appSource, /function handleSelectLiveJob\(jobId: string\)/);
  assert.match(appSource, /setSelectedJob\(null\);/);
  assert.match(appSource, /setArtifacts\(\[\]\);/);
  assert.match(appSource, /<LiveJobSelector/);
  assert.match(appSource, /jobs=\{activeJobs\}/);
  assert.match(appSource, /selectedJobId=\{liveJobListItem\.id\}/);
  assert.match(appSource, /onSelect=\{handleSelectLiveJob\}/);
  assert.match(liveJobSelectorSource, /export function LiveJobSelector/);
  assert.match(liveJobSelectorSource, /jobs\.length <= 1/);
  assert.match(liveJobSelectorSource, /Choose live capture/);
  assert.match(liveJobSelectorSource, /<Select/);
  assert.match(liveJobSelectorSource, /value=\{selectedJobId \?\? ""\}/);
  assert.match(liveJobSelectorSource, /onChange=\{\(event\) => onSelect\(event\.target\.value\)\}/);
  assert.match(liveJobSelectorSource, /jobs\.map\(\(job\) =>/);
  assert.match(stylesSource, /\.live-job-switcher/);
});

test("shows in-app delete confirmation instead of relying on a hidden browser dialog", () => {
  assert.doesNotMatch(source, /window\.confirm/);
  assert.match(source, /Delete this job and its files\? This cannot be undone\./);
  assert.match(source, /Confirm below/);
  assert.match(source, /Delete now/);
  assert.match(source, /setConfirmingDeleteJobId\(jobId\)/);
});

test("clears the delete success notice after changing views", () => {
  assert.match(appSource, /const deleteSuccessNotice = "Job deleted\."/);
  assert.match(appSource, /setNotice\(deleteSuccessNotice\)/);
  assert.match(
    appSource,
    /useEffect\(\(\) => \{\s*setNotice\(\(currentNotice\) => \(currentNotice === deleteSuccessNotice \? "" : currentNotice\)\);\s*\}, \[view\]\);/,
  );
});

test("keeps refreshing a job after stop while the controller finishes in the background", () => {
  const refreshStart = appSource.indexOf("async function refreshStoppedJobUntilSettled(jobId: string)");
  const refreshEnd = appSource.indexOf("async function refreshControllerData()", refreshStart);
  const refreshSource = appSource.slice(refreshStart, refreshEnd);

  assert.notEqual(refreshStart, -1);
  assert.notEqual(refreshEnd, -1);
  assert.match(appSource, /const stopRefreshIntervalMs = 1_500;/);
  assert.match(appSource, /const stopRefreshTimeoutMs = 180_000;/);
  assert.match(appSource, /async function refreshStoppedJobUntilSettled\(jobId: string\)/);
  assert.match(appSource, /while \(Date\.now\(\) < deadline\)/);
  assert.match(appSource, /if \(!ACTIVE_STATES\.has\(job\.state\)\)/);
  assert.match(appSource, /await refreshStoppedJobUntilSettled\(jobId\);/);
  assert.ok(
    refreshSource.indexOf("await loadDesktops();") > refreshSource.indexOf("const job = await getJob(jobId);"),
    "desktop workspace status should refresh after each polled stop state",
  );
});

test("created isolated desktops can be opened and destroyed from the capture workspace", () => {
  assert.match(desktopSessionsSource, /function DesktopSessionsPanel/);
  assert.match(desktopSessionsSource, /Create isolated desktop/);
  assert.match(desktopSessionsSource, /openIsolatedDesktop\(desktop\.browser_url\)/);
  assert.match(desktopSessionsSource, /destroyDesktop\(desktop\.id\)/);
  assert.match(servicesSource, /openIsolatedDesktop\(browserUrl: string\)/);
  assert.match(servicesSource, /invoke\("open_isolated_desktop", \{ browserUrl \}\)/);
  assert.doesNotMatch(tauriSource, /const ISOLATED_DESKTOP_URL/);
  assert.match(tauriSource, /fn open_isolated_desktop\(browser_url: String\) -> Result<\(\), String>/);
  assert.match(tauriSource, /browser_url\.starts_with\("http:\/\/127\.0\.0\.1:"\)/);
  assert.match(tauriSource, /\.arg\(browser_url\)/);
});

test("files reveal generated artifacts in Finder", () => {
  assert.match(jobDetailSource, /openArtifactInFinder/);
  assert.match(jobDetailSource, /async function handleOpenArtifact\(artifact: ArtifactFile\)/);
  assert.match(jobDetailSource, /onClick=\{\(\) => void handleOpenArtifact\(artifact\)\}/);
  assert.doesNotMatch(jobDetailSource, /href=\{artifactHref\(artifact\.download_url\)\}/);
  assert.match(servicesSource, /invoke\("open_artifact_in_finder", \{ path \}\)/);
  assert.match(tauriSource, /fn open_artifact_in_finder\(path: String\) -> Result<\(\), String>/);
  assert.match(tauriSource, /\.arg\("-R"\)/);
  assert.match(tauriSource, /\.arg\(&path\)/);
});

test("job badges surface completed jobs with summary warnings", () => {
  assert.match(source, /formatStateLabel/);
  assert.match(source, /stateTone\(job\.state, job\.metadata_json\)/);
  assert.match(source, /formatStateLabel\(job\.state, job\.metadata_json\)/);
});

test("live summary panel can reset the generated result", () => {
  assert.match(promptModuleSource, /live_summary_default\.txt\?raw/);
  assert.match(liveSummarySource, /getDefaultLiveSummaryPrompt/);
  assert.doesNotMatch(liveSummarySource, literalPattern(liveSummaryPrompt));
  assert.match(liveSummarySource, /function resetSummary\(\) \{\s*setPrompt\(getDefaultLiveSummaryPrompt\(\)\);\s*setResult\(null\);\s*setMessage\(""\);\s*\}/);
  assert.match(liveSummarySource, /onClick=\{resetSummary\}/);
  assert.match(liveSummarySource, />\s*Reset\s*</);
});

test("summary prompts are read from root prompt files", () => {
  assert.equal(existsSync(liveSummaryPromptFile), true);
  assert.equal(existsSync(voiceNoteSummaryPromptFile), true);
  assert.match(promptModuleSource, /voice_note_summary_default\.txt\?raw/);
  assert.match(voiceNotesSource, /getDefaultVoiceNoteSummaryPrompt/);
  assert.doesNotMatch(voiceNotesSource, literalPattern(voiceNoteSummaryPrompt));
});

test("newly created captures are selected and loaded before opening the live view", () => {
  const handlerStart = appSource.indexOf("async function handleCaptureCreated(job: JobResponse, microphoneStream: MediaStream | null = null)");
  const handlerEnd = appSource.indexOf("async function handleStopJob", handlerStart);
  const handlerSource = appSource.slice(handlerStart, handlerEnd);

  assert.notEqual(handlerStart, -1);
  assert.match(handlerSource, /selectJob\(job\.id\)/);
  assert.match(handlerSource, /setSelectedJob\(null\)/);
  assert.match(handlerSource, /await loadJobs\(job\.id\)/);
  assert.match(handlerSource, /await loadSelectedJob\(job\.id\)/);
  assert.ok(handlerSource.indexOf('setView("live")') > handlerSource.indexOf("await loadSelectedJob(job.id)"));
});

test("start capture allows parallel desktops but blocks unavailable targets", () => {
  assert.match(captureSource, /activeCaptures\?: JobResponse\[\]/);
  assert.match(appSource, /<StartCapturePanel[\s\S]*?activeCaptures=\{activeJobs\}[\s\S]*?onCreated=\{handleCaptureCreated\}/);
  assert.match(captureSource, /const selectedTargetUnavailable = selectedTarget\?\.available === false;/);
  assert.match(captureSource, /const macCaptureBlocked =\s*backend === "macos_local" && activeCaptures\.some\(\(job\) => job\.capture_backend === "macos_local"\);/);
  assert.doesNotMatch(captureSource, /Stop the current session before starting a new one\./);
  assert.match(captureSource, /disabled=\{busy \|\| selectedTargetUnavailable \|\| macCaptureBlocked \|\| \(backend === "macos_local" && !selectedTarget\) \|\| \(backend === "docker_desktop" && !selectedTarget\)\}/);
  assert.match(captureSource, /\{busy \? "Starting\.\.\." : "Start capture"\}/);
});

test("local capture permission errors show a recovery panel", () => {
  assert.match(captureTargetsSource, /function isScreenRecordingPermissionError\(message: string\)/);
  assert.match(captureTargetsSource, /screen_recording_permission_denied/);
  assert.match(captureTargetsSource, /system_audio_recording_permission_denied/);
  assert.match(permissionNoticeSource, /function ScreenRecordingPermissionNotice/);
  assert.match(permissionNoticeSource, /Capture access is blocked/);
  assert.match(permissionNoticeSource, /Screen & System Audio Recording/);
  assert.match(permissionNoticeSource, /onClick=\{\(\) => void openScreenRecordingSettings\(\)\}/);
  assert.match(permissionNoticeSource, /Open capture settings/);
  assert.match(captureSource, /<ScreenRecordingPermissionNotice \/>/);
});

test("app-managed services wait for spawned ports before reporting startup", () => {
  assert.match(tauriSource, /fn wait_for_port_open\(port: u16, name: &str, timeout: Duration\) -> Result<\(\), String>/);

  const macosReconcileStart = tauriSource.indexOf("fn reconcile_macos_capture_agent");
  const controllerReconcileStart = tauriSource.indexOf("fn reconcile_controller_api");
  const spawnStart = tauriSource.indexOf("fn spawn_app_service");
  const macosReconcile = tauriSource.slice(macosReconcileStart, controllerReconcileStart);
  const controllerReconcile = tauriSource.slice(controllerReconcileStart, spawnStart);

  assert.match(
    macosReconcile,
    /spawn_app_service\([\s\S]*?\)\?;\s*wait_for_port_open\(\s*MACOS_CAPTURE_PORT,\s*"This Mac capture",\s*Duration::from_secs\(10\),?\s*\)/,
  );
  assert.match(
    controllerReconcile,
    /spawn_app_service\([\s\S]*?\)\?;\s*wait_for_port_open\(\s*CONTROLLER_API_PORT,\s*"Controller API",\s*Duration::from_secs\(10\),?\s*\)/,
  );
});

test("dashboard does not render system checks", () => {
  const refreshStart = appSource.indexOf("async function refreshControllerData()");
  const firstEffectStart = appSource.indexOf("useEffect(() => {", refreshStart);
  const refreshSource = appSource.slice(refreshStart, firstEffectStart);
  const bootStart = appSource.indexOf("async function boot()");
  const bootEnd = appSource.indexOf("void boot();", bootStart);
  const bootSource = appSource.slice(bootStart, bootEnd);

  assert.doesNotMatch(appSource, /HealthPanel/);
  assert.doesNotMatch(appSource, /getHealth/);
  assert.doesNotMatch(appSource, /HealthStatusResponse/);
  assert.doesNotMatch(appSource, /refreshHealth/);
  assert.doesNotMatch(source, /System checks/);
  assert.doesNotMatch(refreshSource, /Promise\.all\(\[getJobs\(\), getHealth\(\), getDesktops\(\)\]\)/);
  assert.match(bootSource, /void refreshControllerData\(\);[\s\S]*?await startLocalServices\(\)/);
});

test("app runtime refresh only refreshes local service status", () => {
  assert.doesNotMatch(appSource, /async function refreshRuntimeStatus\(\)/);
  assert.match(appSource, /<ServiceStrip[\s\S]*?onRefresh=\{\(\) => void refreshStatus\(\)\}/);
  assert.match(appSource, /<SettingsPanel[\s\S]*?onRefresh=\{\(\) => void refreshStatus\(\)\}/);
});

test("app-managed services reject stale controller APIs without desktop routes", () => {
  assert.match(tauriSource, /fn controller_api_supports_desktops\(\) -> bool/);
  assert.match(tauriSource, /fn controller_api_supports_processed_microphone\(\) -> bool/);
  assert.match(tauriSource, /local_http_status\(CONTROLLER_API_PORT, "\/api\/desktops", Duration::from_secs\(2\)\)/);
  assert.match(tauriSource, /local_http_get\(CONTROLLER_API_PORT, "\/api\/health", Duration::from_secs\(2\)\)/);
  assert.match(tauriSource, /processed_capture_microphone/);
  assert.match(tauriSource, /DESKTOP_SESSIONS_ROOT=\{\}/);
  assert.match(tauriSource, /DESKTOP_SESSIONS_REGISTRY_PATH=\{\}/);

  const controllerReconcileStart = tauriSource.indexOf("fn reconcile_controller_api");
  const nextFunctionStart = tauriSource.indexOf("\nfn spawn_app_service", controllerReconcileStart);
  const controllerReconcile = tauriSource.slice(controllerReconcileStart, nextFunctionStart);

  assert.match(controllerReconcile, /port_open && !controller_api_supports_desktops\(\)/);
  assert.match(controllerReconcile, /port_open && !controller_api_supports_processed_microphone\(\)/);
  assert.match(controllerReconcile, /stop_child_service\(\s*runtime_root,\s*"controller-api",\s*&mut children\.controller_api,?\s*\)\?/);
  assert.match(controllerReconcile, /does not support isolated desktops/);
  assert.match(controllerReconcile, /does not support processed microphone capture/);
});

test("app-owned macOS capture agent is not restarted just because screen access is blocked", () => {
  const macosReconcileStart = tauriSource.indexOf("fn reconcile_macos_capture_agent");
  const controllerReconcileStart = tauriSource.indexOf("fn reconcile_controller_api");
  const macosReconcile = tauriSource.slice(macosReconcileStart, controllerReconcileStart);

  assert.doesNotMatch(macosReconcile, /child_running\s*&&\s*permission_denied/);
  assert.match(macosReconcile, /if !child_running && port_open && !active_capture/);
});

test("local capture picker groups selectable apps and windows by application", () => {
  assert.match(captureTargetsSource, /function targetGroups\(targets: CaptureTarget\[\]\)/);
  assert.match(captureTargetsSource, /label: "Displays"/);
  assert.match(captureTargetsSource, /target\.kind === "application"/);
  assert.match(captureTargetsSource, /label: "Applications"/);
  assert.match(captureTargetsSource, /target\.kind === "window"/);
  assert.match(captureTargetsSource, /`\$\{appName\} windows`/);
});

test("start session exposes recording and summary options", () => {
  assert.match(captureSource, /Screen record/);
  assert.match(captureSource, /Notify me about silence/);
  assert.match(captureSource, /const \[notifyOnInactivity, setNotifyOnInactivity\] = useState\(true\);/);
  assert.doesNotMatch(captureSource, /requestSilenceNotificationPermission/);
  assert.doesNotMatch(captureSource, /openNotificationSettings/);
  assert.doesNotMatch(captureSource, /Allow notifications/);
  assert.doesNotMatch(captureSource, /sendNativeNotification/);
  assert.doesNotMatch(captureSource, /const TEST_NOTIFICATION_DELAY_MS/);
  assert.doesNotMatch(captureSource, /startSilenceNotificationMonitor/);
  assert.doesNotMatch(captureSource, /async function sendTestNotification\(\)/);
  assert.doesNotMatch(captureSource, /test-alert-\$\{Date\.now\(\)\}/);
  assert.doesNotMatch(captureSource, /Test silence alert/);
  assert.doesNotMatch(captureSource, />\s*Test alert\s*</);
  assert.match(captureSource, /silence_timeout_minutes: SILENCE_NOTIFICATION_TIMEOUT_MINUTES/);
  assert.match(captureSource, /const \[recordMicrophone, setRecordMicrophone\] = useState\(false\);/);
  assert.match(captureSource, /const \[echoCancellation, setEchoCancellation\] = useState\(true\);/);
  assert.match(captureSource, /Record microphone/);
  assert.match(captureSource, /Use your microphone without changing other apps\./);
  assert.match(captureSource, /Reduce speaker echo/);
  assert.match(captureSource, /Keeps session audio playing while cleaning your microphone\./);
  assert.match(captureSource, /requestProcessedMicrophoneStream/);
  assert.match(captureSource, /const shouldRecordMicrophone = canRecordMicrophone \? recordMicrophone : false/);
  assert.match(captureSource, /record_microphone: shouldRecordMicrophone/);
  assert.match(captureSource, /echo_cancellation_enabled: shouldRecordMicrophone \? echoCancellation : false/);
  assert.match(captureSource, /Mute this app for me/);
  assert.match(captureSource, /This mutes the selected app while capture runs\./);
  assert.doesNotMatch(captureSource, /Google Chrome/);
  assert.match(captureSource, /mute_target_audio: canMuteTargetAudio \? muteTargetAudio : false/);
  assert.match(captureSource, /notify_on_inactivity: notifyOnInactivity/);
  assert.match(captureSource, /Generate summary/);
  assert.match(captureSource, /record_screen: screenRecord/);
  assert.match(captureSource, /generate_summary: generateSummary/);
});

test("start session hides checkbox options that are not available", () => {
  assert.doesNotMatch(captureSource, /disabled=\{!canRecordMicrophone\}/);
  assert.doesNotMatch(captureSource, /disabled=\{!canMuteTargetAudio\}/);
  assert.match(captureSource, /\{canRecordMicrophone \? \(\s*<label className="option-row">/);
  assert.match(captureSource, /\{canMuteTargetAudio \? \(\s*<label className="option-row">/);
});

test("live view exposes a runtime app mute toggle for active captures", () => {
  assert.match(appSource, /setTargetAudioMuted/);
  assert.match(appSource, /setRecordMicrophoneEnabled/);
  assert.match(appSource, /setEchoCancellationEnabled/);
  assert.match(appSource, /startCaptureMicrophone/);
  assert.match(appSource, /captureMicrophoneLiveUrl/);
  assert.match(appSource, /const \[mutingJobId, setMutingJobId\] = useState<string \| null>\(null\);/);
  assert.match(appSource, /const \[microphoneJobId, setMicrophoneJobId\] = useState<string \| null>\(null\);/);
  assert.match(appSource, /const \[echoCancellationJobId, setEchoCancellationJobId\] = useState<string \| null>\(null\);/);
  assert.match(appSource, /async function handleSetTargetAudioMuted\(jobId: string, muted: boolean\)/);
  assert.match(appSource, /async function handleSetRecordMicrophone\(jobId: string, enabled: boolean\)/);
  assert.match(appSource, /async function handleSetEchoCancellation\(jobId: string, enabled: boolean\)/);
  assert.match(appSource, /<LiveCaptureControls/);
  assert.match(liveControlsSource, /VolumeX/);
  assert.match(liveControlsSource, /Volume2/);
  assert.match(liveControlsSource, /MicOff/);
  assert.match(liveControlsSource, /Mic/);
  assert.match(liveControlsSource, /Mute app/);
  assert.match(liveControlsSource, /Unmute app/);
  assert.match(liveControlsSource, /Record microphone/);
  assert.match(liveControlsSource, /Stop microphone/);
  assert.match(liveControlsSource, /canToggleTargetAudioMute/);
  assert.match(liveControlsSource, /canToggleMicrophoneRecording/);
  assert.match(liveControlsSource, /targetAudioMuted/);
  assert.match(liveControlsSource, /recordMicrophoneEnabled/);
  assert.match(liveControlsSource, /Reduce speaker echo/);
  assert.match(liveControlsSource, /Keeps session audio playing while cleaning your microphone\./);
  assert.match(liveControlsSource, /echoCancellationEnabled/);
  assert.match(liveControlsSource, /canToggleEchoCancellation/);
});

test("live transcript splits system audio and microphone into separate sections", () => {
  assert.match(liveTranscriptSource, /System audio/);
  assert.match(liveTranscriptSource, /Self/);
  assert.doesNotMatch(liveTranscriptSource, /label: "Microphone"/);
  assert.match(liveTranscriptSource, /source === "microphone"/);
  assert.match(liveTranscriptSource, /source === "system"/);
});

test("voice notes are available as a separate recording workspace", () => {
  assert.match(navigationSource, /label: "Voice notes"/);
  assert.match(navigationSource, /view: "voice-notes"/);
  assert.match(appSource, /visibleView === "voice-notes"/);
  assert.match(appSource, /<VoiceNotesPanel \/>/);
  assert.match(voiceNotesSource, /requestProcessedMicrophoneStream\(\)/);
  assert.match(voiceNotesSource, /new MediaRecorder\(stream\)/);
  assert.match(voiceNotesSource, /new WebSocket\(voiceNoteLiveUrl\(\)\)/);
  assert.match(voiceNotesSource, /encodeLinear16/);
  assert.match(voiceNotesSource, /isAudibleMicrophoneInput/);
  assert.match(voiceNotesSource, /isVoiceNoteTranscriptTextEvent/);
  assert.match(voiceNotesSource, /No microphone sound yet/);
  assert.match(voiceNotesSource, /Waiting for words/);
  assert.match(voiceNotesSource, /Listening for words/);
  assert.match(voiceNotesSource, /await audioContext\.resume\(\)/);
  assert.match(voiceNotesSource, /processor\.connect\(audioContext\.destination\)/);
  assert.match(voiceNotesSource, /event\.outputBuffer\.getChannelData\(0\)\.fill\(0\)/);
  assert.match(voiceNotesSource, /createVoiceNote/);
  assert.match(voiceNotesSource, /saveVoiceNote/);
  assert.match(voiceNotesSource, /getVoiceNotes/);
  assert.match(voiceNotesSource, /importVoiceNotes/);
  assert.match(voiceNotesSource, /generateVoiceNoteSummary/);
  assert.match(voiceNotesSource, /Listening now/);
  assert.match(voiceNotesSource, /Saved to notes/);
  assert.match(voiceNotesSource, /Voice summary/);
  assert.match(voiceNotesSource, /summarizeVoiceNote/);
  assert.match(voiceNotesSource, /requestMicrophoneAccess/);
  assert.match(voiceNotesSource, /openMicrophoneSettings/);
  assert.match(voiceNotesSource, /Open microphone settings/);
  assert.match(servicesSource, /invoke<boolean>\("request_microphone_access"\)/);
  assert.match(servicesSource, /invoke\("open_microphone_settings"\)/);
  assert.match(tauriSource, /fn request_microphone_access\(\)/);
  assert.match(tauriSource, /requestAccessForMediaType/);
  assert.match(tauriSource, /Privacy_Microphone/);
  assert.doesNotMatch(voiceNotesSource, /SpeechRecognition|webkitSpeechRecognition/);
});

test("saved voice notes collapse to cards after their one-time save", () => {
  assert.match(voiceNotesSource, /const \[expandedNoteId, setExpandedNoteId\] = useState<string \| null>\(null\);/);
  assert.match(voiceNotesSource, /const \[unsavedNoteIds, setUnsavedNoteIds\] = useState<Set<string>>/);
  assert.match(voiceNotesSource, /async function saveNote\(noteId: string\)/);
  assert.match(voiceNotesSource, /setExpandedNoteId\(\(current\) => \(current === noteId \? null : current\)\)/);
  assert.match(voiceNotesSource, /setExpandedNoteId\(null\);/);
  assert.match(voiceNotesSource, /unsavedNoteIds\.has\(note\.id\)/);
  assert.match(voiceNotesSource, /voice-note-card/);
  assert.match(voiceNotesSource, /voice-note-details/);
  assert.match(voiceNotesSource, /Save/);
});

test("active captures start a native silence monitor outside the live view", () => {
  assert.match(appSource, /@tauri-apps\/api\/event/);
  assert.match(appSource, /type SilenceAppAlertPayload = \{/);
  assert.match(appSource, /const \[silenceAlert, setSilenceAlert\] = useState<SilenceAppAlertPayload \| null>\(null\);/);
  assert.match(appSource, /listen<SilenceAppAlertPayload>\("silence-alert",/);
  assert.match(appSource, /setSilenceAlert\(event\.payload\)/);
  assert.match(appSource, /className="silence-alert-region"/);
  assert.match(appSource, /className="silence-alert"/);
  assert.match(appSource, /role="alert"/);
  assert.match(appSource, /Dismiss silence alert/);
  assert.match(stylesSource, /\.silence-alert-region/);
  assert.match(stylesSource, /position: fixed/);
  assert.match(stylesSource, /top: 24px/);
  assert.match(stylesSource, /right: 24px/);
  assert.match(stylesSource, /\.silence-alert/);
  assert.match(appSource, /useSilenceNotification\(activeJobs,/);
  assert.match(appSource, /async function handleCaptureCreated\(job: JobResponse, microphoneStream: MediaStream \| null = null\)/);
  assert.match(notificationSource, /SILENCE_NOTIFICATION_TIMEOUT_MINUTES = 2/);
  assert.match(notificationSource, /SILENCE_NOTIFICATION_TIMEOUT_MS = SILENCE_NOTIFICATION_TIMEOUT_MINUTES \* MINUTE_MS/);
  assert.match(notificationSource, /EMPTY_TRANSCRIPT_NOTIFICATION_THRESHOLD = 3/);
  assert.match(notificationSource, /EMPTY_TRANSCRIPT_IDLE_TICK_MS/);
  assert.match(notificationSource, /isEmptyTranscriptResult/);
  assert.match(notificationSource, /recordEmptyTranscriptResult/);
  assert.match(notificationSource, /recordTranscriptIdleTick/);
  assert.match(notificationSource, /recordEmptyTranscriptResultAndEvaluate/);
  assert.match(notificationSource, /recordTranscriptIdleTickAndEvaluate/);
  assert.match(notificationSource, /silenceNotificationTimeoutMsForJob/);
  assert.doesNotMatch(notificationSource, /checkNativeNotificationPermission/);
  assert.doesNotMatch(notificationSource, /requestNativeNotificationPermission/);
  assert.doesNotMatch(notificationSource, /sendNativeNotification/);
  assert.doesNotMatch(notificationSource, /@tauri-apps\/plugin-notification/);
  assert.doesNotMatch(notificationSource, /sendNotification/);
  assert.doesNotMatch(notificationSource, /requestPermission/);
  assert.doesNotMatch(notificationSource, /isPermissionGranted/);
  assert.doesNotMatch(notificationSource, /silenceNotificationIconUrl/);
  assert.match(notificationSource, /SILENCE_ALERT_START_FAILED_MESSAGE/);
  assert.match(silenceHookSource, /notifyOnInactivityEnabled\(activeJob\)/);
  assert.match(silenceHookSource, /function elapsedMsSince\(timestamp: string \| null\)/);
  assert.match(silenceHookSource, /const activeJobs = Array\.isArray\(jobs\) \? jobs : jobs \? \[jobs\] : \[\];/);
  assert.match(silenceHookSource, /for \(const activeJob of activeJobs\)/);
  assert.match(silenceHookSource, /const timeoutMs = silenceNotificationTimeoutMsForJob\(activeJob\)/);
  assert.match(
    silenceHookSource,
    /startSilenceNotificationMonitor\(\{\s*jobId: activeJob\.id,\s*title: silenceNotificationRecordingLabel\(activeJob\),\s*timeoutMs,\s*elapsedMs: elapsedMsSince\(activeJob\.started_at \?\? activeJob\.created_at\),/,
  );
  assert.match(silenceHookSource, /silenceNotificationRecordingLabel/);
  assert.match(silenceHookSource, /isEmptyTranscriptResult\(event\)/);
  assert.match(silenceHookSource, /recordSilenceNotificationActivity\(activeJob\.id\)/);
  assert.match(silenceHookSource, /stopSilenceNotificationMonitor\(activeJob\.id\)/);
  assert.doesNotMatch(silenceHookSource, /window\.setInterval/);
  assert.doesNotMatch(silenceHookSource, /window\.setTimeout/);
  assert.match(silenceHookSource, /SILENCE_ALERT_START_FAILED_MESSAGE/);
  assert.match(silenceHookSource, /new EventSource\(apiUrl\(`\/api\/jobs\/\$\{activeJob\.id\}\/live\/stream`\)/);
  assert.match(silenceHookSource, /isTranscriptActivity\(event\)/);
  assert.match(servicesSource, /startSilenceNotificationMonitor/);
  assert.match(servicesSource, /elapsedMs\?: number/);
  assert.match(servicesSource, /alert\?: SilenceAlertPayload/);
  assert.match(servicesSource, /oneShot\?: boolean/);
  assert.match(servicesSource, /invoke\("start_silence_notification_monitor", \{ payload \}\)/);
  assert.match(servicesSource, /recordSilenceNotificationActivity/);
  assert.match(servicesSource, /invoke\("record_silence_notification_activity", \{ jobId \}\)/);
  assert.match(servicesSource, /stopSilenceNotificationMonitor/);
  assert.match(servicesSource, /invoke\("stop_silence_notification_monitor", \{ jobId \}\)/);
  assert.doesNotMatch(tauriSource, /thirdeye_send_notification/);
  assert.doesNotMatch(tauriSource, /notify_rust::Notification::new\(\)/);
  assert.doesNotMatch(tauriSource, /fn send_native_notification/);
  assert.doesNotMatch(tauriSource, /show_native_notification/);
  assert.doesNotMatch(tauriSource, /open_notification_settings/);
  assert.doesNotMatch(tauriSource, /NativeNotificationPayload/);
  assert.match(tauriSource, /struct SilenceAlertPayload/);
  assert.match(tauriSource, /struct SilenceNotificationMonitor/);
  assert.match(tauriSource, /HashMap<String, SilenceNotificationJob>/);
  assert.match(tauriSource, /alert: Option<SilenceAlertPayload>/);
  assert.match(tauriSource, /one_shot: bool/);
  assert.match(tauriSource, /silence-notifications\.log/);
  assert.match(tauriSource, /fn log_silence_notification_event/);
  assert.match(tauriSource, /silence-monitor start/);
  assert.match(tauriSource, /silence-monitor waiting/);
  assert.match(tauriSource, /silence-monitor notify/);
  assert.match(tauriSource, /fn emit_silence_app_alert/);
  assert.match(tauriSource, /"silence-alert"/);
  assert.doesNotMatch(tauriSource, /UserAttentionType::Critical/);
  assert.match(tauriSource, /window\.show\(\)/);
  assert.match(tauriSource, /window\.unminimize\(\)/);
  assert.match(tauriSource, /window\.maximize\(\)/);
  assert.match(tauriSource, /window\.set_focus\(\)/);
  assert.match(tauriSource, /log_window_attention_result\("maximize", job_id, generation, window\.maximize\(\)\)/);
  assert.match(tauriSource, /log_window_attention_result\("focus", job_id, generation, window\.set_focus\(\)\)/);
  assert.doesNotMatch(tauriSource, /request_user_attention/);
  assert.match(tauriSource, /silence-monitor app-alert emitted/);
  assert.match(tauriSource, /silence-monitor window \{action\} requested/);
  assert.doesNotMatch(tauriSource, /silence-monitor dock attention/);
  assert.match(tauriSource, /fn start_silence_notification_monitor\(/);
  assert.match(tauriSource, /fn record_silence_notification_activity\(/);
  assert.match(tauriSource, /fn stop_silence_notification_monitor\(/);
  assert.match(tauriSource, /run_silence_notification_monitor/);
  assert.doesNotMatch(tauriSource, /app\.notification\(\)\s*\.builder\(\)\s*\.title\(payload\.title\)\s*\.body\(payload\.body\)\s*\.show\(\)/);
  assert.doesNotMatch(tauriSource, /tauri_plugin_notification::init\(\)/);
  assert.doesNotMatch(tauriSource, /send_native_notification/);
  assert.match(tauriSource, /start_silence_notification_monitor/);
  assert.match(tauriSource, /record_silence_notification_activity/);
  assert.match(tauriSource, /stop_silence_notification_monitor/);
  assert.ok(!tauriCapabilities.permissions.includes("notification:default"));
});

test("macOS dev launcher starts the Vite dev server before opening Tauri", () => {
  assert.match(devScriptSource, /VITE_PID/);
  assert.match(devScriptSource, /trap cleanup EXIT INT TERM/);
  assert.match(devScriptSource, /npm run ui:dev &/);
  assert.ok(devScriptSource.indexOf("npm run ui:dev &") < devScriptSource.indexOf("DEP_TAURI_DEV=true cargo build"));
  assert.match(devScriptSource, /wait_for_vite/);
});

test("native Notification Center plumbing is absent from silence alerts", () => {
  assert.doesNotMatch(tauriCargoSource, /tauri-plugin-notification/);
  assert.doesNotMatch(tauriCargoSource, /^cc = /m);
  assert.doesNotMatch(tauriBuildSource, /native\/macos_notification\.m/);
  assert.doesNotMatch(tauriBuildSource, /cc::Build/);
  assert.doesNotMatch(tauriBuildSource, /framework=AppKit|framework=CoreServices|framework=Foundation/);
  assert.equal(existsSync(macosNotificationPath), false);
});
