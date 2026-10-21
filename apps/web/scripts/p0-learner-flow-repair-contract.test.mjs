// Active learner UI coverage: project9-render.test.mjs.
// Superseded page-layout contracts are listed in docs/releases/2026-10-11-exploration-test.md.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const taskPage = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url),
  "utf8",
);
const submissionComposer = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url),
  "utf8",
);
const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const feishuUrl = await readFile(new URL("../src/lib/feishu-url.ts", import.meta.url), "utf8");
const learnerHome = await readFile(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const liveStatusSignal = await readFile(
  new URL("../src/app/live-status-signal.tsx", import.meta.url),
  "utf8",
);
const contentDraftForm = await readFile(
  new URL("../src/app/content/content-draft-form.tsx", import.meta.url),
  "utf8",
);
const journeyMap = await readFile(
  new URL("../src/app/app/journey-map.tsx", import.meta.url),
  "utf8",
);
const resultPage = await readFile(new URL("../src/app/app/result/page.tsx", import.meta.url), "utf8");
const opsPage = await readFile(new URL("../src/app/ops/page.tsx", import.meta.url), "utf8");
const reviewDetail = await readFile(
  new URL("../src/app/review/[reviewId]/page.tsx", import.meta.url),
  "utf8",
);
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");







test("learner primary actions have one unmistakable visual treatment", () => {
  assert.match(styles, /\.learner-journey-page \.button\.primary/);
  assert.match(styles, /\.learner-task-page \.button\.primary/);
  assert.match(styles, /linear-gradient\(135deg, #2854d7, #173eaf\)/);
});



test("route map remains orientation-only while the current task card owns navigation", () => {
  assert.match(journeyMap, /href=\{`\/app\/tasks\/\$\{node\.assignment_id\}`\}/);
  assert.doesNotMatch(journeyMap, /route-node-link/);
});





test("draft saving always gives a visible result and remains manually actionable", () => {
  assert.match(submissionComposer, /有修改尚未保存/);
  assert.match(submissionComposer, /正在保存草稿……/);
  assert.match(submissionComposer, /草稿保存成功/);
  assert.match(submissionComposer, /当前内容已经保存/);
  assert.match(submissionComposer, /保存失败，修改仍保留在本机/);
  assert.doesNotMatch(submissionComposer, /disabled=\{submitPending \|\| draftPending \|\| !isOnline \|\| currentSnapshot === savedSnapshot\}/);
});
