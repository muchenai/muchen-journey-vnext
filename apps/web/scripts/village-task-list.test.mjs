import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const cache = new Map();
function load(name) {
  if (cache.has(name)) return cache.get(name);
  const source = ts.transpileModule(readFileSync(new URL(`../src/app/project29/${name}.ts`, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports, require: dependency => load(dependency.replace(/^\.\//, "")) });
  cache.set(name, compiledModule.exports);
  return compiledModule.exports;
}

const { filterVillageTaskStatus, sortVillageTasks, villageTaskStatusOptions } = load("villageTaskList");
const { filterDepartmentTasks } = load("taskDepartments");
const ids = tasks => Array.from(tasks, task => task.id);
const task = (id, status, minutes = 20, experience = 50, extra = {}) => ({
  id, status, minutes, experience, title: `验证任务 ${id}`, description: "真实任务说明", category: "数据交付",
  publishingDepartment: "多语种数据交付线", level: "入门", review: "导师评审",
  rewardAllocations: [{ id: "data", points: 10 }], ...extra,
});

test("task status choices have the requested labels and filter each status exactly", () => {
  assert.deepEqual(Array.from(villageTaskStatusOptions, ({ value, label }) => [value, label]), [
    ["all", "全部状态"], ["active", "进行中"], ["pending", "待审核"], ["returned", "待修改"], ["completed", "已完成"],
  ]);
  const tasks = Object.freeze(["available", "active", "pending", "returned", "completed", "unavailable"]
    .map(status => Object.freeze(task(status, status))));
  const all = filterVillageTaskStatus(tasks, "all");
  assert.deepEqual(ids(all), ids(tasks));
  assert.notEqual(all, tasks);
  for (const status of ["active", "pending", "returned", "completed"]) {
    const filtered = filterVillageTaskStatus(tasks, status);
    assert.deepEqual(ids(filtered), [status]);
    assert.equal(filtered[0], tasks.find(row => row.status === status));
  }
  assert.deepEqual(ids(filterVillageTaskStatus([], "active")), []);
});

const mixedTasks = () => [
  task("completed-fast", "completed", 1, 999),
  task("active-slow", "active", 80, 800),
  task("available-slow", "available", 50, 300),
  task("pending-fast", "pending", 5, 500),
  task("available-fast", "available", 5, 100),
  task("returned-fast", "returned", 5, 500),
  task("completed-slow", "completed", 70, 2000),
  task("unavailable-fast", "unavailable", 3, 1000),
  task("available-tie", "available", 5, 100),
  task("active-tie", "active", 5, 500),
];

test("recommended order puts available first and completed last while preserving each group's source order", () => {
  const tasks = Object.freeze(mixedTasks().map(Object.freeze));
  const original = ids(tasks);
  const expected = ["available-slow", "available-fast", "available-tie", "active-slow", "pending-fast",
    "returned-fast", "unavailable-fast", "active-tie", "completed-fast", "completed-slow"];
  for (const sort of ["recommended", "unknown"]) {
    const sorted = sortVillageTasks(tasks, sort);
    assert.deepEqual(ids(sorted), expected);
    assert.notEqual(sorted, tasks);
    assert.deepEqual(ids(tasks), original);
    assert.ok(sorted.every(row => tasks.includes(row)), "Sorting must retain task objects");
  }
  assert.deepEqual(ids(sortVillageTasks([], "recommended")), []);
});

test("duration sorts within status groups and preserves ties without mutating the input", () => {
  const tasks = Object.freeze(mixedTasks().map(Object.freeze));
  const original = ids(tasks);
  assert.deepEqual(ids(sortVillageTasks(tasks, "duration")), [
    "available-fast", "available-tie", "available-slow", "unavailable-fast", "pending-fast",
    "returned-fast", "active-tie", "active-slow", "completed-fast", "completed-slow",
  ]);
  assert.deepEqual(ids(tasks), original);
});

test("reward sorts experience descending within status groups and preserves equal rewards", () => {
  const tasks = Object.freeze(mixedTasks().map(Object.freeze));
  const original = ids(tasks);
  assert.deepEqual(ids(sortVillageTasks(tasks, "reward")), [
    "available-slow", "available-fast", "available-tie", "unavailable-fast", "active-slow",
    "pending-fast", "returned-fast", "active-tie", "completed-slow", "completed-fast",
  ]);
  assert.deepEqual(ids(tasks), original);
});

test("a cancelled task returned as available moves ahead of unfinished and completed tasks", () => {
  const tasks = [task("cancelled", "active", 90, 1), task("pending", "pending", 1, 999), task("finished", "completed", 1, 999)];
  const updated = tasks.map(row => row.id === "cancelled" ? { ...row, status: "available", claimed: false } : row);
  for (const sort of ["recommended", "duration", "reward"]) {
    assert.deepEqual(ids(sortVillageTasks(updated, sort)), ["cancelled", "pending", "finished"]);
  }
  assert.deepEqual(ids(filterVillageTaskStatus(updated, "active")), []);
  assert.deepEqual(ids(filterVillageTaskStatus(updated, "all")), ["cancelled", "pending", "finished"]);
  assert.equal(tasks[0].status, "active");
  const withdrawn = updated.map(row => row.id === "cancelled" ? { ...row, status: "unavailable" } : row);
  assert.deepEqual(ids(sortVillageTasks(withdrawn, "duration")), ["pending", "cancelled", "finished"]);
});

test("status filters compose with publishing department, level, review, search and badge filters", () => {
  const tasks = [
    task("matching", "pending", 30),
    task("wrong-status", "active", 10),
    task("wrong-department", "pending", 10, 50, { publishingDepartment: "开发部" }),
    task("wrong-level", "pending", 10, 50, { level: "进阶" }),
    task("wrong-review", "pending", 10, 50, { review: "自动评测" }),
    task("wrong-query", "pending", 10, 50, { title: "另一个任务" }),
    task("wrong-badge", "pending", 10, 50, { rewardAllocations: [{ id: "tech", points: 10 }] }),
  ];
  const byDepartment = rows => filterDepartmentTasks(rows, "multilingual", "入门", "导师评审", "验证", "数据交付");
  const statusFirst = byDepartment(filterVillageTaskStatus(tasks, "pending"));
  const departmentFirst = filterVillageTaskStatus(byDepartment(tasks), "pending");
  assert.deepEqual(ids(statusFirst), ["matching"]);
  assert.deepEqual(ids(departmentFirst), ["matching"]);
  assert.deepEqual(ids(sortVillageTasks(statusFirst, "duration")), ["matching"]);
  assert.deepEqual(ids(filterVillageTaskStatus(byDepartment(tasks), "completed")), []);
  assert.deepEqual(ids(filterVillageTaskStatus(filterDepartmentTasks(tasks, "functional"), "pending")), ["wrong-department"]);
});

function loadTaskClassifications() {
  const compiledModule = { exports: {} };
  const nativeRequire = createRequire(import.meta.url);
  const source = ts.transpileModule(readFileSync(new URL("../src/app/project29/TaskClassifications.tsx", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const dependencies = {
    "./taskClassifications.css": {},
    "./ModuleShell": { ModulePanel: ({ children, className }) => React.createElement("section", { className }, children) },
    "./taskDepartments": load("taskDepartments"),
    "./villageTaskList": load("villageTaskList"),
  };
  vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports,
    require: name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name),
  });
  return compiledModule.exports.TaskClassifications;
}
const TaskClassifications = loadTaskClassifications();
const classificationProps = () => ({
  tasks: [task("active", "active"), task("pending", "pending"), task("returned", "returned")],
  department: "all", level: "全部", review: "全部", badgeType: "全部",
  onDepartment() {}, onLevel() {}, onReview() {}, onBadgeType() {}, onReset() {},
});
function findElement(tree, predicate) {
  if (Array.isArray(tree)) return tree.map(node => findElement(node, predicate)).find(Boolean);
  if (!React.isValidElement(tree)) return undefined;
  return predicate(tree) ? tree : findElement(tree.props.children, predicate);
}

test("my tasks renders the selected status and forwards each option through its actual change handler", () => {
  const changed = [];
  const props = { ...classificationProps(), status: "returned", visibleCount: 2, onStatus: value => changed.push(value) };
  const tree = TaskClassifications(props);
  const select = findElement(tree, node => node.type === "select" && node.props["aria-label"] === "我的任务状态");
  assert.ok(select);
  assert.equal(select.props.value, "returned");
  assert.deepEqual(Array.from(select.props.children, option => [option.props.value, option.props.children]), [
    ["all", "全部状态"], ["active", "进行中"], ["pending", "待审核"], ["returned", "待修改"], ["completed", "已完成"],
  ]);
  for (const value of ["all", "active", "pending", "returned", "completed"]) select.props.onChange({ target: { value } });
  assert.deepEqual(changed, ["all", "active", "pending", "returned", "completed"]);
  const html = renderToStaticMarkup(React.createElement(TaskClassifications, props));
  assert.match(html, /aria-label="我的任务状态"/);
  assert.match(html, /class="task-classification-count" role="status">2 个任务/);
});

test("the hall hides status filtering and task counts use the visible result count including zero", () => {
  const props = { ...classificationProps(), visibleCount: 0, onStatus() {} };
  const tree = TaskClassifications(props);
  assert.equal(findElement(tree, node => node.type === "select" && node.props["aria-label"] === "我的任务状态"), undefined);
  const html = renderToStaticMarkup(React.createElement(TaskClassifications, props));
  assert.doesNotMatch(html, /aria-label="我的任务状态"/);
  assert.match(html, /class="task-classification-count" role="status">0 个任务/);
  const fallback = renderToStaticMarkup(React.createElement(TaskClassifications, classificationProps()));
  assert.match(fallback, /class="task-classification-count" role="status">3 个任务/);
});
