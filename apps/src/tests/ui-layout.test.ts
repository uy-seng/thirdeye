import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appSource = () => readFileSync(resolve(import.meta.dirname, "../app/App.tsx"), "utf-8");
const navigationSource = () => readFileSync(resolve(import.meta.dirname, "../components/navigation/Navigation.tsx"), "utf-8");
const settingsSource = () => readFileSync(resolve(import.meta.dirname, "../features/settings/SettingsPanel.tsx"), "utf-8");
const voiceNotesSource = () => readFileSync(resolve(import.meta.dirname, "../features/voice-notes/VoiceNotesPanel.tsx"), "utf-8");

test("main navigation omits removed overview and captures tabs", () => {
  const source = navigationSource();

  assert.equal(source.includes('label: "Overview"'), false);
  assert.equal(source.includes('label: "Captures"'), false);
});

test("capture page owns capture history and details", () => {
  const source = appSource();
  const captureBranch = source.match(/\{visibleView === "capture" \? \((?<body>[\s\S]*?)\n        \) : null\}/)?.groups?.body ?? "";

  assert.match(captureBranch, /<StartCapturePanel/);
  assert.match(captureBranch, /<JobsTable/);
  assert.match(captureBranch, /<JobDetail/);
  assert.equal(source.includes('visibleView === "captures"'), false);
});

test("settings page owns isolated desktop workspaces", () => {
  const app = appSource();
  const settings = settingsSource();
  const captureBranch = app.match(/\{visibleView === "capture" \? \((?<body>[\s\S]*?)\n        \) : null\}/)?.groups?.body ?? "";

  assert.equal(captureBranch.includes("<DesktopSessionsPanel"), false);
  assert.match(settings, /DesktopSessionsPanel/);
});

test("voice note Ask panel only renders while recording", () => {
  const source = voiceNotesSource();

  assert.match(source, /\{isRecording \? \(\s*<Card className="summary-panel voice-ask-ai-card">/);
});
