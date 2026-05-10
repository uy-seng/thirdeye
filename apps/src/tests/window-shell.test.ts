import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
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
  bundle: {
    macOS: {
      dmg: {
        appPosition: { x: number; y: number };
        applicationFolderPosition: { x: number; y: number };
        background: string;
        windowSize: { height: number; width: number };
      };
    };
  };
};

test("macOS window uses a solid dark native title bar", () => {
  const mainWindow = tauriConfig.app.windows.find((window) => window.label === "main");

  assert.ok(mainWindow);
  assert.equal(mainWindow.titleBarStyle, "Transparent");
  assert.equal(mainWindow.backgroundColor, "#050505");
  assert.equal(mainWindow.theme, "Dark");
});

test("macOS DMG uses an explicit light installer layout", () => {
  const dmg = tauriConfig.bundle.macOS.dmg;

  assert.equal(dmg.background, "assets/dmg-background.png");
  assert.equal(existsSync(new URL("../../tauri/assets/dmg-background.png", import.meta.url)), true);
  assert.deepEqual(dmg.windowSize, { width: 660, height: 400 });
  assert.deepEqual(dmg.appPosition, { x: 180, y: 190 });
  assert.deepEqual(dmg.applicationFolderPosition, { x: 480, y: 190 });
});
