import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const source = [
  readFileSync(join(testDir, "../app/App.tsx"), "utf8"),
  readFileSync(join(testDir, "../app/view.ts"), "utf8"),
  readFileSync(join(testDir, "../components/navigation/Navigation.tsx"), "utf8"),
].join("\n");

test("does not show a Files tab in the app navigation", () => {
  assert.doesNotMatch(source, /label:\s*"Files"/);
  assert.doesNotMatch(source, /view:\s*"artifacts"/);
  assert.doesNotMatch(source, /view\s*===\s*"artifacts"/);
});

test("uses the shared thirdeye logo in the navigation brand", () => {
  assert.match(source, /import thirdeyeLogoUrl from "\.\.\/\.\.\/\.\.\/\.\.\/assets\/logo\.png";/);
  assert.match(source, /<img alt="thirdeye logo" className="brand-logo" src=\{thirdeyeLogoUrl\} \/>/);
  assert.doesNotMatch(source, /<div className="brand-mark">t<\/div>/);
});
