import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const actions = readFileSync(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const composer = readFileSync(new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url), "utf8");

test("successful submission stays on the task and exposes an accessible receipt", () => {
  assert.match(actions, /revalidatePath\(`\/app\/tasks\/\$\{assignmentId\}`\)/);
  assert.match(actions, /success: "本阶段已提交，正在等待审核。"/);
  assert.doesNotMatch(actions, /redirect\("\/app\?transition=submitted"\)/);
  assert.match(composer, /submitState\.success/);
  assert.match(composer, /role="status" aria-live="polite"/);
});

test("draft feedback distinguishes pending, automatic, manual, and already-saved states", () => {
  assert.match(composer, /有修改尚未保存/);
  assert.match(composer, /正在保存草稿/);
  assert.match(composer, /草稿已保存/);
  assert.match(composer, /草稿保存成功/);
  assert.match(composer, /当前内容已经保存/);
  assert.match(composer, /保存草稿/);
});
