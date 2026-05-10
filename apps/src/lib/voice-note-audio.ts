import type { TranscriptBlock } from "./types";

export type VoiceNoteTranscriptState = {
  transcript: string;
  draft: string;
};

const microphoneBlockedMessage = "Microphone access is blocked. Open microphone settings, allow thirdeye, then try again.";
const audibleMicrophoneThreshold = 0.02;

export const processedMicrophoneAudioConstraints: MediaStreamConstraints = {
  audio: {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
};

export type MicrophonePcmStreamSession = {
  stop: (options?: { finalize?: boolean; timeoutMs?: number }) => Promise<void>;
};

type MicrophonePcmStreamOptions = {
  stream: MediaStream;
  url: string;
  requireReady?: boolean;
  readyTimeoutMs?: number;
  onMessage?: (event: unknown) => void;
  onClose?: () => void;
};

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

export async function requestProcessedMicrophoneStream() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone recording is not available in this window.");
  }
  return navigator.mediaDevices.getUserMedia(processedMicrophoneAudioConstraints);
}

export function stopMediaStream(stream: MediaStream | null | undefined) {
  stream?.getTracks().forEach((track) => track.stop());
}

export function startMicrophonePcmStream({
  stream,
  url,
  requireReady = false,
  readyTimeoutMs = 5_000,
  onMessage,
  onClose,
}: MicrophonePcmStreamOptions): Promise<MicrophonePcmStreamSession> {
  return new Promise((resolve, reject) => {
    const websocket = new WebSocket(url);
    websocket.binaryType = "arraybuffer";
    let audioContext: AudioContext | null = null;
    let source: MediaStreamAudioSourceNode | null = null;
    let processor: ScriptProcessorNode | null = null;
    let silentGain: GainNode | null = null;
    let recording = false;
    let resolved = false;
    let stopped = false;
    let finishResolve: (() => void) | null = null;
    let startupError: Error | null = null;

    function cleanupGraph() {
      recording = false;
      processor?.disconnect();
      source?.disconnect();
      silentGain?.disconnect();
      void audioContext?.close().catch(() => undefined);
      processor = null;
      source = null;
      silentGain = null;
      audioContext = null;
    }

    function resolveFinish() {
      finishResolve?.();
      finishResolve = null;
    }

    function rejectBeforeReady(error: Error) {
      if (resolved) {
        return;
      }
      stopped = true;
      cleanupGraph();
      stopMediaStream(stream);
      reject(startupError ?? error);
    }

    const readyTimer = window.setTimeout(() => {
      rejectBeforeReady(new Error("Microphone connection did not start. Restart the app and try again."));
      if (websocket.readyState < WebSocket.CLOSING) {
        websocket.close();
      }
    }, readyTimeoutMs);

    function buildSession(): MicrophonePcmStreamSession {
      return {
        stop: ({ finalize = true, timeoutMs = 5_000 } = {}) =>
          new Promise((finish) => {
            if (stopped) {
              finish();
              return;
            }
            stopped = true;
            cleanupGraph();
            stopMediaStream(stream);
            if (websocket.readyState === WebSocket.OPEN && finalize) {
              finishResolve = finish;
              websocket.send(JSON.stringify({ type: "Finalize" }));
              window.setTimeout(() => {
                resolveFinish();
                if (websocket.readyState < WebSocket.CLOSING) {
                  websocket.close();
                }
              }, timeoutMs);
              return;
            }
            if (websocket.readyState < WebSocket.CLOSING) {
              websocket.close();
            }
            finish();
          }),
      };
    }

    function startGraph() {
      if (resolved || stopped) {
        return;
      }
      window.clearTimeout(readyTimer);
      audioContext = new AudioContext();
      source = audioContext.createMediaStreamSource(stream);
      processor = audioContext.createScriptProcessor(4096, 1, 1);
      silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      recording = true;
      processor.onaudioprocess = (event) => {
        if (!recording || websocket.readyState !== WebSocket.OPEN) {
          return;
        }
        const samples = event.inputBuffer.getChannelData(0);
        websocket.send(encodeLinear16(samples, audioContext?.sampleRate ?? 16_000));
      };
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioContext.destination);
      resolved = true;
      resolve(buildSession());
    }

    websocket.onopen = () => {
      if (!requireReady) {
        startGraph();
      }
    };
    websocket.onerror = () => {
      startupError = startupError ?? new Error("Microphone connection was rejected. Restart the app and try again.");
      rejectBeforeReady(startupError);
    };
    websocket.onclose = () => {
      window.clearTimeout(readyTimer);
      if (!stopped && resolved) {
        cleanupGraph();
        stopMediaStream(stream);
        onClose?.();
      }
      resolveFinish();
      rejectBeforeReady(new Error("Microphone connection was rejected. Restart the app and try again."));
    };
    websocket.onmessage = (message) => {
      if (typeof message.data !== "string") {
        return;
      }
      let payload: unknown;
      try {
        payload = JSON.parse(message.data);
      } catch {
        return;
      }
      if (requireReady && !resolved && typeof payload === "object" && payload && "type" in payload && payload.type === "ready") {
        startGraph();
        return;
      }
      if (
        !resolved &&
        typeof payload === "object" &&
        payload &&
        "type" in payload &&
        payload.type === "warning" &&
        "message" in payload &&
        typeof payload.message === "string" &&
        payload.message.trim()
      ) {
        startupError = new Error(payload.message.trim());
      }
      if (typeof payload === "object" && payload && "type" in payload && payload.type === "complete") {
        resolveFinish();
        if (websocket.readyState < WebSocket.CLOSING) {
          websocket.close();
        }
      }
      onMessage?.(payload);
    };
  });
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
