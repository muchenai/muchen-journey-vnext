import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const modulesSource = await readFile(new URL("../src/lib/journey-program.ts", import.meta.url), "utf8");
const learnerHomeSource = await readFile(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const overviewSource = await readFile(new URL("../src/app/app/program-overview.tsx", import.meta.url), "utf8");
const detailSource = await readFile(new URL("../src/app/app/maps/[mapKey]/page.tsx", import.meta.url), "utf8");
const inviteOrientationSource = await readFile(
  new URL("../src/app/join/private-invite-orientation.tsx", import.meta.url),
  "utf8",
);
const product = JSON.parse(
  await readFile(new URL("../../../config/muchen_journey_product.json", import.meta.url), "utf8"),
);
const controlledRelease = JSON.parse(
  await readFile(
    new URL("../../../config/muchen_journey_2026_09_01_controlled_release.json", import.meta.url),
    "utf8",
  ),
);
const generatedControlledRelease = JSON.parse(
  await readFile(
    new URL("../src/lib/muchen-journey-controlled-release.generated.json", import.meta.url),
    "utf8",
  ),
);

test("the controlled release exposes exactly the four owner-approved modules", () => {
  assert.match(modulesSource, /approved_product_modules\.modules/);
  assert.match(modulesSource, /controlledRelease\.modules/);
  assert.match(overviewSource, /2026-09-01 四模块受控首发/);
  assert.deepEqual(controlledRelease.modules, [
    "exploration-camp",
    "newcomer-village",
    "ai-academy",
    "delivery-guild",
  ]);
  assert.deepEqual(generatedControlledRelease.modules, controlledRelease.modules);
  assert.equal(generatedControlledRelease.full_product_release, false);
  assert.equal(generatedControlledRelease.release_authorized, false);
  assert.doesNotMatch(overviewSource, /五段成长|Career Map/);
});

test("the full product contract remains intact outside the controlled release projection", () => {
  assert.deepEqual(
    product.approved_product_modules.modules.map(({ key }) => key),
    [
      "exploration-camp",
      "newcomer-village",
      "ai-academy",
      "delivery-guild",
      "certification-arena",
      "career-map",
    ],
  );
  assert.equal(product.development_authorization.status, "DIRECT_FULL_MODULE_DEVELOPMENT");
  assert.equal(product.development_authorization.release_authorized, false);
});

test("formal outcomes remain evidence based and human signed", () => {
  assert.match(modulesSource, /实操证据和真人签署/);
  assert.match(modulesSource, /Journey 内不直接执行生产作业/);
  assert.match(modulesSource, /正式能力等级必须有实操证据和真人签署/);
  assert.match(modulesSource, /不能把积分、AI 建议或 Day 1 结果直接转换/);
  assert.match(overviewSource, /AI 建议、积分和自证都不会单独产生人才结论/);
});

test("AI Academy points to the approved formal plan source", () => {
  assert.match(modulesSource, /AI学院主管_2026下半年执行计划_V0\.2/);
});

test("module pages lead with the human question, next action, evidence and gate", () => {
  assert.match(detailSource, /journeyModule.question/);
  assert.match(detailSource, /进入这一站时，只做一件事/);
  assert.match(detailSource, /可复核证据/);
  assert.match(detailSource, /必须经过的真人 Gate/);
  assert.match(detailSource, /系统明确不能做/);
});

test("the current learner action precedes the controlled-module directory", () => {
  const currentActionIndex = learnerHomeSource.indexOf("<JourneyMap");
  const programOverviewIndex = learnerHomeSource.indexOf("<JourneyProgramOverview");

  assert.ok(currentActionIndex >= 0);
  assert.ok(programOverviewIndex > currentActionIndex);
  assert.match(overviewSource, /做完当前一步，再看四个模块/);
});

test("a learner without a journey projection still receives one executable current action", () => {
  assert.match(learnerHomeSource, /\) : opensTask \|\| waitsForReview \|\| opensResult \? \(/);
  assert.match(learnerHomeSource, /href=\{taskHref\}/);
  assert.match(learnerHomeSource, /进入当前任务/);
});

test("module entry reuses existing Enrollment facts and does not create a second task source", () => {
  assert.match(learnerHomeSource, /\/api\/v1\/me\/enrollments/);
  assert.match(learnerHomeSource, /enrollment_id=/);
  assert.match(overviewSource, /LearnerEnrollment/);
  assert.match(overviewSource, /journey_stable_key/);
  assert.match(overviewSource, /进入已分配任务/);
  assert.match(overviewSource, /\/app\?enrollment_id=/);
  assert.doesNotMatch(overviewSource, /create|POST|new Enrollment/);
});

test("public orientation is limited to the four controlled release modules", () => {
  assert.deepEqual(
    product.maps.map(({ key }) => key),
    [
      "exploration-camp",
      "newcomer-village",
      "ai-academy",
      "delivery-guild",
      "certification-arena",
    ],
  );
  assert.match(inviteOrientationSource, /controlledRelease\.modules/);
  assert.match(inviteOrientationSource, /四个受控首发模块/);
  assert.doesNotMatch(inviteOrientationSource, /Career Map|认证竞技场/);
  assert.doesNotMatch(inviteOrientationSource, /BOSS副本/);
});
