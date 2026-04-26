import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../styles.css"), "utf8");

test("uses a plain white app background instead of a notebook grid", () => {
  const bodyRule = css.match(/body\s*\{(?<body>[^}]+)\}/)?.groups?.body ?? "";

  assert.match(bodyRule, /background:\s*#ffffff\s*;/);
  assert.doesNotMatch(bodyRule, /linear-gradient/);
  assert.doesNotMatch(bodyRule, /background-size:\s*28px 28px/);
});

test("collapses shared two-panel layouts to one panel per row at compact widths", () => {
  assert.match(
    css,
    /@media\s*\(max-width:\s*1400px\)\s*\{[\s\S]*?\.grid-two\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\);[\s\S]*?\}/,
  );
});
