import assert from "node:assert/strict";
import test from "node:test";

import { hashForView, viewFromHash, type View } from "../app/view";

const expectedHashes: Record<View, string> = {
  capture: "#/capture",
  live: "#/live",
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
  assert.equal(viewFromHash(""), "capture");
  assert.equal(viewFromHash("#/"), "capture");
  assert.equal(viewFromHash("#/capture"), "capture");
  assert.equal(viewFromHash("#/live"), "live");
  assert.equal(viewFromHash("#/captures"), "capture");
  assert.equal(viewFromHash("#/voice-notes"), "voice-notes");
  assert.equal(viewFromHash("#/settings"), "settings");
  assert.equal(viewFromHash("#/dashboard"), "capture");
  assert.equal(viewFromHash("#/jobs"), "capture");
  assert.equal(viewFromHash("#/missing"), "capture");
});
