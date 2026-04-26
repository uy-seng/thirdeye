import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(join(testDir, "../app/App.tsx"), "utf8");
const navigationSource = readFileSync(join(testDir, "../components/navigation/Navigation.tsx"), "utf8");
const serviceStripSource = readFileSync(join(testDir, "../components/services/ServiceStrip.tsx"), "utf8");
const captureSource = readFileSync(join(testDir, "../features/capture/StartCapturePanel.tsx"), "utf8");
const captureTargetsSource = readFileSync(join(testDir, "../features/capture/captureTargets.ts"), "utf8");
const permissionNoticeSource = readFileSync(join(testDir, "../features/capture/ScreenRecordingPermissionNotice.tsx"), "utf8");
const jobDetailSource = readFileSync(join(testDir, "../features/jobs/JobDetail.tsx"), "utf8");
const liveControlsSource = readFileSync(join(testDir, "../features/live/LiveCaptureControls.tsx"), "utf8");
const liveSummarySource = readFileSync(join(testDir, "../features/live/LiveSummaryPanel.tsx"), "utf8");
const source = [
  appSource,
  navigationSource,
  serviceStripSource,
  captureSource,
  captureTargetsSource,
  permissionNoticeSource,
  jobDetailSource,
  liveControlsSource,
  liveSummarySource,
].join("\n");
const servicesSource = readFileSync(join(testDir, "../lib/services.ts"), "utf8");
const tauriSource = readFileSync(join(testDir, "../../tauri/src/lib.rs"), "utf8");

test("shows the live view only when an active capture exists", () => {
  assert.match(navigationSource, /function Navigation\(\{ view, setView, liveAvailable \}/);
  assert.match(navigationSource, /liveAvailable \? \[\{ view: "live"(?: as const)?, label: "Live"/);
  assert.match(appSource, /const visibleView = view === "live" && !activeJob \? "capture" : view/);
  assert.match(appSource, /<Navigation setView=\{setView\} view=\{visibleView\} liveAvailable=\{Boolean\(activeJob\)\} \/>/);
  assert.match(appSource, /\{visibleView === "live" && activeJob \? \(/);
});

test("live view follows the active capture instead of a stale selected job", () => {
  assert.match(appSource, /const liveJob = selectedJob\?\.id === activeJob\?\.id \? selectedJob : null;/);
  assert.match(appSource, /if \(visibleView !== "live" \|\| !activeJob \|\| selectedJob\?\.id === activeJob\.id\) \{/);
  assert.match(appSource, /selectJob\(activeJob\.id\);/);
  assert.match(appSource, /void loadSelectedJob\(activeJob\.id\);/);
  assert.match(appSource, /<LiveTranscript job=\{liveJob\} \/>/);
  assert.match(appSource, /<LiveSummaryPanel job=\{liveJob\} onSaved=\{\(\) => void loadSelectedJob\(activeJob\.id\)\} \/>/);
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
  assert.match(appSource, /const stopRefreshIntervalMs = 1_500;/);
  assert.match(appSource, /const stopRefreshTimeoutMs = 180_000;/);
  assert.match(appSource, /async function refreshStoppedJobUntilSettled\(jobId: string\)/);
  assert.match(appSource, /while \(Date\.now\(\) < deadline\)/);
  assert.match(appSource, /if \(!ACTIVE_STATES\.has\(job\.state\)\)/);
  assert.match(appSource, /await refreshStoppedJobUntilSettled\(jobId\);/);
});

test("settings can open the isolated desktop in the host browser", () => {
  assert.match(serviceStripSource, /openIsolatedDesktop/);
  assert.match(serviceStripSource, /report\.name === "Isolated desktop"/);
  assert.match(serviceStripSource, /onClick=\{\(\) => void openIsolatedDesktop\(\)\}/);
  assert.match(serviceStripSource, />\s*Open\s*</);
  assert.match(servicesSource, /invoke\("open_isolated_desktop"\)/);
  assert.match(tauriSource, /const ISOLATED_DESKTOP_URL: &str = "http:\/\/127\.0\.0\.1:3000\/";/);
  assert.match(tauriSource, /fn open_isolated_desktop\(\)/);
  assert.match(tauriSource, /arg\(ISOLATED_DESKTOP_URL\)/);
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
  assert.match(liveSummarySource, /const defaultSummaryPrompt = "Summarize decisions, risks, and next steps\.";/);
  assert.match(liveSummarySource, /function resetSummary\(\) \{\s*setPrompt\(defaultSummaryPrompt\);\s*setResult\(null\);\s*setMessage\(""\);\s*\}/);
  assert.match(liveSummarySource, /onClick=\{resetSummary\}/);
  assert.match(liveSummarySource, />\s*Reset\s*</);
});

test("newly created captures are selected and loaded before opening the live view", () => {
  const handlerStart = appSource.indexOf("async function handleCaptureCreated(job: JobResponse)");
  const handlerEnd = appSource.indexOf("async function handleStopJob", handlerStart);
  const handlerSource = appSource.slice(handlerStart, handlerEnd);

  assert.notEqual(handlerStart, -1);
  assert.match(handlerSource, /selectJob\(job\.id\)/);
  assert.match(handlerSource, /setSelectedJob\(null\)/);
  assert.match(handlerSource, /await loadJobs\(job\.id\)/);
  assert.match(handlerSource, /await loadSelectedJob\(job\.id\)/);
  assert.ok(handlerSource.indexOf('setView("live")') > handlerSource.indexOf("await loadSelectedJob(job.id)"));
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

  assert.match(macosReconcile, /spawn_app_service\([\s\S]*?\)\?;\s*wait_for_port_open\(MACOS_CAPTURE_PORT, "This Mac capture", Duration::from_secs\(10\)\)/);
  assert.match(controllerReconcile, /spawn_app_service\([\s\S]*?\)\?;\s*wait_for_port_open\(CONTROLLER_API_PORT, "Controller API", Duration::from_secs\(10\)\)/);
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
  assert.match(captureSource, /Mute this app for me/);
  assert.match(captureSource, /This mutes the selected app while capture runs\./);
  assert.doesNotMatch(captureSource, /Google Chrome/);
  assert.match(captureSource, /mute_target_audio: canMuteTargetAudio \? muteTargetAudio : false/);
  assert.match(captureSource, /Generate summary/);
  assert.match(captureSource, /record_screen: screenRecord/);
  assert.match(captureSource, /generate_summary: generateSummary/);
});

test("live view exposes a runtime app mute toggle for active captures", () => {
  assert.match(appSource, /setTargetAudioMuted/);
  assert.match(appSource, /const \[mutingJobId, setMutingJobId\] = useState<string \| null>\(null\);/);
  assert.match(appSource, /async function handleSetTargetAudioMuted\(jobId: string, muted: boolean\)/);
  assert.match(appSource, /<LiveCaptureControls/);
  assert.match(liveControlsSource, /VolumeX/);
  assert.match(liveControlsSource, /Volume2/);
  assert.match(liveControlsSource, /Mute app/);
  assert.match(liveControlsSource, /Unmute app/);
  assert.match(liveControlsSource, /canToggleTargetAudioMute/);
  assert.match(liveControlsSource, /targetAudioMuted/);
});
