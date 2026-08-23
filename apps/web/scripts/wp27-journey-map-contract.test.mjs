import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(
  new URL("../src/app/app/journey-map.tsx", import.meta.url),
  "utf8",
);
const stageTitle = readFileSync(
  new URL("../src/app/app/stage-title.ts", import.meta.url),
  "utf8",
);
const css = readFileSync(
  new URL("../src/app/globals.css", import.meta.url),
  "utf8",
);

test("journey nodes and route line share one coordinate source", () => {
  assert.match(component, /const ROUTE_POINTS =/);
  assert.match(component, /points\.map\(\(point\) => point\.join/);
  assert.match(component, /points\.slice\(0, journey\.nodes\.length\)\.map/);
  assert.match(component, /transform=\{`translate\(\$\{x\} \$\{y\}\)`\}/);
  assert.match(component, /className="route-node-anchor"/);
  assert.match(component, /data-route-index=\{index\}/);
  assert.doesNotMatch(component, /--route-x-/);
  assert.doesNotMatch(component, /style=\{pointStyle\}/);
  assert.doesNotMatch(css, /\.route-node:nth-child\([^)]*\)\s*\{[^}]*translateY/);
});

test("published stages use runtime short labels and progressive disclosure", () => {
  assert.match(component, /import \{ stageDisplayTitle \} from "\.\/stage-title"/);
  assert.match(component, /stageDisplayTitle\(node\.title\)/);
  assert.match(stageTitle, /Day\\s\*0/);
  assert.match(stageTitle, /宝藏\[一二三四\]/);
  assert.match(stageTitle, /\(\?:能力\)\?评测\[一二三\]/);
  assert.doesNotMatch(component, /const ROUTE_LABELS/);
  assert.match(component, /<title>\{hint\}<\/title>/);
  assert.match(component, /className="journey-route-accessible"/);
});

test("strict CSP cannot strip route coordinates", () => {
  assert.doesNotMatch(component, /style=\{/);
  assert.match(component, /viewBox=\{viewBox\}/);
  assert.match(component, /<polyline points=\{points\.map/);
});
