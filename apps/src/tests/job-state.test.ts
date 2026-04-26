import assert from "node:assert/strict";
import test from "node:test";

import {
  canDeleteJob,
  canStopCapture,
  canToggleTargetAudioMute,
  completedJobWarnings,
  formatStateLabel,
  stateTone,
  stopCaptureButtonLabel,
  stopCaptureStatusMessage,
  targetAudioMuted,
} from "../lib/job-state";

test("keeps stop capture disabled once stopping has started", () => {
  assert.equal(canStopCapture("recording"), true);
  assert.equal(canStopCapture("recording", true), false);
  assert.equal(canStopCapture("live_streaming"), true);
  assert.equal(canStopCapture("stopping"), false);
  assert.equal(canStopCapture("finalizing_deepgram"), false);
});

test("shows stop progress while capture is stopping", () => {
  assert.equal(stopCaptureButtonLabel("recording"), "Stop capture");
  assert.equal(stopCaptureButtonLabel("recording", true), "Stopping...");
  assert.equal(stopCaptureStatusMessage("recording"), "");
  assert.equal(stopCaptureStatusMessage("recording", true), "Stopping capture and finalizing files.");
  assert.equal(stopCaptureButtonLabel("stopping"), "Stopping...");
  assert.equal(stopCaptureStatusMessage("stopping"), "Stopping capture and finalizing files.");
});

test("allows deleting only inactive jobs", () => {
  assert.equal(canDeleteJob("completed"), true);
  assert.equal(canDeleteJob("failed"), true);
  assert.equal(canDeleteJob("recording"), false);
  assert.equal(canDeleteJob("summarizing"), false);
});

test("surfaces completed jobs with summary warnings", () => {
  const job = {
    state: "completed",
    metadata_json: {
      summary_status: "failed",
      summary_error: "summary unavailable",
    },
  };

  assert.deepEqual(completedJobWarnings(job), [
    {
      error: "summary unavailable",
      kind: "summary",
      label: "Summary needs attention",
      status: "failed",
    },
  ]);
  assert.equal(formatStateLabel("completed", job.metadata_json), "completed with warnings");
  assert.equal(stateTone("completed", job.metadata_json), "warn");
});

test("allows runtime mute toggles only for active local app or window captures", () => {
  const localAppJob = {
    state: "live_streaming",
    capture_backend: "macos_local",
    capture_target: { kind: "application" },
    metadata_json: { session_preferences: { mute_target_audio: true } },
  };
  const localDisplayJob = {
    ...localAppJob,
    capture_target: { kind: "display" },
  };
  const dockerJob = {
    ...localAppJob,
    capture_backend: "docker_desktop",
  };

  assert.equal(targetAudioMuted(localAppJob), true);
  assert.equal(canToggleTargetAudioMute(localAppJob), true);
  assert.equal(canToggleTargetAudioMute({ ...localAppJob, state: "recording" }), true);
  assert.equal(canToggleTargetAudioMute({ ...localAppJob, state: "pending_start" }), false);
  assert.equal(canToggleTargetAudioMute(localDisplayJob), false);
  assert.equal(canToggleTargetAudioMute(dockerJob), false);
});
