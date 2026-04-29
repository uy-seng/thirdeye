import assert from "node:assert/strict";
import test from "node:test";

import {
  EMPTY_TRANSCRIPT_NOTIFICATION_THRESHOLD,
  EMPTY_TRANSCRIPT_IDLE_TICK_MS,
  SILENCE_NOTIFICATION_TIMEOUT_MS,
  createSilenceNotificationState,
  evaluateSilenceNotification,
  isEmptyTranscriptResult,
  isTranscriptActivity,
  notifyOnInactivityEnabled,
  recordEmptyTranscriptResult,
  recordEmptyTranscriptResultAndEvaluate,
  recordTranscriptIdleTick,
  recordTranscriptIdleTickAndEvaluate,
  recordTranscriptActivity,
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

test("treats empty final and interim transcript events as empty Deepgram results", () => {
  assert.equal(isEmptyTranscriptResult({ type: "final", text: "" }), true);
  assert.equal(isEmptyTranscriptResult({ type: "interim", text: "   " }), true);
  assert.equal(isEmptyTranscriptResult({ type: "final", text: "hello" }), false);
  assert.equal(isEmptyTranscriptResult({ type: "status", state: "live_streaming" }), false);
});

test("starts the silence timer after consecutive empty Deepgram results", () => {
  let state = createSilenceNotificationState();

  state = recordEmptyTranscriptResult(state, 1_000);
  assert.equal(state.consecutiveEmptyTranscriptResults, 1);
  assert.equal(state.timerStartedAt, null);

  state = recordEmptyTranscriptResult(state, 2_000);
  assert.equal(state.consecutiveEmptyTranscriptResults, EMPTY_TRANSCRIPT_NOTIFICATION_THRESHOLD - 1);
  assert.equal(state.timerStartedAt, null);

  state = recordEmptyTranscriptResult(state, 3_000);
  assert.equal(state.consecutiveEmptyTranscriptResults, EMPTY_TRANSCRIPT_NOTIFICATION_THRESHOLD);
  assert.equal(state.timerStartedAt, 3_000);
});

test("starts the silence timer when Deepgram returns no transcript results", () => {
  let state = createSilenceNotificationState();

  state = recordTranscriptIdleTick(state, EMPTY_TRANSCRIPT_IDLE_TICK_MS);
  state = recordTranscriptIdleTick(state, EMPTY_TRANSCRIPT_IDLE_TICK_MS * 2);
  state = recordTranscriptIdleTick(state, EMPTY_TRANSCRIPT_IDLE_TICK_MS * 3);

  assert.equal(state.consecutiveEmptyTranscriptResults, EMPTY_TRANSCRIPT_NOTIFICATION_THRESHOLD);
  assert.equal(state.timerStartedAt, EMPTY_TRANSCRIPT_IDLE_TICK_MS * 3);
});

test("uses the capture silence timeout for inactivity alerts", () => {
  assert.equal(silenceNotificationTimeoutMsForJob({ silence_timeout_minutes: 5 }), 5 * 60 * 1000);
  assert.equal(silenceNotificationTimeoutMsForJob({ silence_timeout_minutes: 0 }), SILENCE_NOTIFICATION_TIMEOUT_MS);
});

test("cancels a running silence timer when non-empty transcription arrives", () => {
  let state = createSilenceNotificationState();

  state = recordEmptyTranscriptResult(state, 1_000);
  state = recordEmptyTranscriptResult(state, 2_000);
  state = recordEmptyTranscriptResult(state, 3_000);

  state = recordTranscriptActivity(state);

  assert.equal(state.consecutiveEmptyTranscriptResults, 0);
  assert.equal(state.timerStartedAt, null);
});

test("resets the silence cycle after a notification so later empty results can notify again", () => {
  let state = createSilenceNotificationState();
  state = recordEmptyTranscriptResult(state, 1_000);
  state = recordEmptyTranscriptResult(state, 2_000);
  state = recordEmptyTranscriptResult(state, 3_000);

  let result = evaluateSilenceNotification(state, 3_000 + SILENCE_NOTIFICATION_TIMEOUT_MS);
  assert.equal(result.shouldNotify, true);
  state = result.state;
  assert.equal(state.consecutiveEmptyTranscriptResults, 0);
  assert.equal(state.timerStartedAt, null);

  state = recordEmptyTranscriptResult(state, 4_000 + SILENCE_NOTIFICATION_TIMEOUT_MS);
  state = recordEmptyTranscriptResult(state, 5_000 + SILENCE_NOTIFICATION_TIMEOUT_MS);
  state = recordEmptyTranscriptResult(state, 6_000 + SILENCE_NOTIFICATION_TIMEOUT_MS);
  result = evaluateSilenceNotification(state, 6_000 + SILENCE_NOTIFICATION_TIMEOUT_MS * 2);

  assert.equal(result.shouldNotify, true);
});

test("empty stream events can trigger inactivity alerts without waiting for a timer callback", () => {
  let state = createSilenceNotificationState();
  state = recordEmptyTranscriptResult(state, 1_000);
  state = recordEmptyTranscriptResult(state, 2_000);
  state = recordEmptyTranscriptResult(state, 3_000);

  const result = recordEmptyTranscriptResultAndEvaluate(
    state,
    3_000 + SILENCE_NOTIFICATION_TIMEOUT_MS,
    SILENCE_NOTIFICATION_TIMEOUT_MS,
  );

  assert.equal(result.shouldNotify, true);
  assert.equal(result.state.timerStartedAt, null);
});

test("idle ticks can trigger inactivity alerts without waiting for a timer callback", () => {
  let state = createSilenceNotificationState();
  state = recordTranscriptIdleTick(state, 1_000);
  state = recordTranscriptIdleTick(state, 2_000);
  state = recordTranscriptIdleTick(state, 3_000);

  const result = recordTranscriptIdleTickAndEvaluate(
    state,
    3_000 + SILENCE_NOTIFICATION_TIMEOUT_MS,
    SILENCE_NOTIFICATION_TIMEOUT_MS,
  );

  assert.equal(result.shouldNotify, true);
  assert.equal(result.state.timerStartedAt, null);
});

test("defaults inactivity notifications on unless the job disables them", () => {
  assert.equal(notifyOnInactivityEnabled({ metadata_json: {} }), true);
  assert.equal(notifyOnInactivityEnabled({ metadata_json: { session_preferences: {} } }), true);
  assert.equal(notifyOnInactivityEnabled({ metadata_json: { session_preferences: { notify_on_inactivity: true } } }), true);
  assert.equal(notifyOnInactivityEnabled({ metadata_json: { session_preferences: { notify_on_inactivity: false } } }), false);
});
