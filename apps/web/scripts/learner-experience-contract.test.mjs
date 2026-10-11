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
const joinPage = await readFile(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const resultPage = await readFile(
  new URL("../src/app/app/result/page.tsx", import.meta.url),
  "utf8",
);
const homePage = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
const learnerLayout = await readFile(
  new URL("../src/app/app/layout.tsx", import.meta.url),
  "utf8",
);
const learnerHome = await readFile(
  new URL("../src/app/app/page.tsx", import.meta.url),
  "utf8",
);
const journeyMap = await readFile(
  new URL("../src/app/app/journey-map.tsx", import.meta.url),
  "utf8",
);
const explorationCampDashboard = await readFile(
  new URL("../src/app/app/exploration-camp-dashboard.tsx", import.meta.url),
  "utf8",
);
const stageTitle = await readFile(
  new URL("../src/app/app/stage-title.ts", import.meta.url),
  "utf8",
);
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");









test("Day 1 requires a fresh AI self-check without using the score as a threshold", () => {
  assert.match(explorationCampDashboard, /stage_kind === "DAY_0"/);
  assert.match(explorationCampDashboard, /enableDayOneAiSelfCheck=\{enableDayOneAiSelfCheck\}/);
  assert.match(submissionComposer, /第二份材料《\{aiReferenceMaterialTitle\}》/);
  assert.match(submissionComposer, /本次自查得分/);
  assert.match(submissionComposer, /改进建议/);
  assert.doesNotMatch(submissionComposer, /界面预览/);
  assert.doesNotMatch(submissionComposer, /不设置通过线，也不影响任务提交和下一站解锁/);
  const checkHandler = submissionComposer.match(/function runDayOneAiSelfCheck\(\) \{([\s\S]*?)\n  \}/)?.[1];
  assert.ok(checkHandler);
  assert.doesNotMatch(checkHandler, /submitAssignment|submitAction|requestSubmit/);
  assert.match(submissionComposer, /dayOneAiSelfCheckResult\?\.checkedBody !== body/);
  assert.match(submissionComposer, /请先完成一次 AI 自查，再提交本次答案/);
  assert.doesNotMatch(submissionComposer, /score\s*[<>]=?\s*80/);
});

test("Day 1 review supports immutable answer versions and continuing improvement", () => {
  assert.match(explorationCampDashboard, /allowed_commands\.includes\("start_evidence_revision"\)/);
  assert.match(explorationCampDashboard, /继续完善答案/);
  assert.match(explorationCampDashboard, /name="destination" value="evidence"/);
  assert.match(explorationCampDashboard, /查看历史版本/);
  assert.match(explorationCampDashboard, /提交新的答案版本/);
  assert.match(styles, /\.journey-version-history/);
});

test("default learner copy does not repeat input or completion instructions", () => {
  assert.doesNotMatch(taskPage, /先完成输入/);
  assert.doesNotMatch(taskPage, /完成当前材料后，小任务会自动出现/);
  assert.doesNotMatch(taskPage, /完成本阶段/);
});


test("the map and result share the published Journey stage titles", () => {
  assert.match(journeyMap, /import \{ stageDisplayTitle, stageUserFacingTitle \} from "\.\/stage-title"/);
  assert.match(journeyMap, /stageDisplayTitle\(node\.title\)/);
  assert.match(journeyMap, /stageUserFacingTitle\(current\.title\)/);
  assert.doesNotMatch(journeyMap, /const ROUTE_LABELS/);
  assert.doesNotMatch(journeyMap, /AI 与模型/);
  assert.match(resultPage, /stageDisplayTitle\(node\.title\)/);
  assert.match(resultPage, /stageDisplayTitle\(evaluation\.stage_title\)/);
});
