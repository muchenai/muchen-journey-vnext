import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const taskPage = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url),
  "utf8",
);
const reviewer = await readFile(
  new URL("../src/app/review/[reviewId]/review-workbench.tsx", import.meta.url),
  "utf8",
);
const submissionComposer = await readFile(
  new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url),
  "utf8",
);
const resultPage = await readFile(
  new URL("../src/app/app/result/page.tsx", import.meta.url),
  "utf8",
);
const opsPage = await readFile(
  new URL("../src/app/ops/page.tsx", import.meta.url),
  "utf8",
);
const invitePanel = await readFile(
  new URL("../src/app/ops/invite-management-panel.tsx", import.meta.url),
  "utf8",
);

test("learner receives the V2 learning input before the response composer", () => {
  assert.match(taskPage, /learning_blocks/);
  assert.match(taskPage, /knowledge_checks/);
  assert.match(taskPage, /先探索，再输出/);
  assert.ok(
    taskPage.indexOf("experience.learning_blocks")
      < taskPage.indexOf("<SubmissionComposer"),
  );
});

test("reviewer records bounded numeric evidence alongside the human judgment", () => {
  assert.match(reviewer, /max_points/);
  assert.match(reviewer, /meets_threshold/);
  assert.match(reviewer, /name={`\$\{dimension\.dimension_key\}_score`}/);
});

test("learner and reviewer disclose advisory AI provenance", () => {
  for (const field of ["used", "purpose", "model_version", "prompt_version"]) {
    assert.match(submissionComposer, new RegExp(`learner_ai_${field}`));
    assert.match(reviewer, new RegExp(`reviewer_ai_${field}`));
  }
  assert.match(reviewer, /AI 只提供建议/);
  assert.match(submissionComposer, /AI 输出只是建议/);
});

test("result and operator pages use next-training-stage semantics only", () => {
  assert.match(resultPage, /下一训练阶段决定/);
  assert.match(resultPage, /待授权真人决定/);
  assert.match(resultPage, /申请独立人工复核/);
  assert.match(resultPage, /原决定保持不可变/);
  assert.match(resultPage, /复核谱系/);
  assert.match(resultPage, /未参与原决定的 Reviewer/);
  assert.match(resultPage, /替换决定已作为新版本追加/);
  assert.doesNotMatch(resultPage, /人工准入|自动准入|淘汰|录用/);
  assert.match(opsPage, /下一训练阶段决定尚未启用/);
  assert.doesNotMatch(opsPage, /FormalAdmissionPanel|create_formal_admission/);
  assert.match(invitePanel, /下一训练阶段由另行授权的真人决定/);
  assert.doesNotMatch(invitePanel, /人工准入|自动准入|淘汰|录用/);
});

test("READY handoff requires active authorization and the Person's explicit confirmation", () => {
  assert.match(resultPage, /acceptControlledTaskHandoff/);
  assert.match(resultPage, /本人确认进入受控训练/);
  assert.match(resultPage, /只会原子创建一个新手村 Enrollment 和一个 Assignment/);
  assert.match(resultPage, /不会执行生产作业/);
  assert.match(resultPage, /系统不会自动分配任务/);
  assert.match(resultPage, /Outcome 与 Handoff 保持不可变/);
});
