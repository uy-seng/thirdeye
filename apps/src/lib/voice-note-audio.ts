import type { TranscriptBlock } from "./types";

export type VoiceNoteTranscriptState = {
  transcript: string;
  draft: string;
};

const microphoneBlockedMessage = "Microphone access is blocked. Open microphone settings, allow thirdeye, then try again.";
const audibleMicrophoneThreshold = 0.02;

function errorName(error: unknown) {
  return error instanceof Error ? error.name : "";
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "";
}

export function isVoiceNoteMicrophoneAccessBlocked(error: unknown) {
  const name = errorName(error);
  const message = errorMessage(error).toLowerCase();
  return (
    name === "NotAllowedError" ||
    name === "SecurityError" ||
    message.includes("permission") ||
    message.includes("not allowed") ||
    message.includes("denied")
  );
}

export function formatVoiceNoteRecordingError(error: unknown) {
  const name = errorName(error);
  if (isVoiceNoteMicrophoneAccessBlocked(error)) {
    return microphoneBlockedMessage;
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No microphone was found. Connect a microphone and try again.";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "The microphone is busy. Close other apps using it, then try again.";
  }
  return errorMessage(error) || "Unable to start voice recording.";
}

function appendText(current: string, incoming: string) {
  const next = incoming.trim();
  if (!next) {
    return current;
  }
  return current ? `${current} ${next}` : next;
}

export function isAudibleMicrophoneInput(input: Float32Array, threshold = audibleMicrophoneThreshold) {
  return input.some((sample) => Math.abs(sample) >= threshold);
}

export function isVoiceNoteTranscriptTextEvent(event: TranscriptBlock) {
  return (event.type === "final" || event.type === "interim") && Boolean(event.text?.trim());
}

function downsample(input: Float32Array, inputSampleRate: number, outputSampleRate: number) {
  if (inputSampleRate === outputSampleRate) {
    return input;
  }

  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.max(1, Math.floor(input.length / ratio));
  const output = new Float32Array(outputLength);

  for (let outputIndex = 0; outputIndex < outputLength; outputIndex += 1) {
    const start = Math.floor(outputIndex * ratio);
    const end = Math.min(input.length, Math.floor((outputIndex + 1) * ratio));
    let total = 0;
    let count = 0;
    for (let inputIndex = start; inputIndex < end; inputIndex += 1) {
      total += input[inputIndex] ?? 0;
      count += 1;
    }
    output[outputIndex] = count > 0 ? total / count : input[start] ?? 0;
  }

  return output;
}

export function encodeLinear16(input: Float32Array, inputSampleRate: number, outputSampleRate = 16_000) {
  const samples = downsample(input, inputSampleRate, outputSampleRate);
  const output = new ArrayBuffer(samples.length * 2);
  const view = new DataView(output);

  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index] ?? 0));
    const value = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    view.setInt16(index * 2, value, true);
  }

  return output;
}

export function mergeTranscriptEvent(state: VoiceNoteTranscriptState, event: TranscriptBlock): VoiceNoteTranscriptState {
  if (event.type === "interim") {
    const draft = event.text?.trim() ?? "";
    return draft ? { ...state, draft } : state;
  }

  if (event.type === "final") {
    if (!event.text?.trim()) {
      return state;
    }
    return {
      transcript: appendText(state.transcript, event.text ?? ""),
      draft: "",
    };
  }

  return state;
}

export function mergedTranscriptText(state: VoiceNoteTranscriptState) {
  return appendText(state.transcript, state.draft);
}
