import assert from "node:assert/strict";
import test from "node:test";
import { readWorkspace, workspaceKey, selfCheckRecovery } from "../src/app/project9/workspace-recovery.ts";

test("draft survives a return/refresh, including an intentionally empty edit", () => {
  const entries = new Map();
  const storage = { getItem: key => entries.get(key) ?? null };
  const key = workspaceKey("learner-assignment-a", 1, 3);
  entries.set(key, JSON.stringify({ body: "https://test.feishu.cn/docx/answer", pendingSince: 1000 }));
  assert.equal(readWorkspace(storage, key).body, "https://test.feishu.cn/docx/answer");
  assert.equal(readWorkspace(storage, workspaceKey("another-assignment", 1, 3)), null);
  assert.equal(readWorkspace(storage, workspaceKey("learner-assignment-a", 1, 4)), null);
  entries.set(key, JSON.stringify({ body: "", pendingSince: null }));
  assert.deepEqual(readWorkspace(storage, key), { body: "", pendingSince: null });
  entries.set(key, "broken JSON");
  assert.equal(readWorkspace(storage, key), null);
});

const row = status => ({ id: "record", body: "url", createdAt: new Date(10_000).toISOString(), status, result: "saved advice", commentId: null });
test("returning while AI runs or comments sync keeps submit blocked, completion releases it", () => {
  assert.equal(selfCheckRecovery([row("RUNNING")], null).busy, true);
  assert.equal(selfCheckRecovery([row("SENDING")], null).busy, true);
  assert.equal(selfCheckRecovery([row("COMPLETED")], null).busy, false);
  assert.equal(selfCheckRecovery([row("FAILED")], null).busy, false);
  assert.equal(selfCheckRecovery([row("UNCERTAIN")], null).busy, false);
});

test("navigation before server claim retains pending state, abandoned markers expire", () => {
  assert.equal(selfCheckRecovery([], 10_000, 12_000).busy, true);
  assert.equal(selfCheckRecovery([row("COMPLETED")], 20_000, 21_000).busy, true);
  assert.equal(selfCheckRecovery([row("COMPLETED")], 10_000, 12_000).busy, false);
  assert.equal(selfCheckRecovery([], 10_000, 41_000).busy, false);
  assert.equal(selfCheckRecovery([], null, 12_000).busy, false);
});
