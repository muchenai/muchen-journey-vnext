// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const layout = readFileSync(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
