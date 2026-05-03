import assert from "node:assert/strict";
import test from "node:test";

import { userVisibleArtifacts } from "../lib/artifacts";

test("debug and internal artifacts stay out of frontend file lists", () => {
  const artifacts = userVisibleArtifacts([
    {
      name: "transcript.md",
      path: "/tmp/transcript.md",
      size_bytes: 100,
      download_url: "/artifacts/job/transcript.md",
    },
    {
      name: "transcript.json",
      path: "/tmp/logs/transcript.json",
      size_bytes: 100,
      download_url: "/artifacts/job/transcript.json",
    },
    {
      name: "deepgram-events.jsonl",
      path: "/tmp/logs/deepgram-events.jsonl",
      size_bytes: 100,
      download_url: "/artifacts/job/deepgram-events.jsonl",
    },
    {
      name: "controller-events.jsonl",
      path: "/tmp/logs/controller-events.jsonl",
      size_bytes: 100,
      download_url: "/artifacts/job/controller-events.jsonl",
    },
    {
      name: "metadata.json",
      path: "/tmp/artifacts/metadata.json",
      size_bytes: 100,
      download_url: "/artifacts/job/metadata.json",
    },
    {
      name: "transcript.txt",
      path: "/tmp/artifacts/transcript.txt",
      size_bytes: 100,
      download_url: "/artifacts/job/transcript.txt",
    },
  ]);

  assert.deepEqual(
    artifacts.map((artifact) => artifact.name),
    ["transcript.md"],
  );
});
