import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

test("voice notes page renders Ask AI controls without the old standalone summary card", () => {
  const source = readFileSync(resolve(import.meta.dirname, "../features/voice-notes/VoiceNotesPanel.tsx"), "utf-8");

  assert.equal(source.includes("Ask AI"), true);
  assert.equal(source.includes("Generate Summary"), true);
  assert.equal(source.includes("Save Result"), true);
  assert.equal(source.includes("Reset"), true);
  assert.equal(source.includes("Voice summary"), false);
  assert.equal(source.includes("voice-summary-card"), false);
});

test("recording stop attaches saved live summaries or falls back to automatic summary", () => {
  const source = readFileSync(resolve(import.meta.dirname, "../features/voice-notes/VoiceNotesPanel.tsx"), "utf-8");

  assert.equal(source.includes("pendingSavedLiveSummaryRef.current"), true);
  assert.equal(source.includes("const noteToSave = savedLiveSummary ? { ...note, summary: savedLiveSummary } : note"), true);
  assert.equal(source.includes("void summarizeVoiceNote(savedNote, { persist: true })"), true);
});

test("saved note transcripts render read-only", () => {
  const source = readFileSync(resolve(import.meta.dirname, "../features/voice-notes/VoiceNotesPanel.tsx"), "utf-8");

  assert.equal(source.includes("updateNote(note.id, { transcript"), false);
  assert.equal(source.includes("className=\"voice-note-transcript\""), true);
});

test("saved note edits stay local until Save", () => {
  const source = readFileSync(resolve(import.meta.dirname, "../features/voice-notes/VoiceNotesPanel.tsx"), "utf-8");

  assert.equal(source.includes("beginEditNote(note)"), true);
  assert.equal(source.includes("updateNoteDraft({ title: event.target.value })"), true);
  assert.equal(source.includes("Summary ready. Click Save to keep it."), true);
  assert.equal(source.includes("await updateVoiceNote(noteId, {"), true);
});

test("Ask AI manual save persists live and saved-note results separately", () => {
  const source = readFileSync(resolve(import.meta.dirname, "../features/voice-notes/VoiceNotesPanel.tsx"), "utf-8");

  assert.equal(source.includes("setPendingSavedLiveSummary(askResult)"), true);
  assert.equal(source.includes("Saved for this recording."), true);
  assert.equal(source.includes("await updateVoiceNote(noteId, { summary: askResult })"), true);
});
