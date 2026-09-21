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
const resultPage = await readFile(new URL("../src/app/app/result/page.tsx", import.meta.url), "utf8");
const opsPage = await readFile(new URL("../src/app/ops/page.tsx", import.meta.url), "utf8");
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
  assert.match(
    submissionComposer,
    /const isRevision = \["submit_revision", "submit_evidence_revision"\]\.includes\(command\)/,
  );
  assert.match(submissionComposer, /isRevision && initial\.evidenceUrl/);
  assert.match(submissionComposer, /打开我上次提交的文档/);
  assert.match(submissionComposer, /上次提交已经为你载入/);
  assert.match(submissionComposer, /只改需要调整的部分，不必从头重做/);
});

test("a passed revision replaces the old revision callout with the final outcome", () => {
  assert.match(taskPage, /latestReviewPassed = stageComplete && latestVersion\?\.decision === "PASS"/);
  assert.match(taskPage, /latestPassFeedback = latestReviewPassed \? latestVersion\.feedback : null/);
  assert.match(taskPage, /stageComplete \? "路标已点亮" : needsRevision \? "Reviewer 已回应"/);
  assert.match(taskPage, /stageComplete[\s\S]*"这一站，已经完成"/);
  assert.match(taskPage, /className="feedback-callout completion-feedback stage-completion-hero"/);
  assert.match(taskPage, /你的判断已经被确认/);
  assert.match(taskPage, /needsRevision && assignment\.latest_revision_feedback/);
  assert.match(taskPage, /回到旅程地图/);
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

test("material transitions preserve context while submissions show completion first", () => {
  assert.match(actions, /redirect\(`\/app\/tasks\/\$\{assignmentId\}#task-workspace`\)/);
  assert.match(actions, /#\$\{anchor\}/);
  assert.match(actions, /success: "本阶段已提交，正在等待审核。"/);
  assert.doesNotMatch(actions, /redirect\("\/app\?transition=submitted"\)/);
  assert.match(styles, /\.skip-link\s*\{[^}]*left: -10000px/);
  assert.match(styles, /\.skip-link:focus-visible\s*\{[^}]*left: 8px/);
  assert.doesNotMatch(styles, /\.skip-link:focus\s*\{/);
  assert.match(learnerHome, /className="journey-transition"/);
  assert.match(learnerHome, /下一站已解锁/);
  assert.match(learnerHome, /已经交给 Reviewer/);
  assert.match(learnerHome, /八个路标都已点亮/);
  assert.match(learnerHome, /打开旅程收获，看看你带走了什么/);
  assert.match(learnerHome, /className="button transition-action"/);
});

test("route map remains orientation-only while the current task card owns navigation", () => {
  assert.match(journeyMap, /href=\{`\/app\/tasks\/\$\{node\.assignment_id\}`\}/);
  assert.doesNotMatch(journeyMap, /route-node-link/);
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

test("completed evidence stations can be retested without mixing in reviewer revision", () => {
  assert.match(taskPage, /allowed_commands\.includes\("start_evidence_revision"\)/);
  assert.match(taskPage, /allowed_commands\.includes\("cancel_evidence_revision"\)/);
  assert.match(taskPage, /修改并重新测试/);
  assert.match(taskPage, /正在重新测试，原版本不会被覆盖/);
  assert.match(taskPage, /本次提交将生成 Version/);
  assert.match(taskPage, /取消重新测试/);
  assert.match(actions, /evidence-revision\/start/);
  assert.match(actions, /evidence-revision\/cancel/);
  assert.match(actions, /submission_command/);
  assert.match(actions, /submitted=retest&version=\$\{result\.version_no\}#retest-success/);
  assert.match(submissionComposer, /command === "submit_evidence_revision"/);
  assert.match(submissionComposer, /检查并重新提交/);
  assert.match(taskPage, /重新提交成功，Version \{submittedVersionNo\} 已保存/);
  assert.match(taskPage, /open=\{validRetestReceipt\}/);
  assert.match(resultPage, /result\.active_evidence_retest/);
  assert.match(resultPage, /当前结果基于上一次完整完成记录/);
  assert.match(resultPage, /本次自证重测不会改写正式评测结论/);
  assert.match(opsPage, /enrollment\.evidence_retest_in_progress/);
  assert.match(opsPage, /结营后重测中/);
  assert.match(opsPage, /本轮结束前暂停 Enrollment 运营命令/);
});

test("the current-mission card occupies normal space immediately before the three-step path", () => {
  const governanceIndex = taskPage.indexOf('className="task-governance"');
  const missionIndex = taskPage.indexOf('className="mission-now"');
  const flowIndex = taskPage.indexOf('className="task-flow"');
  assert.ok(governanceIndex >= 0 && governanceIndex < missionIndex);
  assert.ok(missionIndex < flowIndex);
  assert.doesNotMatch(styles, /\.mission-now\s*\{[^}]*margin:\s*-\d/);
  assert.doesNotMatch(styles, /\.mission-now\s*\{[^}]*z-index/);
});

test("draft saving always gives a visible result and remains manually actionable", () => {
  assert.match(submissionComposer, /有修改尚未保存/);
  assert.match(submissionComposer, /正在保存草稿……/);
  assert.match(submissionComposer, /草稿保存成功/);
  assert.match(submissionComposer, /当前内容已经保存/);
  assert.match(submissionComposer, /保存失败，修改仍保留在本机/);
  assert.doesNotMatch(submissionComposer, /disabled=\{submitPending \|\| draftPending \|\| !isOnline \|\| currentSnapshot === savedSnapshot\}/);
});

test("formal model-judgement materials ask concrete questions that match the task", () => {
  assert.match(taskPage, /if \(stageKey === "ASM-002-MODEL-JUDGEMENT"\)/);
  assert.match(taskPage, /看起来合理、但仍必须核对证据才能下结论的回答信号/);
  assert.match(taskPage, /先给出可以或不可以，再用一条具体证据说明理由/);
  assert.doesNotMatch(taskPage, /找出支持你选择 A 或 B 的关键证据/);
});

test("completed stations become achievement views instead of stale action prompts", () => {
  assert.match(taskPage, /stageComplete \? "回看这一站"/);
  assert.match(taskPage, /stageComplete \? completedTaskBriefHeading/);
  assert.match(taskPage, /isTreasure && materialsReady && !stageComplete/);
  assert.match(taskPage, /stageComplete \? "路标已点亮"/);
  assert.match(taskPage, /这枚宝藏已经收入旅程/);
  assert.match(taskPage, /回到旅程地图/);
  assert.ok(
    taskPage.indexOf('className="feedback-callout completion-feedback stage-completion-hero"')
      < taskPage.indexOf('className="task-flow"'),
    "completed-stage payoff must appear before historical materials and task details",
  );
  assert.match(styles, /\.stage-completion-hero \{/);
});

test("long materials lead with a bounded exploration time without hiding source length", () => {
  assert.match(taskPage, /function explorationMinutes/);
  assert.match(taskPage, /本轮建议 \{explorationMinutes/);
  assert.match(taskPage, /原材料约 \$\{material\.estimated_duration_minutes\} min/);
  assert.doesNotMatch(taskPage, /原材料约 \{material\.estimated_duration_minutes\} min · 这一轮只找 1 条线索/);
});
