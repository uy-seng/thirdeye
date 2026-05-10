import assert from "node:assert/strict";
import test from "node:test";

import {
  encodeLinear16,
  mergeTranscriptEvent,
  processedMicrophoneAudioConstraints,
  startMicrophonePcmStream,
} from "../lib/voice-note-audio";

test("encodes microphone float samples as little-endian linear16 pcm", () => {
  const pcm = new Int16Array(encodeLinear16(new Float32Array([-1, -0.5, 0, 0.5, 1]), 16_000, 16_000));

  assert.deepEqual(Array.from(pcm), [-32768, -16384, 0, 16383, 32767]);
});

test("downsamples microphone audio before encoding for live transcription", () => {
  const pcm = new Int16Array(encodeLinear16(new Float32Array([0, 0.25, 0.5, 0.75]), 32_000, 16_000));

  assert.deepEqual(Array.from(pcm), [4095, 20479]);
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
