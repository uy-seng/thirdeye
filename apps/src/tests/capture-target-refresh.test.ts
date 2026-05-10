import assert from "node:assert/strict";
import test from "node:test";

import { createLatestTargetRequestGate } from "../features/capture/captureTargets";

test("target refresh gate ignores stale permission responses after a newer refresh starts", () => {
  const gate = createLatestTargetRequestGate();

  const staleRequest = gate.start();
  const latestRequest = gate.start();

  assert.equal(gate.isLatest(staleRequest), false);
  assert.equal(gate.isLatest(latestRequest), true);
});
