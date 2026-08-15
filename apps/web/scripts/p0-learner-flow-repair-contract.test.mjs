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
const learnerHome = await readFile(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const journeyMap = await readFile(
  new URL("../src/app/app/journey-map.tsx", import.meta.url),
  "utf8",
);
const reviewDetail = await readFile(
  new URL("../src/app/review/[reviewId]/page.tsx", import.meta.url),
  "utf8",
);
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("the station shows a three-step path instead of an undefined quiz", () => {
  assert.match(taskPage, /aria-label="这一站的完成路径"/);
  assert.match(taskPage, /收集线索/);
  assert.match(taskPage, /完成挑战/);
  assert.match(taskPage, /提交后等待真人评审/);
  assert.doesNotMatch(taskPage, /小测|小任务/);
});

test("Feishu-document work has a visible submission entry and novice guidance", () => {
  assert.match(taskPage, /const expectsExternalDocument =/);
  assert.match(taskPage, /const expectsExternalDocument = isAssessment/);
  assert.match(submissionComposer, /id="external-document-title">完成文档，再把链接交给 Reviewer/);
  assert.match(submissionComposer, /在飞书中创建自己的副本/);
  assert.match(submissionComposer, /从浏览器地址栏复制完整链接/);
  assert.match(submissionComposer, /name="evidence_url"/);
  assert.match(actions, /请粘贴 HTTPS 飞书文档链接/);
  assert.match(actions, /hostname\.endsWith\("\.feishu\.cn"\)/);
  assert.match(reviewDetail, /打开 Learner 的飞书文档/);
  assert.match(reviewDetail, /target="_blank" rel="noreferrer"/);
  assert.match(reviewDetail, /if \(!isFeishuHost\) return part/);
});

test("material and submission transitions preserve the learner context", () => {
  assert.match(actions, /redirect\(`\/app\/tasks\/\$\{assignmentId\}#task-workspace`\)/);
  assert.match(actions, /#\$\{anchor\}/);
  assert.match(actions, /\/app\?transition=submitted#next-action/);
  assert.match(learnerHome, /className="journey-transition"/);
  assert.match(learnerHome, /下一站已解锁/);
  assert.match(learnerHome, /已经交给 Reviewer/);
  assert.match(learnerHome, /八个路标都已点亮/);
  assert.match(learnerHome, /打开旅程收获，看看你带走了什么/);
});

test("completed stages remain available for review without unlocking future stages", () => {
  assert.match(journeyMap, /node\.status !== "LOCKED"/);
  assert.match(journeyMap, /href=\{`\/app\/tasks\/\$\{node\.assignment_id\}`\}/);
});

test("long links wrap and the three-step path becomes vertical on mobile", () => {
  assert.match(styles, /\.learning-material-content \.material-body[^}]*overflow-wrap: anywhere/);
  assert.match(styles, /\.material-open-link[^}]*max-width: 100%/);
  assert.match(taskPage, /function ContractLine/);
  assert.match(taskPage, /<ContractLine value=\{item\} \/>/);
  assert.match(styles, /\.contract-line[^}]*overflow-wrap: anywhere/);
  assert.match(styles, /\.task-contract-columns > div[^}]*min-width: 0/);
  assert.match(styles, /\.task-flow ol \{ grid-template-columns: 1fr; \}/);
});

test("the learner sees a single current focus and visible response map", () => {
  assert.match(taskPage, /className="mission-now"/);
  assert.match(taskPage, /现在只做这一步/);
  assert.match(submissionComposer, /<section className="response-map"/);
  assert.doesNotMatch(submissionComposer, /<details className="response-map"/);
});
