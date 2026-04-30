import assert from "node:assert/strict";
import test from "node:test";

import {
  createVoiceNote,
  deleteVoiceNote,
  formatVoiceNoteDuration,
  loadVoiceNotes,
  saveVoiceNotes,
  VOICE_NOTES_STORAGE_KEY,
} from "../lib/voice-notes";

function installStorage() {
  const values = new Map<string, string>();
  globalThis.localStorage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
    clear: () => {
      values.clear();
    },
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    get length() {
      return values.size;
    },
  };
}

test("creates a saved voice note from the finished transcript", () => {
  const note = createVoiceNote({
    id: "note-1",
    createdAt: "2026-04-30T16:00:00.000Z",
    transcript: "Follow up with design on Monday. Capture the customer quote.",
    durationMs: 65_000,
    audioDataUrl: "data:audio/webm;base64,abc123",
  });

  assert.equal(note.title, "Follow up with design on Monday");
  assert.equal(note.transcript, "Follow up with design on Monday. Capture the customer quote.");
  assert.equal(note.durationMs, 65_000);
  assert.equal(note.audioDataUrl, "data:audio/webm;base64,abc123");
});

test("falls back to a friendly title when no words were captured", () => {
  const note = createVoiceNote({
    id: "note-2",
    createdAt: "2026-04-30T16:00:00.000Z",
    transcript: "  ",
    durationMs: 4_000,
  });

  assert.equal(note.title, "Voice note");
  assert.equal(note.transcript, "");
});

test("stores newest voice notes first and deletes by id", () => {
  installStorage();
  const first = createVoiceNote({
    id: "note-1",
    createdAt: "2026-04-30T16:00:00.000Z",
    transcript: "First note",
    durationMs: 10_000,
  });
  const second = createVoiceNote({
    id: "note-2",
    createdAt: "2026-04-30T16:01:00.000Z",
    transcript: "Second note",
    durationMs: 12_000,
  });

  saveVoiceNotes([first]);
  saveVoiceNotes([second, ...loadVoiceNotes()]);

  assert.equal(localStorage.getItem(VOICE_NOTES_STORAGE_KEY)?.includes("Second note"), true);
  assert.deepEqual(loadVoiceNotes().map((note) => note.id), ["note-2", "note-1"]);

  deleteVoiceNote("note-2");

  assert.deepEqual(loadVoiceNotes().map((note) => note.id), ["note-1"]);
});

test("keeps generated summaries with saved voice notes", () => {
  installStorage();
  const note = createVoiceNote({
    id: "note-summary",
    createdAt: "2026-04-30T16:00:00.000Z",
    transcript: "Call Morgan about the launch checklist.",
    durationMs: 22_000,
  });

  saveVoiceNotes([
    {
      ...note,
      summary: {
        markdown: "Morgan owns the launch checklist follow-up.",
        provider: "openclaw/test",
        generatedAt: "2026-04-30T16:01:00.000Z",
      },
    },
  ]);

  assert.equal(loadVoiceNotes()[0]?.summary?.markdown, "Morgan owns the launch checklist follow-up.");
});

test("formats voice note durations for short recordings", () => {
  assert.equal(formatVoiceNoteDuration(4_500), "0:05");
  assert.equal(formatVoiceNoteDuration(65_000), "1:05");
  assert.equal(formatVoiceNoteDuration(3_610_000), "60:10");
});
