import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

test("app boot starts local services before loading controller data", () => {
  const source = readFileSync(resolve(import.meta.dirname, "../app/App.tsx"), "utf-8");
  const bootBody = source.match(/async function boot\(\) \{(?<body>[\s\S]*?)\n    \}/)?.groups?.body ?? "";

  assert.equal(bootBody.includes("void refreshControllerData();"), false);
  assert.match(bootBody, /await startLocalServices\(\)[\s\S]*await refreshControllerData\(\)/);
});
