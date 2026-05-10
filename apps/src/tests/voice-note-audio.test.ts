import assert from "node:assert/strict";
import test from "node:test";

import * as voiceNoteAudio from "../lib/voice-note-audio";
import {
  encodeLinear16,
  formatVoiceNoteRecordingError,
  isAudibleMicrophoneInput,
  mergeTranscriptEvent,
  processedMicrophoneAudioConstraints,
  startMicrophonePcmStream,
} from "../lib/voice-note-audio";
import type { TranscriptBlock } from "../lib/types";

const voiceNoteAudioExports = voiceNoteAudio as typeof voiceNoteAudio & {
  isVoiceNoteTranscriptTextEvent?: (event: TranscriptBlock) => boolean;
};

test("encodes microphone float samples as little-endian linear16 pcm", () => {
  const pcm = new Int16Array(encodeLinear16(new Float32Array([-1, -0.5, 0, 0.5, 1]), 16_000, 16_000));

  assert.deepEqual(Array.from(pcm), [-32768, -16384, 0, 16383, 32767]);
});

test("downsamples microphone audio before encoding for live transcription", () => {
  const pcm = new Int16Array(encodeLinear16(new Float32Array([0, 0.25, 0.5, 0.75]), 32_000, 16_000));

  assert.deepEqual(Array.from(pcm), [4095, 20479]);
});

test("detects when microphone samples contain speech-level audio", () => {
  assert.equal(isAudibleMicrophoneInput(new Float32Array([0, 0.004, -0.008, 0.03])), true);
});

test("treats near-silent microphone samples as no usable speech audio", () => {
  assert.equal(isAudibleMicrophoneInput(new Float32Array([0, 0.001, -0.002, 0.003])), false);
});

test("recognizes only non-empty live transcription events as voice note text", () => {
  const isTextEvent = voiceNoteAudioExports.isVoiceNoteTranscriptTextEvent;

  assert.equal(typeof isTextEvent, "function");
  assert.equal(isTextEvent?.({ type: "interim", text: "" }), false);
  assert.equal(isTextEvent?.({ type: "final", text: "   " }), false);
  assert.equal(isTextEvent?.({ type: "interim", text: "spoken words" }), true);
  assert.equal(isTextEvent?.({ type: "warning", message: "paused" }), false);
});

test("processed microphone constraints request browser voice processing", () => {
  assert.deepEqual(processedMicrophoneAudioConstraints, {
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
});

test("microphone websocket startup surfaces server warning messages", async () => {
  class FakeWebSocket {
    static CLOSING = 2;
    static instances: FakeWebSocket[] = [];

    binaryType = "";
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onopen: (() => void) | null = null;
    readyState = 1;

    constructor(readonly url: string) {
      FakeWebSocket.instances.push(this);
    }

    close() {
      this.readyState = 3;
      this.onclose?.();
    }

    send() {
      return;
    }

    emit(payload: unknown) {
      this.onmessage?.({ data: JSON.stringify(payload) });
    }
  }

  const originalWebSocket = globalThis.WebSocket;
  const originalWindow = globalThis.window;
  const stoppedTracks: string[] = [];
  globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
  globalThis.window = {
    clearTimeout: globalThis.clearTimeout,
    setTimeout: globalThis.setTimeout,
  } as unknown as Window & typeof globalThis;

  try {
    const stream = {
      getTracks: () => [{ stop: () => stoppedTracks.push("track") }],
    } as unknown as MediaStream;
    const promise = startMicrophonePcmStream({
      stream,
      url: "ws://127.0.0.1:8788/ws/jobs/job-1/microphone",
      requireReady: true,
    });
    const socket = FakeWebSocket.instances[0];
    assert.ok(socket);

    socket.emit({ type: "warning", message: "Microphone recording is not enabled for this capture." });
    socket.close();

    await assert.rejects(promise, /Microphone recording is not enabled for this capture\./);
    assert.deepEqual(stoppedTracks, ["track"]);
  } finally {
    globalThis.WebSocket = originalWebSocket;
    globalThis.window = originalWindow;
  }
});

test("microphone websocket startup explains rejected connections", async () => {
  class FakeWebSocket {
    static CLOSING = 2;
    static instances: FakeWebSocket[] = [];

    binaryType = "";
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    onopen: (() => void) | null = null;
    readyState = 1;

    constructor(readonly url: string) {
      FakeWebSocket.instances.push(this);
    }

    close() {
      this.readyState = 3;
      this.onclose?.();
    }

    send() {
      return;
    }
  }

  const originalWebSocket = globalThis.WebSocket;
  const originalWindow = globalThis.window;
  globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
  globalThis.window = {
    clearTimeout: globalThis.clearTimeout,
    setTimeout: globalThis.setTimeout,
  } as unknown as Window & typeof globalThis;

  try {
    const stream = {
      getTracks: () => [{ stop: () => undefined }],
    } as unknown as MediaStream;
    const promise = startMicrophonePcmStream({
      stream,
      url: "ws://127.0.0.1:8788/ws/jobs/job-1/microphone",
      requireReady: true,
    });
    const socket = FakeWebSocket.instances[0];
    assert.ok(socket);

    socket.close();

    await assert.rejects(promise, /Microphone connection was rejected\. Restart the app and try again\./);
  } finally {
    globalThis.WebSocket = originalWebSocket;
    globalThis.window = originalWindow;
  }
});

test("merges final and interim live transcription events into note text", () => {
  let state = mergeTranscriptEvent({ transcript: "First sentence", draft: "" }, { type: "interim", text: "draft words" });
  state = mergeTranscriptEvent(state, { type: "final", text: "Finished words" });

  assert.deepEqual(state, {
    transcript: "First sentence Finished words",
    draft: "",
  });
});

test("keeps visible draft text when a later live transcription event is empty", () => {
  const draftAfterEmptyInterim = mergeTranscriptEvent(
    { transcript: "Committed words", draft: "visible draft" },
    { type: "interim", text: "" },
  );
  const draftAfterEmptyFinal = mergeTranscriptEvent(
    { transcript: "Committed words", draft: "visible draft" },
    { type: "final", text: "   " },
  );

  assert.deepEqual(draftAfterEmptyInterim, {
    transcript: "Committed words",
    draft: "visible draft",
  });
  assert.deepEqual(draftAfterEmptyFinal, {
    transcript: "Committed words",
    draft: "visible draft",
  });
});

test("explains blocked microphone access with a clear recovery step", () => {
  const error = new DOMException(
    "The request is not allowed by the user agent or the platform in the current context, possibly because the user denied permission.",
    "NotAllowedError",
  );

  assert.equal(
    formatVoiceNoteRecordingError(error),
    "Microphone access is blocked. Open microphone settings, allow thirdeye, then try again.",
  );
});
