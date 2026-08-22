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
const reviewerQueue = await readFile(
  new URL("../src/app/review/page.tsx", import.meta.url),
  "utf8",
);
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
const reviewDetail = await readFile(
  new URL("../src/app/review/[reviewId]/page.tsx", import.meta.url),
  "utf8",
);
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("the station shows a three-step path instead of an undefined quiz", () => {
  assert.match(taskPage, /aria-label="这一站的完成路径"/);
  assert.match(taskPage, /const learningStepTitle = "学习材料"/);
  assert.match(taskPage, /isAssessment \? "能力评测"/);
  assert.match(taskPage, /: "宝藏小任务"/);
  assert.match(taskPage, /isAssessment \? "主管评审" : "阶段完成"/);
  assert.match(taskPage, /提交后等待真人评审/);
});

test("pending review is never presented as a completed station", () => {
  assert.match(taskPage, /const stageComplete = assignment\.status === "COMPLETED"/);
  assert.match(taskPage, /\["SUBMITTED", "IN_REVIEW"\]\.includes\(assignment\.status\)/);
  assert.match(taskPage, /等待 Reviewer 开始评审/);
  assert.match(taskPage, /Reviewer 正在评审/);
  assert.match(taskPage, /提交成功，正在等待 Reviewer 开始评审/);
  assert.doesNotMatch(
    taskPage,
    /const stageComplete = assignment\.submission !== null && assignment\.allowed_commands\.length === 0/,
  );
});

test("revision gives the learner an immediate route back to their own work", () => {
  assert.match(taskPage, /needsRevision \? \(/);
  assert.match(taskPage, /href="#task-workspace"/);
  assert.match(taskPage, /查看反馈并修改/);
  assert.match(taskPage, /Reviewer 希望你调整这里/);
  assert.match(taskPage, /只改反馈指出的部分/);
  assert.match(submissionComposer, /const isRevision = command === "submit_revision"/);
  assert.match(submissionComposer, /isRevision && initial\.evidenceUrl/);
  assert.match(submissionComposer, /打开我上次提交的文档/);
  assert.match(submissionComposer, /上次提交已经为你载入/);
  assert.match(submissionComposer, /只改需要调整的部分，不必从头重做/);
});

test("a passed revision replaces the old revision callout with the final outcome", () => {
  assert.match(taskPage, /latestReviewPassed = stageComplete && latestVersion\?\.decision === "PASS"/);
  assert.match(taskPage, /latestPassFeedback = latestReviewPassed \? latestVersion\.feedback : null/);
  assert.match(taskPage, /latestReviewPassed \? "Reviewer 已确认" : needsRevision \? "Reviewer 已回应"/);
  assert.match(taskPage, /latestReviewPassed[\s\S]*"这一站，已经完成"/);
  assert.match(taskPage, /className="feedback-callout completion-feedback"/);
  assert.match(taskPage, /你的判断已经被确认/);
  assert.match(taskPage, /needsRevision && assignment\.latest_revision_feedback/);
  assert.match(taskPage, /继续下一站/);
  assert.match(styles, /\.completion-feedback/);
});

test("learner and reviewer status pages refresh while visible and announce changes", () => {
  assert.match(learnerHome, /<LiveStatusSignal/);
  assert.match(learnerHome, /提交成功，已交给主管评审/);
  assert.match(learnerHome, /评分完成，旅程已经更新/);
  assert.match(reviewerQueue, /<LiveStatusSignal/);
  assert.match(reviewerQueue, /有新的提交或评审状态变化/);
  assert.match(liveStatusSignal, /const REFRESH_INTERVAL_MS = 12_000/);
  assert.match(liveStatusSignal, /document\.visibilityState !== "visible"/);
  assert.match(liveStatusSignal, /router\.refresh\(\)/);
  assert.match(liveStatusSignal, /aria-live="polite"/);
});

test("answer references are accepted by the editor but hidden until submission", () => {
  assert.match(contentDraftForm, /name="reference_materials"/);
  assert.match(contentDraftForm, /提交后开放的参考答案/);
  assert.match(actions, /reference_materials: optionalTextLines/);
  assert.match(taskPage, /POST_SUBMISSION_REFERENCE/);
  assert.match(taskPage, /assignment\.submission \? \(/);
  assert.match(taskPage, /参考答案将在提交后开放/);
  assert.match(taskPage, /查看提交后的参考答案/);
});

test("learner primary actions have one unmistakable visual treatment", () => {
  assert.match(styles, /\.learner-journey-page \.button\.primary/);
  assert.match(styles, /\.learner-task-page \.button\.primary/);
  assert.match(styles, /linear-gradient\(135deg, #2854d7, #173eaf\)/);
});

test("Feishu-document work has a visible submission entry and novice guidance", () => {
  assert.match(taskPage, /const expectsExternalDocument =/);
  assert.match(taskPage, /const expectsExternalDocument = isAssessment/);
  assert.match(submissionComposer, /isRevision \? "修改原文档，再提交新版本" : "完成文档，再把链接交给 Reviewer"/);
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
  assert.match(styles, /\.skip-link\s*\{[^}]*left: -10000px/);
  assert.match(styles, /\.skip-link:focus-visible\s*\{[^}]*left: 8px/);
  assert.doesNotMatch(styles, /\.skip-link:focus\s*\{/);
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
  assert.match(styles, /\.response-map ol, \.external-document-path ol, \.revision-path \{ grid-template-columns: 1fr; \}/);
});

test("the learner sees a single current focus and visible response map", () => {
  assert.match(taskPage, /className="mission-now"/);
  assert.match(taskPage, /现在只做这一步/);
  assert.match(taskPage, /className="task-next-unlock"/);
  assert.match(taskPage, /完成材料后解锁/);
  assert.match(taskPage, /materialsReady \? <section className="task-brief"/);
  assert.match(styles, /\.task-next-unlock/);
  assert.match(submissionComposer, /<section className="response-map"/);
  assert.doesNotMatch(submissionComposer, /<details className="response-map"/);
});
