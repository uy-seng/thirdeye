import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const tauriConfig = JSON.parse(readFileSync(new URL("../../tauri/tauri.conf.json", import.meta.url), "utf8")) as {
  app: {
    windows: Array<{
      backgroundColor?: string;
      label?: string;
      theme?: string;
      titleBarStyle?: string;
    }>;
  };
};

test("macOS window uses a solid dark native title bar", () => {
  const mainWindow = tauriConfig.app.windows.find((window) => window.label === "main");

  assert.ok(mainWindow);
  assert.equal(mainWindow.titleBarStyle, "Transparent");
  assert.equal(mainWindow.backgroundColor, "#050505");
  assert.equal(mainWindow.theme, "Dark");
});
