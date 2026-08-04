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
const admission = await readFile(
  new URL("../src/app/ops/formal-admission-panel.tsx", import.meta.url),
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

test("operator previews the advisory score before making the final admission decision", () => {
  assert.match(admission, /previewFormalAdmission/);
  assert.match(admission, /createFormalAdmission/);
  assert.match(admission, /系统建议.*仅供人工参考/);
  assert.match(admission, /该不可变准入结论由我本人作出并承担责任/);
});
