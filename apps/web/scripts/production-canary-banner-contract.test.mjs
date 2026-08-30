import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const layout = readFileSync(new URL("../src/app/layout.tsx", import.meta.url), "utf8");

test("production canary banner is bound to the runtime marker", () => {
  assert.match(layout, /process\.env\.RELEASE_MARKER === "PRODUCTION_CANARY_UAT"/);
  assert.match(layout, /生产受控内测/);
  assert.match(layout, /不代表正式发布/);
});
