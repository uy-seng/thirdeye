import assert from "node:assert/strict";
import test from "node:test";

import { hashForView, viewFromHash, type View } from "../app/view";

const expectedHashes: Record<View, string> = {
  overview: "#/",
  capture: "#/capture",
  live: "#/live",
  captures: "#/captures",
  "voice-notes": "#/voice-notes",
  settings: "#/settings",
};

test("workspace views have stable hash routes", () => {
  assert.deepEqual(
    Object.fromEntries((Object.keys(expectedHashes) as View[]).map((view) => [view, hashForView(view)])),
    expectedHashes,
  );
});

test("workspace routes decode current and legacy hashes", () => {
  assert.equal(viewFromHash(""), "overview");
  assert.equal(viewFromHash("#/"), "overview");
  assert.equal(viewFromHash("#/capture"), "capture");
  assert.equal(viewFromHash("#/live"), "live");
  assert.equal(viewFromHash("#/captures"), "captures");
  assert.equal(viewFromHash("#/voice-notes"), "voice-notes");
  assert.equal(viewFromHash("#/settings"), "settings");
  assert.equal(viewFromHash("#/dashboard"), "overview");
  assert.equal(viewFromHash("#/jobs"), "captures");
  assert.equal(viewFromHash("#/missing"), "overview");
});
