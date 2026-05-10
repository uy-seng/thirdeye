import assert from "node:assert/strict";
import test from "node:test";

import {
  API_BASE,
  apiJson,
  apiUrl,
  artifactHref,
  captureMicrophoneLiveUrl,
  createDesktop,
  deleteVoiceNote,
  deleteJob,
  destroyDesktop,
  generateTranscriptSummary,
  generateVoiceNoteSummary,
  getDesktops,
  getJobs,
  getVoiceNotes,
  importVoiceNotes,
  saveVoiceNote,
  saveTranscriptSummary,
  setEchoCancellationEnabled,
  setRecordMicrophoneEnabled,
  setTargetAudioMuted,
  startCapture,
  updateVoiceNote,
} from "../lib/api";

test("apiUrl points the native app at the local controller API", () => {
  assert.equal(API_BASE, "http://127.0.0.1:8788");
  assert.equal(apiUrl("/api/jobs"), "http://127.0.0.1:8788/api/jobs");
});

test("captureMicrophoneLiveUrl points processed capture microphone audio at the job socket", () => {
  assert.equal(captureMicrophoneLiveUrl("job-123"), "ws://127.0.0.1:8788/ws/jobs/job-123/microphone");
});

test("artifactHref keeps absolute artifact links and expands local paths", () => {
  assert.equal(artifactHref("http://127.0.0.1:8788/artifacts/job/summary.md"), "http://127.0.0.1:8788/artifacts/job/summary.md");
  assert.equal(artifactHref("/artifacts/job/summary.md"), "http://127.0.0.1:8788/artifacts/job/summary.md");
});

test("controller requests do not attach local authentication state", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify([]), { headers: { "content-type": "application/json" }, status: 200 });
  };

  try {
    await getJobs();

    const headers = calls[0]?.init?.headers as Headers;
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs");
    assert.equal(headers.has("x-thirdeye-client"), false);
    assert.equal(headers.has("authorization"), false);
    assert.equal(calls[0]?.init?.credentials, undefined);
    assert.equal(artifactHref("/artifacts/job/summary.md"), "http://127.0.0.1:8788/artifacts/job/summary.md");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("apiJson formats structured FastAPI validation errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      detail: [
        {
          type: "extra_forbidden",
          loc: ["body", "record_microphone"],
          msg: "Extra inputs are not permitted",
          input: true,
        },
      ],
    }),
    { headers: { "content-type": "application/json" }, status: 422 },
  );

  try {
    await assert.rejects(
      () => apiJson("/api/jobs/start", { method: "POST", body: JSON.stringify({ record_microphone: true }) }),
      /record_microphone: Extra inputs are not permitted/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("apiJson explains local service connection failures", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new TypeError("Load failed");
  };

  try {
    await assert.rejects(
      () => apiJson("/api/jobs/start", { method: "POST", body: JSON.stringify({ title: "Capture" }) }),
      /Could not connect to the local app service\. Restart the app and try again\./,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("desktop session APIs create, list, and destroy isolated desktops", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    if (String(input).endsWith("/api/desktops") && init?.method === "POST") {
      return new Response(
        JSON.stringify({
          id: "desktop-1",
          target_id: "desktop:desktop-1",
          label: "Interview room",
          container_id: "container-1",
          container_name: "thirdeye-desktop-desktop-1",
          browser_url: "http://127.0.0.1:3002",
          agent_url: "http://127.0.0.1:8793",
          status: "ready",
          created_at: "2026-05-02T00:00:00Z",
          active_job_id: null,
          active_job_state: null,
          error_message: null,
        }),
        { headers: { "content-type": "application/json" }, status: 200 },
      );
    }
    if (String(input).endsWith("/api/desktops/desktop-1/destroy")) {
      return new Response(JSON.stringify({ status: "destroyed" }), { headers: { "content-type": "application/json" }, status: 200 });
    }
    return new Response(JSON.stringify({ desktops: [] }), { headers: { "content-type": "application/json" }, status: 200 });
  };

  try {
    await getDesktops();
    const created = await createDesktop("Interview room");
    await destroyDesktop("desktop-1");

    assert.equal(created.browser_url, "http://127.0.0.1:3002");
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/desktops");
    assert.equal(calls[1]?.url, "http://127.0.0.1:8788/api/desktops");
    assert.equal(calls[1]?.init?.method, "POST");
    assert.deepEqual(JSON.parse(String(calls[1]?.init?.body)), { label: "Interview room" });
    assert.equal(calls[2]?.url, "http://127.0.0.1:8788/api/desktops/desktop-1/destroy");
    assert.equal(calls[2]?.init?.method, "POST");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("generateTranscriptSummary posts a live summary prompt for the selected job", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        request_id: "summary-1",
        markdown: "# Live Summary",
        provider: "openclaw/test",
        source: { final_block_count: 2, interim_included: true },
      }),
      { headers: { "content-type": "application/json" }, status: 200 },
    );
  };

  try {
    const result = await generateTranscriptSummary("job-123", "Summarize decisions");

    assert.equal(result.request_id, "summary-1");
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs/job-123/transcript-summary/generate");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(calls[0]?.init?.credentials, undefined);
    assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), { prompt: "Summarize decisions" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("saveTranscriptSummary persists the generated live summary result", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        name: "transcript-summary-20260423.md",
        path: "/tmp/transcript-summary-20260423.md",
        size_bytes: 2048,
        download_url: "/artifacts/job-123/transcript-summary-20260423.md",
      }),
      { headers: { "content-type": "application/json" }, status: 200 },
    );
  };

  try {
    const result = await saveTranscriptSummary("job-123", "summary-1");

    assert.equal(result.name, "transcript-summary-20260423.md");
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs/job-123/transcript-summary/save");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(calls[0]?.init?.credentials, undefined);
    assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), { request_id: "summary-1" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("generateVoiceNoteSummary posts a voice note transcript to OpenClaw", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        markdown: "# Voice Summary",
        provider: "openclaw/test",
      }),
      { headers: { "content-type": "application/json" }, status: 200 },
    );
  };

  try {
    const result = await generateVoiceNoteSummary({
      title: "Quick note",
      transcript: "Follow up tomorrow.",
      prompt: "Summarize this voice note.",
    });

    assert.equal(result.markdown, "# Voice Summary");
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/voice-notes/summary/generate");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(calls[0]?.init?.credentials, undefined);
    assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), {
      title: "Quick note",
      transcript: "Follow up tomorrow.",
      prompt: "Summarize this voice note.",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("voice note storage API uses controller persistence routes", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const note = {
    id: "note-1",
    title: "Quick note",
    transcript: "Follow up tomorrow.",
    createdAt: "2026-04-30T16:00:00.000Z",
    durationMs: 10_000,
    audioDataUrl: "data:audio/webm;base64,abc123",
  };
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const payload = init?.method === undefined || url.endsWith("/api/voice-notes/import") ? [note] : note;
    return new Response(JSON.stringify(payload), { headers: { "content-type": "application/json" }, status: 200 });
  };

  try {
    assert.deepEqual(await getVoiceNotes(), [note]);
    assert.equal((await saveVoiceNote(note)).id, "note-1");
    assert.equal((await updateVoiceNote("note-1", { title: "Updated" })).id, "note-1");
    assert.deepEqual(await importVoiceNotes([note]), [note]);
    assert.equal((await deleteVoiceNote("note-1")).id, "note-1");

    assert.deepEqual(
      calls.map((call) => [call.url, call.init?.method ?? "GET"]),
      [
        ["http://127.0.0.1:8788/api/voice-notes", "GET"],
        ["http://127.0.0.1:8788/api/voice-notes", "POST"],
        ["http://127.0.0.1:8788/api/voice-notes/note-1", "PATCH"],
        ["http://127.0.0.1:8788/api/voice-notes/import", "POST"],
        ["http://127.0.0.1:8788/api/voice-notes/note-1", "DELETE"],
      ],
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("startCapture sends screen recording and summary preferences", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        id: "job-123",
        title: "Transcript only",
        source_url: null,
        created_at: "2026-04-23T00:00:00Z",
        started_at: null,
        stopped_at: null,
        state: "live_streaming",
        max_duration_minutes: 30,
        auto_stop_enabled: false,
        silence_timeout_minutes: 5,
        recording_path: null,
        transcript_text_path: null,
        transcript_events_path: null,
        summary_path: null,
        error_message: null,
        capture_backend: "macos_local",
        capture_target: {
          id: "display:1",
          kind: "display",
          label: "Display 1",
          app_bundle_id: null,
          app_name: null,
          app_pid: null,
          window_id: null,
          display_id: "1",
        },
        metadata_json: {},
      }),
      { headers: { "content-type": "application/json" }, status: 200 },
    );
  };

  try {
    await startCapture({
      title: "Transcript only",
      capture_backend: "macos_local",
	      record_screen: false,
	      record_microphone: true,
	      echo_cancellation_enabled: true,
	      generate_summary: false,
      mute_target_audio: true,
      notify_on_inactivity: false,
      silence_timeout_minutes: 2,
      capture_target: {
        id: "display:1",
        kind: "display",
        label: "Display 1",
        app_bundle_id: null,
        app_name: null,
        app_pid: null,
        window_id: null,
        display_id: "1",
      },
    });

    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs/start");
    assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), {
      title: "Transcript only",
      source_url: null,
      capture_backend: "macos_local",
      capture_target: {
        id: "display:1",
        kind: "display",
        label: "Display 1",
        app_bundle_id: null,
        app_name: null,
        app_pid: null,
        window_id: null,
        display_id: "1",
      },
	      record_screen: false,
	      record_microphone: true,
	      echo_cancellation_enabled: true,
	      generate_summary: false,
      mute_target_audio: true,
      notify_on_inactivity: false,
      silence_timeout_minutes: 2,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("deleteJob removes the selected job through the local controller", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify({ ok: true }), { headers: { "content-type": "application/json" }, status: 200 });
  };

  try {
    await deleteJob("job-123");

    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs/job-123/delete");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(calls[0]?.init?.credentials, undefined);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("setTargetAudioMuted posts the runtime mute preference", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        id: "job-123",
        title: "Live capture",
        source_url: null,
        created_at: "2026-04-23T00:00:00Z",
        started_at: "2026-04-23T00:00:01Z",
        stopped_at: null,
        state: "live_streaming",
        max_duration_minutes: 30,
        auto_stop_enabled: false,
        silence_timeout_minutes: 5,
        recording_path: null,
        transcript_text_path: null,
        transcript_events_path: null,
        summary_path: null,
        error_message: null,
        capture_backend: "macos_local",
        capture_target: {
          id: "application:chrome",
          kind: "application",
          label: "Google Chrome",
          app_bundle_id: "com.google.Chrome",
          app_name: "Google Chrome",
          app_pid: 4242,
          window_id: null,
          display_id: null,
        },
        metadata_json: { session_preferences: { mute_target_audio: true } },
      }),
      { headers: { "content-type": "application/json" }, status: 200 },
    );
  };

  try {
    const result = await setTargetAudioMuted("job-123", true);

    assert.equal(result.metadata_json.session_preferences?.mute_target_audio, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs/job-123/mute-target-audio");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), { mute_target_audio: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("setRecordMicrophoneEnabled posts the runtime microphone preference", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        id: "job-123",
        title: "Live capture",
        source_url: null,
        created_at: "2026-04-23T00:00:00Z",
        started_at: "2026-04-23T00:00:01Z",
        stopped_at: null,
        state: "live_streaming",
        max_duration_minutes: 30,
        auto_stop_enabled: false,
        silence_timeout_minutes: 5,
        recording_path: null,
        transcript_text_path: null,
        transcript_events_path: null,
        summary_path: null,
        error_message: null,
        capture_backend: "macos_local",
        capture_target: {
          id: "display:main",
          kind: "display",
          label: "Built-in Display",
          app_bundle_id: null,
          app_name: null,
          app_pid: null,
          window_id: null,
          display_id: "main",
        },
        metadata_json: { session_preferences: { record_microphone: true } },
      }),
      { headers: { "content-type": "application/json" }, status: 200 },
    );
  };

  try {
    const result = await setRecordMicrophoneEnabled("job-123", true);

    assert.equal(result.metadata_json.session_preferences?.record_microphone, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs/job-123/record-microphone");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), { record_microphone: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("setEchoCancellationEnabled posts the runtime echo cancellation preference", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    return new Response(
      JSON.stringify({
        id: "job-123",
        title: "Live capture",
        source_url: null,
        created_at: "2026-04-23T00:00:00Z",
        started_at: "2026-04-23T00:00:01Z",
        stopped_at: null,
        state: "live_streaming",
        max_duration_minutes: 30,
        auto_stop_enabled: false,
        silence_timeout_minutes: 5,
        recording_path: null,
        transcript_text_path: null,
        transcript_events_path: null,
        summary_path: null,
        error_message: null,
        capture_backend: "macos_local",
        capture_target: {
          id: "display:main",
          kind: "display",
          label: "Built-in Display",
          app_bundle_id: null,
          app_name: null,
          app_pid: null,
          window_id: null,
          display_id: "main",
        },
        metadata_json: { session_preferences: { record_microphone: true, echo_cancellation_enabled: true } },
      }),
      { headers: { "content-type": "application/json" }, status: 200 },
    );
  };

  try {
    const result = await setEchoCancellationEnabled("job-123", true);

    assert.equal(result.metadata_json.session_preferences?.echo_cancellation_enabled, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, "http://127.0.0.1:8788/api/jobs/job-123/echo-cancellation");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.deepEqual(JSON.parse(String(calls[0]?.init?.body)), { echo_cancellation_enabled: true });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
