import assert from "node:assert/strict";
import test from "node:test";

import { scrollVoiceNoteTranscriptToLatest } from "../lib/voice-note-live-note";

test("scrolls the voice note live transcript to the latest text", () => {
  const transcriptSurface = {
    scrollHeight: 860,
    scrollTop: 120,
  };

  scrollVoiceNoteTranscriptToLatest(transcriptSurface);

  assert.equal(transcriptSurface.scrollTop, 860);
});

test("ignores missing voice note transcript surfaces", () => {
  assert.doesNotThrow(() => scrollVoiceNoteTranscriptToLatest(null));
});
