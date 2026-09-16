import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const composer = await readFile(new URL("src/app/app/tasks/[assignmentId]/submission-composer.tsx", root), "utf8");
const actions = await readFile(new URL("src/app/actions.ts", root), "utf8");

test("submission feedback stays on the task and exposes success", () => {
  assert.match(actions, /return \{ success:/);
  const submitAction = actions.slice(actions.indexOf("export async function submitAssignment"), actions.indexOf("export async function saveSubmissionDraft"));
  assert.doesNotMatch(submitAction, /redirect\("\/app"\);/);
  assert.match(composer, /submitState\.success/);
  assert.match(composer, /返回旅程地图/);
});

test("draft feedback distinguishes manual saving and saved receipt", () => {
  assert.match(composer, /正在保存草稿到服务器/);
  assert.match(composer, /草稿已保存到服务器/);
  assert.match(composer, /aria-live="polite"/);
});
