export const VOICE_NOTES_STORAGE_KEY = "thirdeye.voice-notes";

import type { VoiceNote, VoiceNoteSummary, VoiceNoteSummaryGenerateResponse } from "./types";

export type { VoiceNote, VoiceNoteSummary };

export type VoiceNoteInput = {
  id: string;
  createdAt: string;
  transcript: string;
  durationMs: number;
  audioDataUrl?: string;
};

function normalizeTranscript(transcript: string) {
  return transcript.replace(/\s+/g, " ").trim();
}

function titleFromTranscript(transcript: string) {
  const normalized = normalizeTranscript(transcript);
  if (!normalized) {
    return "Voice note";
  }

  return normalized
    .split(" ")
    .slice(0, 6)
    .join(" ")
    .replace(/[.,!?;:]+$/, "");
}

function isVoiceNote(value: unknown): value is VoiceNote {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<VoiceNote>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.title === "string" &&
    typeof candidate.transcript === "string" &&
    typeof candidate.createdAt === "string" &&
    typeof candidate.durationMs === "number" &&
    (candidate.audioDataUrl === undefined || typeof candidate.audioDataUrl === "string") &&
    (candidate.summary === undefined || isVoiceNoteSummary(candidate.summary))
  );
}

function isVoiceNoteSummary(value: unknown): value is VoiceNoteSummary {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<VoiceNoteSummary>;
  return (
    typeof candidate.markdown === "string" &&
    typeof candidate.provider === "string" &&
    typeof candidate.generatedAt === "string"
  );
}

function storageAvailable() {
  return typeof localStorage !== "undefined";
}

export function createVoiceNote(input: VoiceNoteInput): VoiceNote {
  const transcript = normalizeTranscript(input.transcript);
  return {
    id: input.id,
    title: titleFromTranscript(transcript),
    transcript,
    createdAt: input.createdAt,
    durationMs: input.durationMs,
    audioDataUrl: input.audioDataUrl,
  };
}

export function createVoiceNoteSummary(result: VoiceNoteSummaryGenerateResponse, generatedAt = new Date().toISOString()): VoiceNoteSummary {
  return {
    markdown: result.markdown,
    provider: result.provider,
    generatedAt,
  };
}

export function loadLegacyVoiceNotes(): VoiceNote[] {
  if (!storageAvailable()) {
    return [];
  }

  const raw = localStorage.getItem(VOICE_NOTES_STORAGE_KEY);
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isVoiceNote) : [];
  } catch {
    return [];
  }
}

export function clearLegacyVoiceNotes() {
  if (storageAvailable()) {
    localStorage.removeItem(VOICE_NOTES_STORAGE_KEY);
  }
}

export function formatVoiceNoteDuration(durationMs: number) {
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
