import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const actionsSource = readFileSync(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const panelSource = readFileSync(
  new URL("../src/app/ops/identity-access-panel.tsx", import.meta.url),
  "utf8",
);

test("revoked identity transfer requires ownership confirmation and remains locked", () => {
  assert.match(actionsSource, /ownership_confirmed/);
  assert.match(actionsSource, /transfer-revoked/);
  assert.match(actionsSource, /target_role: "CONTENT_EDITOR"/);
  assert.match(panelSource, /迁移后身份仍保持撤销/);
  assert.match(panelSource, /有效会话 0/);
  assert.match(panelSource, /迁移身份（保持撤销）/);
});
