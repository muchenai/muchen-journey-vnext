import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const taskPage = readFileSync(new URL("../src/app/app/tasks/[assignmentId]/page.tsx", import.meta.url), "utf8");
const learnerHome = readFileSync(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const learnerActions = readFileSync(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const routeMap = readFileSync(new URL("../src/app/app/journey-map.tsx", import.meta.url), "utf8");
const globalError = readFileSync(new URL("../src/app/error.tsx", import.meta.url), "utf8");
const joinPage = readFileSync(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const homePage = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("the essential task remains visible while secondary criteria stay on demand", () => {
  assert.match(taskPage, /<section className="task-brief"/);
  assert.doesNotMatch(taskPage, /<details className="task-supporting-rules"/);
  assert.ok(taskPage.indexOf('className="task-brief"') < taskPage.indexOf('id="task-workspace"'));
  assert.match(taskPage, /<h3 id="task-deliverables-title">这一站只交付<\/h3>/);
  assert.match(taskPage, /怎么完成<\/h3>/);
  assert.match(taskPage, /<details className="task-success-criteria">/);
  assert.match(taskPage, /<summary>怎样算完成？<\/summary>/);
  assert.match(taskPage, /\{materialsReady \? <section id="task-workspace" className="task-workspace"/);
});

test("learner copy removes repeated locking and stage labels", () => {
  for (const repeatedCopy of ["先完成输入", "完成当前材料后，小任务会自动出现", "完成本阶段"]) {
    assert.doesNotMatch(taskPage, new RegExp(repeatedCopy));
  }
  assert.match(learnerHome, /const primaryActionLabel/);
  assert.doesNotMatch(learnerHome, />进入这一站<\/Link>/);
});

test("stage completion is seen before the learner chooses the next station", () => {
  assert.match(learnerActions, /redirect\("\/app\?transition=submitted"\)/);
  assert.doesNotMatch(learnerActions, /transition=submitted#next-action/);
  assert.match(learnerHome, /className="button transition-action"/);
  assert.match(learnerHome, /进入下一站/);
  assert.match(learnerHome, /query\.transition === "submitted" && \(opensTask \|\| opensResult\) \? null/);
  assert.match(styles, /\.journey-transition \{[^}]*order: -2/);
  assert.match(styles, /\.journey-transition \.transition-action/);
});

test("Day 0 opens with one achievable action instead of an eighty-minute burden", () => {
  assert.match(taskPage, /const taskTimeLabel = isDayZero\s*\? "先找 1 条线索"/);
  assert.match(taskPage, /const taskTimeAriaLabel = isDayZero\s*\? "当前动作：先找一条线索"/);
  assert.match(taskPage, /aria-label=\{taskTimeAriaLabel\}/);
  assert.match(taskPage, /\{taskTimeLabel\}/);
  assert.doesNotMatch(taskPage, /aria-label=\{`预计 \$\{assignment\.estimated_duration_minutes\} 分钟`\}/);
});

test("route nodes expose their shared-coordinate anchor for geometry checks", () => {
  assert.match(routeMap, /className="route-node-anchor"/);
  assert.match(routeMap, /data-route-index=\{index\}/);
  assert.match(routeMap, /transform=\{`translate\(\$\{x\} \$\{y\}\)`\}/);
  assert.match(routeMap, /<circle className="route-node-hit-area" r=\{isCurrent \? 32 : 28\} \/>/);
  assert.match(styles, /\.route-node-hit-area \{[^}]*fill: transparent[^}]*pointer-events: all/);
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

test("desktop invitation headline stays on one deliberate line", () => {
  assert.match(joinPage, /这张通行证，只属于你。/);
  assert.match(styles, /\.join-entry > h1 \{[^}]*white-space: nowrap/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.join-entry > h1 \{[^}]*font-size: clamp\(24px, 7vw, 31px\)[^}]*white-space: nowrap/);
});

test("mobile task titles balance deliberate lines instead of leaving an orphan glyph", () => {
  assert.match(styles, /\.task-hero-card h1 \{[^}]*line-break: strict[^}]*text-wrap: balance/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.task-hero-card h1 \{[^}]*max-width: 100%[^}]*font-size: clamp\(32px, 9vw, 40px\)[^}]*line-height: 1\.08/);
});
