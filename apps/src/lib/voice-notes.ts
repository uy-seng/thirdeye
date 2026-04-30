export const VOICE_NOTES_STORAGE_KEY = "thirdeye.voice-notes";

export type VoiceNote = {
  id: string;
  title: string;
  transcript: string;
  createdAt: string;
  durationMs: number;
  audioDataUrl?: string;
  summary?: VoiceNoteSummary;
};

export type VoiceNoteSummary = {
  markdown: string;
  provider: string;
  generatedAt: string;
};

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

export function loadVoiceNotes(): VoiceNote[] {
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

export function saveVoiceNotes(notes: VoiceNote[]) {
  if (!storageAvailable()) {
    return;
  }

  localStorage.setItem(VOICE_NOTES_STORAGE_KEY, JSON.stringify(notes));
}

export function deleteVoiceNote(noteId: string) {
  saveVoiceNotes(loadVoiceNotes().filter((note) => note.id !== noteId));
}

export function formatVoiceNoteDuration(durationMs: number) {
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
