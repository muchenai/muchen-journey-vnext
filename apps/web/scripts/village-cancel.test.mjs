import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const nativeRequire = createRequire(import.meta.url);
function reactHarness() {
  const slots = []; let cursor = 0;
  return {
    react: {
      useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial; return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }]; },
      useRef(initial) { const index = cursor++; if (!(index in slots)) slots[index] = { current: initial }; return slots[index]; },
      useCallback: callback => callback, useEffect() {},
    },
    reset() { cursor = 0; },
  };
}
function compile(file, dependencies, extras = {}) {
  const compiledModule = { exports: {} };
  const source = ts.transpileModule(readFileSync(new URL(`../src/app/project29/${file}`, import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports, require: name => dependencies[name] || nativeRequire(name), ...extras });
  return compiledModule.exports;
}
const task = { id: "task-one", status: "active", answer: "服务器已保存草稿", assignmentId: "assignment-one", versionId: "version-one", revision: 4 };
test("cancelled unpublished tasks leave my tasks while claimed unavailable tasks remain", () => {
  const { isVillageTaskClaimed } = compile("useVillageTasks.ts", { react: {} });
  assert.equal(isVillageTaskClaimed({ status: "unavailable", claimed: false }), false);
  assert.equal(isVillageTaskClaimed({ status: "unavailable", claimed: true }), true);
  assert.equal(isVillageTaskClaimed({ status: "available", claimed: false }), false);
  for (const status of ["active", "returned", "pending", "completed"]) assert.equal(isVillageTaskClaimed({ status }), true);
});
function formHarness(initial = {}) {
  const h = reactHarness(), calls = [];
  const { VillageTaskForm } = compile("VillageTaskForm.tsx", { react: h.react });
  const props = { task, answer: task.answer, busy: false, onAnswer() {}, onAction: async command => { calls.push(command); return true; }, ...initial };
  return { calls, props, render(patch = {}) { Object.assign(props, patch); h.reset(); return VillageTaskForm(props); } };
}
function buttons(node, result = []) {
  if (Array.isArray(node)) node.forEach(item => buttons(item, result));
  else if (React.isValidElement(node)) { if (node.type === "button") result.push(node); buttons(node.props.children, result); }
  return result;
}
const button = (tree, text) => buttons(tree).find(item => item.props.children === text);

test("only active tasks show cancel immediately left of save; returned remains editable without cancellation", () => {
  for (const status of ["active", "returned", "pending", "completed", "available", "unavailable"]) {
    const h = formHarness({ task: { ...task, status } }), tree = h.render();
    assert.equal(!!button(tree, "取消接取"), status === "active");
    if (status === "active") assert.deepEqual(buttons(tree).map(item => item.props.children), ["取消接取", "保存草稿", "提交审核"]);
    if (status === "returned") assert.deepEqual(buttons(tree).map(item => item.props.children), ["保存草稿", "重新提交审核"]);
  }
});

test("cancel uses a second confirmation and warns only about unsaved edits without auto-saving", () => {
  const h = formHarness({ answer: "尚未保存的新内容" });
  button(h.render(), "取消接取").props.onClick();
  assert.deepEqual(h.calls, []);
  let tree = h.render(), html = renderToStaticMarkup(tree);
  assert.match(html, /确认取消接取这个任务/);
  assert.match(html, /已保存的草稿会保留/);
  assert.match(html, /取消接取不会自动保存这些修改/);
  tree.props.onSubmit({ preventDefault() {} });
  assert.deepEqual(h.calls, []);
  button(tree, "暂不取消").props.onClick();
  tree = h.render();
  assert.equal(button(tree, "确认取消接取"), undefined);
  button(tree, "取消接取").props.onClick();
  button(h.render(), "确认取消接取").props.onClick();
  assert.deepEqual(h.calls, ["cancel"]);
  assert.equal(button(formHarness().render(), "确认取消接取"), undefined);
});

test("busy confirmation cannot cancel twice and changing to returned cannot expose confirmation", () => {
  const h = formHarness();
  button(h.render(), "取消接取").props.onClick();
  let tree = h.render({ busy: true });
  const confirm = button(tree, "正在取消…");
  assert.equal(confirm.props.disabled, true);
  confirm.props.onClick();
  assert.deepEqual(h.calls, []);
  tree = h.render({ busy: false, task: { ...task, status: "returned" } });
  assert.equal(button(tree, "确认取消接取"), undefined);
  assert.equal(button(tree, "取消接取"), undefined);
});

function tasksHarness() {
  const h = reactHarness();
  let serverTask = { ...task }, failed = false, deferred = null;
  const posts = [];
  const { useVillageTasks: runVillageTasksHook } = compile("useVillageTasks.ts", { react: h.react }, {
    crypto: { randomUUID: () => "fixed-idempotency-key" },
    fetch: async (url, options) => {
      if (options?.method === "POST") {
        const payload = JSON.parse(options.body); posts.push(payload);
        if (deferred) await deferred;
        if (failed) return { ok: false, json: async () => ({ error: "任务已提交审核，不能取消" }) };
        serverTask = { ...serverTask, status: "available", revision: 5, assignmentId: null };
        return { ok: true, json: async () => serverTask };
      }
      return { ok: true, json: async () => ({ items: [serverTask], wallet: { taskPoints: 10 } }) };
    },
  });
  return { posts, render() { h.reset(); return runVillageTasksHook(true); }, fail() { failed = true; }, change(status) { serverTask = { ...serverTask, status }; }, defer() { let release; deferred = new Promise(resolve => { release = resolve; }); return release; } };
}

test("cancel keeps saved draft, uses the current revision and never sends unsaved edits", async () => {
  const h = tasksHarness(); await h.render().refresh();
  const current = h.render();
  const result = await current.mutate(current.tasks[0], "cancel", "尚未保存的内容");
  assert.equal(result.status, "available");
  assert.equal(h.render().tasks[0].answer, task.answer);
  assert.equal(h.posts[0].command, "cancel");
  assert.equal(h.posts[0].revision, 4);
  assert.equal("answer" in h.posts[0], false);
});

test("hook refuses returned, pending and completed cancellation including a stale active handler", async () => {
  for (const status of ["returned", "pending", "completed", "available"]) {
    const h = tasksHarness(); await h.render().refresh(); const stale = h.render().tasks[0];
    h.change(status); await h.render().refresh(); const current = h.render();
    assert.equal(await current.mutate(current.tasks[0], "cancel", ""), null);
    assert.equal(await current.mutate(stale, "cancel", ""), null);
    assert.equal(h.posts.length, 0);
  }
});

test("a failed cancellation preserves active task and draft, while duplicate clicks stay blocked", async () => {
  const h = tasksHarness(); await h.render().refresh(); h.fail();
  const release = h.defer(), current = h.render();
  const pending = current.mutate(current.tasks[0], "cancel", "");
  assert.equal(await current.mutate(current.tasks[0], "cancel", ""), null);
  release(); assert.equal(await pending, null);
  const latest = h.render();
  assert.equal(latest.tasks[0].status, "active");
  assert.equal(latest.tasks[0].answer, task.answer);
  assert.match(latest.error, /不能取消/);
  assert.equal(h.posts.length, 1);
});
