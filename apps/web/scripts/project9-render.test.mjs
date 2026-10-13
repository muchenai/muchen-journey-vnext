import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Compile the real TSX components in memory; no copied component or snapshots.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const nativeRequire = createRequire(import.meta.url);
const cache = new Map();
function load(filename) {
  if (cache.has(filename)) return cache.get(filename).exports;
  const compiled = { exports: {} };
  cache.set(filename, compiled);
  const source = ts.transpileModule(readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    fileName: filename,
  }).outputText;
  const require = (specifier) => {
    if (specifier === "next/navigation") return { useRouter: () => ({ refresh() {} }) };
    if (specifier.endsWith("/actions")) return new Proxy({}, { get: () => () => { throw new Error("Unexpected server mutation during render"); } });
    if (!specifier.startsWith(".") && !specifier.startsWith("@/")) return nativeRequire(specifier);
    const base = specifier.startsWith("@/") ? path.join(root, specifier.slice(2)) : path.resolve(path.dirname(filename), specifier);
    const target = [base, base + ".ts", base + ".tsx"].find(existsSync);
    if (!target) throw new Error("Missing import: " + specifier);
    return load(target);
  };
  vm.runInThisContext("(function(require,module,exports){" + source + "\n})", { filename })(require, compiled, compiled.exports);
  return compiled.exports;
}
const { default: App, Login } = load(path.join(root, "app/project9/App.tsx"));
const { JourneyProvider } = load(path.join(root, "app/project9/journey-context.tsx"));
const { TaskCards, ExecutionDetail, executionTasks } = load(path.join(root, "app/project9/ExecutionPages.tsx"));
const { TaskFeedbackDialog } = load(path.join(root, "app/project9/TaskFeedbackDialog.tsx"));
const experience = (overrides = {}) => ({
  assignmentId: "a1", status: "IN_PROGRESS", revision: 1, taskVersion: 1,
  title: "Day 1", purpose: "学习", shortDescription: "学习", learnerOutcome: "记录",
  referenceMaterials: [], estimatedMinutes: 10, stageKind: "DAY_0", stageKey: "DAY-0", stagePosition: 1,
  currentAssignmentId: "a1", currentStagePosition: 1, allowedCommands: ["submit"], materials: [],
  draftBody: "", completedStages: 0, totalStages: 8, reviewerDisplayName: "审核人",
  latestSubmissionBody: null, latestSubmissionVersion: null, latestSubmissionCreatedAt: null,
  latestFeedback: null, latestFeedbackAt: null, pendingReviewAssignmentId: null,
  activityRecords: [], reviewFeedback: [], journeyTasks: Array.from({ length: 8 }, (_, i) => ({
    assignmentId: "a" + (i + 1), position: i + 1, status: i === 0 ? "CURRENT" : "LOCKED",
    assignmentStatus: i === 0 ? "IN_PROGRESS" : "AVAILABLE", title: executionTasks[i].title, shortDescription: "",
  })), ...overrides,
});
const render = (props = {}) => renderToStaticMarkup(React.createElement(App, { initialScreen: "dashboard", learnerName: "测试同学", experience: experience(), ...props }));
const inside = (element, data = experience()) => renderToStaticMarkup(React.createElement(JourneyProvider, { value: { learnerName: "测试同学", experience: data } }, element));
const renderLogin = (joinError = "") => renderToStaticMarkup(React.createElement(JourneyProvider, {
  value: {
    learnerName: "测试同学", experience: experience(), initialScreen: "login",
    joinPhase: "feishu", joinError, initialNotice: "",
  },
}, React.createElement(Login)));

test("learner entry starts with the real resource loader", () => {
  const html = render({ initialScreen: "login", joinPhase: "feishu" });
  assert.match(html, /项目资源载入进度/);
  assert.match(html, /正在加载项目资源/);
  assert.doesNotMatch(html, /使用飞书登录/);
});

test("Feishu login renders one authorization action without nickname or invite input", () => {
  const html = renderLogin();
  assert.match(html, /使用飞书登录/);
  assert.doesNotMatch(html, /<input/);
  assert.match(renderLogin("授权已过期，请重试"), /授权已过期，请重试/);
});

test("post-login welcome renders on the server without browser globals", () => {
  assert.equal(typeof window, "undefined");
  const html = render({ initialScreen: "welcome" });
  assert.match(html, /欢迎来到/);
  assert.match(html, /开启旅程/);
  assert.match(html, /data-welcome-narrative="true"/);
  assert.match(html, /Muchen Journey是沐晨面向新人和在岗成员建设的学习与实践成长平台/);
});

test("unfinished modules have explicit non-navigation actions; exploration remains available", () => {
  const html = render();
  for (const action of ["novice-village", "ai-academy", "delivery-guild"]) {
    assert.match(html, new RegExp(`<button[^>]+data-action="${action}"`));
  }
  assert.doesNotMatch(html, /href="\/app\/maps\/(newcomer-village|ai-academy|delivery-guild)/);
  assert.match(html, /探索营/);
  assert.match(render({ initialNotice: "该功能正在设计" }), /role="status"[^>]*>该功能正在设计/);
});

test("a new learner sees one accessible task and seven locked tasks", () => {
  const html = inside(React.createElement(TaskCards));
  assert.equal((html.match(/aria-disabled="true"/g) || []).length, 7);
  assert.equal((html.match(/aria-disabled="false"/g) || []).length, 1);
  assert.equal((html.match(/data-action="open-task"/g) || []).length, 8);
});

for (const status of ["SUBMITTED", "IN_REVIEW"]) test(`${status} remains pending while the next task opens`, () => {
  const data = experience();
  data.journeyTasks[0] = { ...data.journeyTasks[0], status: "CURRENT", assignmentStatus: status };
  data.journeyTasks[1] = { ...data.journeyTasks[1], status: "CURRENT", assignmentStatus: "AVAILABLE" };
  const html = inside(React.createElement(TaskCards), data);
  assert.match(html, /待审核/);
  assert.doesNotMatch(html, /已完成/);
  assert.equal((html.match(/aria-disabled="false"/g) || []).length, 2);
});

for (const status of ["COMPLETED", "NEEDS_REVISION"]) test(`${status} can reopen its evidence when the server permits revision`, () => {
  const html = render({ initialScreen: "view", experience: experience({ status, allowedCommands: ["start_evidence_revision"], latestSubmissionBody: "先前提交的证据" }) });
  assert.match(html, /重新修改/);
  assert.match(html, /先前提交的证据/);
  assert.match(html, /<textarea[^>]*readOnly/);
  assert.match(html, /data-action="review-proof"[^>]*|data-action="review-proof"/);
});

test("pending evidence cannot be edited or submitted twice", () => {
  const html = render({ initialScreen: "view", experience: experience({ status: "SUBMITTED", allowedCommands: [], latestSubmissionBody: "已提交证据" }) });
  assert.match(html, /已提交，等待审核/);
  assert.doesNotMatch(html, /data-action="revise-proof"/);
  assert.match(html, /<textarea[^>]*readOnly/);
  const submit = html.match(/<button[^>]*data-action="review-proof"[^>]*>/)?.[0];
  assert.match(submit, /disabled/);
});

test("revising restores the saved draft and exposes cancellation", () => {
  const html = render({ initialScreen: "view", experience: experience({ allowedCommands: ["submit_evidence_revision", "cancel_evidence_revision"], draftBody: "修改中的草稿", latestSubmissionBody: "旧证据" }) });
  assert.match(html, /修改中的草稿/);
  assert.match(html, /data-action="cancel-revision"/);
  assert.doesNotMatch(html, /<textarea[^>]*readOnly/);
});

test("both completed materials retain independent reopen controls", () => {
  const html = inside(React.createElement(ExecutionDetail, { task: executionTasks[1], openedMaterials: [true, true], panelDecoration: null, backDecoration: null }));
  assert.equal((html.match(/已完成/g) || []).length, 2);
  assert.match(html, /重新打开材料 01/);
  assert.match(html, /重新打开材料 02/);
});

test("feedback dialog uses the task title and preserves long reviewer comments", () => {
  const comment = "长评语".repeat(500) + "最后一句";
  const html = renderToStaticMarkup(React.createElement(TaskFeedbackDialog, { title: "评测二/模型判断", onClose() {}, feedback: { records: [{ id: "r1", version: 1, decision: "REVISION_REQUIRED", reviewedAt: "2026-10-11T01:00:00Z", comment, dimensions: [] }] } }));
  assert.match(html, /评测二\/模型判断/);
  assert.match(html, /退回修改/);
  assert.ok(html.includes(comment));
  assert.match(html, /<dialog[^>]*aria-labelledby="task-feedback-title"/);
});
