import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("../src/app/app/journey-map.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("../src/app/globals.css", import.meta.url),
  "utf8",
);
const learnerHome = readFileSync(
  new URL("../src/app/app/page.tsx", import.meta.url),
  "utf8",
);

test("journey nodes and route line share one coordinate source", () => {
  assert.match(component, /const ROUTE_POINTS =/);
  assert.match(component, /points\.map\(\(point\) => point\.join/);
  assert.match(component, /points\.slice\(0, journey\.nodes\.length\)\.map/);
  assert.match(component, /transform=\{`translate\(\$\{x\} \$\{y\}\)`\}/);
  assert.doesNotMatch(component, /--route-x-/);
  assert.doesNotMatch(component, /style=\{pointStyle\}/);
  assert.doesNotMatch(css, /\.route-node:nth-child\([^)]*\)\s*\{[^}]*translateY/);
});

test("the route is orientation-only and leaves one primary current-stage entry", () => {
  assert.doesNotMatch(component, /href=\{`\/app\/tasks/);
  assert.doesNotMatch(component, /route-node-link/);
  assert.match(learnerHome, /打开第一份必读材料/);
  assert.match(learnerHome, /#first-learning-input/);
});

test("all eight formal stages have short route labels and progressive disclosure", () => {
  for (const stableKey of [
    "DAY-0",
    "TRE-001-COMPANY-VALUES",
    "TRE-002-AI-DATA-BASICS",
    "TRE-003-PROJECT-AWARENESS",
    "TRE-004-DELIVERY-FIT",
    "ASM-001-RULE-BREAKDOWN",
    "ASM-002-MODEL-JUDGEMENT",
    "ASM-003-DATA-CONSTRUCTION",
  ]) {
    assert.match(component, new RegExp(`"${stableKey}"`));
  }
  assert.match(component, /<title>\{hint\}<\/title>/);
  assert.match(component, /className="journey-route-accessible"/);
});

test("strict CSP cannot strip route coordinates", () => {
  assert.doesNotMatch(component, /style=\{/);
  assert.match(component, /viewBox=\{viewBox\}/);
  assert.match(component, /<polyline points=\{points\.map/);
});
