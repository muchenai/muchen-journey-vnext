import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const learnerHome = await readFile(new URL("../src/app/app/page.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");
const shell = await readFile(new URL("../src/app/human-experience.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("the shared shell exposes the five contract fact labels as text", () => {
  for (const label of ["完成事实", "人工判断", "AI 建议", "积分激励", "系统状态"]) {
    assert.match(shell, new RegExp(label));
  }
  assert.match(shell, /data-fact-kind/);
  assert.match(home, /<FactLegend/);
  assert.match(learnerHome, /<FactLegend/);
});

test("authority lookup failures fail closed instead of guessing an active state", () => {
  assert.match(api, /resolveLearnerSessionState/);
  assert.match(api, /"UNAVAILABLE"/);
  assert.match(home, /state: "unavailable"/);
  assert.match(home, /重试状态读取/);
  assert.match(home, /状态暂时无法确认/);
  assert.doesNotMatch(home, /catch \{\s*return \{ currentMapIndex: PRODUCT_CURRENT_MAP_INDEX, state: "active"/s);
});

test("locked, empty and error surfaces keep one safe recovery action", () => {
  for (const state of ["locked", "empty", "error"]) {
    assert.match(shell, new RegExp(`"${state}"`));
  }
  assert.match(shell, /className="button primary"/);
  assert.match(shell, /href=\{action\.href\}/);
  assert.match(styles, /\.experience-state/);
  assert.match(styles, /\.fact-label/);
});

test("waiting work exposes the submitted version as the single current action", () => {
  assert.match(learnerHome, /WAIT_FOR_REVIEW/);
  assert.match(learnerHome, /查看已提交版本/);
  assert.match(learnerHome, /href: opensTask \|\| waitsForReview \? taskHref/);
});

test("the current task card projects immutable task, assignment, SLA and review facts", () => {
  assert.match(learnerHome, /current-task-card/);
  for (const field of ["任务类型", "预计时间", "截止时间", "审核边界", "首次反馈", "当前状态来源"]) {
    assert.match(learnerHome, new RegExp(field));
  }
  assert.match(learnerHome, /TaskVersion v\{assignment\.task_version\}/);
  assert.match(learnerHome, /Assignment revision \{assignment\.revision\}/);
  assert.match(learnerHome, /未单独配置；不虚构日期/);
  assert.match(learnerHome, /打开当前任务/);
});
