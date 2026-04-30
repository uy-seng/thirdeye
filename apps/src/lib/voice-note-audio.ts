import type { TranscriptBlock } from "./types";

export type VoiceNoteTranscriptState = {
  transcript: string;
  draft: string;
};

function appendText(current: string, incoming: string) {
  const next = incoming.trim();
  if (!next) {
    return current;
  }
  return current ? `${current} ${next}` : next;
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
    return { ...state, draft: event.text?.trim() ?? "" };
  }

  if (event.type === "final") {
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
