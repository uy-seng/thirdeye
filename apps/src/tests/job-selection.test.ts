import assert from "node:assert/strict";
import test from "node:test";

import { chooseSelectedJobId } from "../lib/job-selection";
import type { JobResponse } from "../lib/types";

function job(id: string, state = "completed"): JobResponse {
  return {
    id,
    title: id,
    source_url: null,
    created_at: "2026-04-23T00:00:00Z",
    started_at: null,
    stopped_at: null,
    state,
    max_duration_minutes: 120,
    auto_stop_enabled: true,
    silence_timeout_minutes: 10,
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
  };
}

test("prefers a newly created capture over the previous selected job", () => {
  assert.equal(
    chooseSelectedJobId({
      currentJobId: "previous-job",
      jobs: [job("new-job", "live_streaming"), job("previous-job")],
      preferredJobId: "new-job",
    }),
    "new-job",
  );
});

test("keeps the current selected job when there is no new capture preference", () => {
  assert.equal(
    chooseSelectedJobId({
      currentJobId: "previous-job",
      jobs: [job("new-job", "live_streaming"), job("previous-job")],
    }),
    "previous-job",
  );
});

test("falls back to the active capture when the current selected job is gone", () => {
  assert.equal(
    chooseSelectedJobId({
      currentJobId: "deleted-job",
      jobs: [job("active-job", "recording"), job("older-job")],
    }),
    "active-job",
  );
});
