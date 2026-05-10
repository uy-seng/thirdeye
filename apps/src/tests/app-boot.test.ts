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

test("settings stop shows local service stop errors", () => {
  const source = readFileSync(resolve(import.meta.dirname, "../app/App.tsx"), "utf-8");
  const stopBody = source.match(/async function handleStopServices\(\) \{(?<body>[\s\S]*?)\n  \}/)?.groups?.body ?? "";

  assert.match(stopBody, /try\s*\{/);
  assert.match(stopBody, /setNotice\("Stopping local services\.\.\."\)/);
  assert.match(stopBody, /catch \(error\)/);
  assert.match(stopBody, /Unable to stop local services\./);
});
