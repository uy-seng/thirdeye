import assert from "node:assert/strict";
import test from "node:test";

import { advanceInitialReplayState, buildTranscriptFeed, createInitialReplayState, shouldClearLiveDraft, shouldRenderTranscriptLine } from "../lib/live-transcript";

test("keeps status events out of the transcript feed", () => {
  assert.equal(shouldRenderTranscriptLine({ type: "status", state: "live_streaming" }), false);
  assert.equal(shouldRenderTranscriptLine({ type: "warning", message: "No audio yet" }), false);
  assert.equal(shouldRenderTranscriptLine({ type: "complete", state: "completed" }), false);
  assert.equal(shouldRenderTranscriptLine({ type: "final", text: "Hello" }), true);
  assert.equal(shouldRenderTranscriptLine({ type: "interim", text: "Hello" }), true);
});

test("clears live drafts when the stream pauses or completes", () => {
  assert.equal(shouldClearLiveDraft({ type: "utterance_end" }), true);
  assert.equal(shouldClearLiveDraft({ type: "complete", state: "completed" }), true);
  assert.equal(shouldClearLiveDraft({ type: "metadata", model: "general-nova-3" }), true);
  assert.equal(shouldClearLiveDraft({ type: "interim", text: "Still changing" }), false);
  assert.equal(shouldClearLiveDraft({ type: "status", state: "live_streaming" }), false);
});

test("skips the initial snapshot replay from the live stream", () => {
  const replay = createInitialReplayState({
    final_blocks: [
      { type: "final", text: "Opening line", start: 0, speaker: 0 },
      { type: "final", text: "Latest line", start: 12, speaker: 0 },
    ],
    interim: "Draft line",
  });

  const firstFinal = advanceInitialReplayState(replay, { type: "final", text: "Opening line", start: 0, speaker: 0 });
  const secondFinal = advanceInitialReplayState(firstFinal.replay, { type: "final", text: "Latest line", start: 12, speaker: 0 });
  const draft = advanceInitialReplayState(secondFinal.replay, { type: "interim", text: "Draft line" });
  const freshFinal = advanceInitialReplayState(draft.replay, { type: "final", text: "Brand new line", start: 18, speaker: 1 });

  assert.equal(firstFinal.skip, true);
  assert.equal(secondFinal.skip, true);
  assert.equal(draft.skip, true);
  assert.equal(freshFinal.skip, false);
});

test("builds readable transcript rows with speaker metadata", () => {
  const feed = buildTranscriptFeed("Live draft", [
    { type: "final", text: "Opening line", start: 5, end: 8, speaker: 0 },
    { type: "final", text: "Continued thought", start: 8, end: 12, speaker: 0 },
    { type: "final", text: "Other speaker", start: 14, end: 16, speaker: 1 },
  ]);

  assert.deepEqual(feed, [
    { kind: "final", text: "Opening line Continued thought", speaker: 0, start: 5, current: 12 },
    { kind: "final", text: "Other speaker", speaker: 1, start: 14, current: 16 },
    { kind: "draft", text: "Live draft" },
  ]);
});
