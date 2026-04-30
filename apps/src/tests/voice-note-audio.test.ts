import assert from "node:assert/strict";
import test from "node:test";

import { encodeLinear16, mergeTranscriptEvent } from "../lib/voice-note-audio";

test("encodes microphone float samples as little-endian linear16 pcm", () => {
  const pcm = new Int16Array(encodeLinear16(new Float32Array([-1, -0.5, 0, 0.5, 1]), 16_000, 16_000));

  assert.deepEqual(Array.from(pcm), [-32768, -16384, 0, 16383, 32767]);
});

test("downsamples microphone audio before encoding for live transcription", () => {
  const pcm = new Int16Array(encodeLinear16(new Float32Array([0, 0.25, 0.5, 0.75]), 32_000, 16_000));

  assert.deepEqual(Array.from(pcm), [4095, 20479]);
});

test("merges final and interim live transcription events into note text", () => {
  let state = mergeTranscriptEvent({ transcript: "First sentence", draft: "" }, { type: "interim", text: "draft words" });
  state = mergeTranscriptEvent(state, { type: "final", text: "Finished words" });

  assert.deepEqual(state, {
    transcript: "First sentence Finished words",
    draft: "",
  });
});
