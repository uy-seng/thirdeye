import assert from "node:assert/strict";
import test from "node:test";

import {
  SILENCE_NOTIFICATION_TIMEOUT_MS,
  isEmptyTranscriptResult,
  isTranscriptActivity,
  notifyOnInactivityEnabled,
  silenceNotificationRecordingLabel,
  silenceNotificationTimeoutMsForJob,
} from "../lib/silence-notifications";

test("treats only non-empty final and interim transcript events as activity", () => {
  assert.equal(isTranscriptActivity({ type: "final", text: "hello" }), true);
  assert.equal(isTranscriptActivity({ type: "interim", text: "draft words" }), true);
  assert.equal(isTranscriptActivity({ type: "final", text: "   " }), false);
  assert.equal(isTranscriptActivity({ type: "interim" }), false);
  assert.equal(isTranscriptActivity({ type: "status", state: "live_streaming" }), false);
  assert.equal(isTranscriptActivity({ type: "metadata", model: "nova-3" }), false);
  assert.equal(isTranscriptActivity({ type: "speech_started" }), false);
  assert.equal(isTranscriptActivity({ type: "utterance_end" }), false);
  assert.equal(isTranscriptActivity({ type: "warning", message: "No audio yet" }), false);
  assert.equal(isTranscriptActivity({ type: "complete", state: "completed" }), false);
});

test("treats empty final and interim transcript events as empty transcript results", () => {
  assert.equal(isEmptyTranscriptResult({ type: "final", text: "" }), true);
  assert.equal(isEmptyTranscriptResult({ type: "interim", text: "   " }), true);
  assert.equal(isEmptyTranscriptResult({ type: "final", text: "hello" }), false);
  assert.equal(isEmptyTranscriptResult({ type: "status", state: "live_streaming" }), false);
});

test("uses the capture silence timeout for inactivity alerts", () => {
  assert.equal(silenceNotificationTimeoutMsForJob({ silence_timeout_minutes: 5 }), 5 * 60 * 1000);
  assert.equal(silenceNotificationTimeoutMsForJob({ silence_timeout_minutes: 0 }), SILENCE_NOTIFICATION_TIMEOUT_MS);
});

test("builds a silence alert label that identifies the recording", () => {
  assert.equal(
    silenceNotificationRecordingLabel({
      title: "Authorized session",
      capture_target: {
        id: "desktop-1",
        kind: "desktop",
        label: "Meeting desktop",
        app_bundle_id: null,
        app_name: null,
        app_pid: null,
        window_id: null,
        display_id: null,
      },
    }),
    "Authorized session - Meeting desktop",
  );
  assert.equal(
    silenceNotificationRecordingLabel({
      title: "Display 1",
      capture_target: {
        id: "display-1",
        kind: "display",
        label: "Display 1",
        app_bundle_id: null,
        app_name: null,
        app_pid: null,
        window_id: null,
        display_id: "1",
      },
    }),
    "Display 1",
  );
});

test("defaults inactivity notifications on unless the job disables them", () => {
  assert.equal(notifyOnInactivityEnabled({ metadata_json: {} }), true);
  assert.equal(notifyOnInactivityEnabled({ metadata_json: { session_preferences: {} } }), true);
  assert.equal(notifyOnInactivityEnabled({ metadata_json: { session_preferences: { notify_on_inactivity: true } } }), true);
  assert.equal(notifyOnInactivityEnabled({ metadata_json: { session_preferences: { notify_on_inactivity: false } } }), false);
});
