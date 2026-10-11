// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const learnerHome = await readFile(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");
const shell = await readFile(new URL("../src/app/human-experience.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");



test("locked, empty and error surfaces keep one safe recovery action", () => {
  for (const state of ["locked", "empty", "error"]) {
    assert.match(shell, new RegExp(`"${state}"`));
  }
  assert.match(shell, /className="button primary"/);
  assert.match(shell, /href=\{action\.href\}/);
  assert.match(styles, /\.experience-state/);
  assert.match(styles, /\.fact-label/);
});
