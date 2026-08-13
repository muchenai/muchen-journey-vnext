import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const taskPage = readFileSync(new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url), "utf8");
const learnerHome = readFileSync(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const routeMap = readFileSync(new URL("../src/app/app/journey-map.tsx", import.meta.url), "utf8");
const globalError = readFileSync(new URL("../src/app/error.tsx", import.meta.url), "utf8");
const joinPage = readFileSync(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const homePage = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");

test("task requirements are visible before the gated response workspace", () => {
  assert.match(taskPage, /<section className="task-brief"/);
  assert.doesNotMatch(taskPage, /<details className="task-supporting-rules"/);
  assert.ok(taskPage.indexOf("task-brief") < taskPage.indexOf("task-workspace"));
  assert.match(taskPage, /<h3 id="task-deliverables-title">需要提交<\/h3>/);
  assert.match(taskPage, /<h3>怎么做<\/h3>/);
  assert.match(taskPage, /<h3>完成标准<\/h3>/);
  assert.match(taskPage, /\{materialsReady \? <section className="task-workspace"/);
});

test("learner copy removes repeated locking and stage labels", () => {
  for (const repeatedCopy of ["先完成输入", "完成当前材料后，小任务会自动出现", "完成本阶段"]) {
    assert.doesNotMatch(taskPage, new RegExp(repeatedCopy));
  }
  assert.match(learnerHome, /const primaryActionLabel/);
  assert.doesNotMatch(learnerHome, />进入这一站<\/Link>/);
});

test("route nodes expose their shared-coordinate anchor for geometry checks", () => {
  assert.match(routeMap, /className="route-node-anchor"/);
  assert.match(routeMap, /data-route-index=\{index\}/);
  assert.match(routeMap, /transform=\{`translate\(\$\{x\} \$\{y\}\)`\}/);
});

test("learner failure surfaces provide bounded recovery without raw API JSON", () => {
  assert.match(globalError, />重试<\/button>/);
  assert.match(globalError, /href="\/app">返回我的旅程/);
  assert.match(globalError, /页面参考编号/);
  assert.match(joinPage, /邀请无效、已过期、已撤销或已经使用/);
  assert.match(homePage, /LEARNER_SESSION_EXPIRED/);
  assert.match(homePage, /已提交的任务与评审事实仍然保留/);
  for (const source of [globalError, joinPage, homePage]) {
    assert.doesNotMatch(source, /Authentication required\./);
  }
});
