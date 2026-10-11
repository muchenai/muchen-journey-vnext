// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const taskPage = readFileSync(new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url), "utf8");
const learnerHome = readFileSync(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const learnerActions = readFileSync(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const routeMap = readFileSync(new URL("../src/app/app/journey-map.tsx", import.meta.url), "utf8");
const globalError = readFileSync(new URL("../src/app/error.tsx", import.meta.url), "utf8");
const joinPage = readFileSync(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const homePage = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");





test("route nodes expose their shared-coordinate anchor for geometry checks", () => {
  assert.match(routeMap, /className="route-node-anchor"/);
  assert.match(routeMap, /data-route-index=\{index\}/);
  assert.match(routeMap, /transform=\{`translate\(\$\{x\} \$\{y\}\)`\}/);
  assert.doesNotMatch(routeMap, /route-node-link/);
  assert.match(routeMap, /className="route-node-orb"/);
});



test("mobile task titles balance deliberate lines instead of leaving an orphan glyph", () => {
  assert.match(styles, /\.task-hero-card h1 \{[^}]*line-break: strict[^}]*text-wrap: balance/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.task-hero-card h1 \{[^}]*max-width: 100%[^}]*font-size: clamp\(32px, 9vw, 40px\)[^}]*line-height: 1\.08/);
});
