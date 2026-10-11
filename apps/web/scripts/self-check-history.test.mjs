import test from "node:test";
import assert from "node:assert/strict";
import { readSelfCheckHistory, saveSelfCheck, selfCheckHistoryKey } from "../src/app/project9/self-check-history.ts";

function storage() {
  const data = new Map();
  return { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) };
}
const entry = { id: "first", createdAt: "2026-10-10T04:00:00Z", body: "学习记录测试内容至少十个字符", result: "本地格式自查完成" };

test("history survives reread, newest first, isolated across learner assignments, stages and versions", () => {
  const store = storage();
  const key = selfCheckHistoryKey("learner-a-treasure-2", 1);
  assert.deepEqual(readSelfCheckHistory(store, key), []);
  saveSelfCheck(store, key, entry);
  saveSelfCheck(store, key, { ...entry, id: "second" });
  assert.deepEqual(readSelfCheckHistory(store, key).map(item => item.id), ["second", "first"]);
  for (const other of [selfCheckHistoryKey("learner-a-treasure-3", 1), selfCheckHistoryKey("learner-b-treasure-2", 1), selfCheckHistoryKey("learner-a-treasure-2", 2)]) {
    assert.deepEqual(readSelfCheckHistory(store, other), []);
  }
});

test("corrupt history is reported without overwriting existing data", () => {
  for (const raw of ["bad json", "{}", '[{"id":"broken"}]']) {
    const store = storage();
    store.setItem("key", raw);
    assert.throws(() => saveSelfCheck(store, "key", entry));
    assert.equal(store.getItem("key"), raw);
  }
});

test("storage access and quota failures are not reported as saved", () => {
  const denied = { getItem() { throw new Error("denied"); }, setItem() {} };
  assert.throws(() => readSelfCheckHistory(denied, "key"));
  const full = { getItem() { return null; }, setItem() { throw new Error("quota"); } };
  assert.throws(() => saveSelfCheck(full, "key", entry));
});
