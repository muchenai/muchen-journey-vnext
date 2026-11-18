import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import React from "react";
import ts from "typescript";

const nativeRequire = createRequire(import.meta.url);
const Form = () => null;
let nextHarnessId = 0;

function compile(file, dependencies) {
  const compiledModule = { exports: {} };
  const compiled = ts.transpileModule(readFileSync(new URL(`../src/app/project29/${file}`, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(compiled, {
    module: compiledModule, exports: compiledModule.exports, URL,
    require: name => name === "./explorationTaskState" ? compile("explorationTaskState.ts", {}) : dependencies[name] || nativeRequire(name),
  });
  return compiledModule.exports;
}

function harness(file, name, initial, dependencies = {}) {
  const slots = [], portals = [], instanceId = ++nextHarnessId;
  let cursor = 0;
  const react = {
    useState(initialValue) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initialValue;
      return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useId() {
      const index = cursor++;
      if (!(index in slots)) slots[index] = `test-${instanceId}-${index}`;
      return slots[index];
    },
  };
  const component = compile(file, {
    react,
    "react-dom": { createPortal(children, container) { portals.push({ children, container }); return { portal: true, children }; } },
    "./VillageTaskForm": { VillageTaskForm: Form },
    ...dependencies,
  })[name];
  const props = { ...initial };
  return {
    portals,
    render(patch = {}) { Object.assign(props, patch); cursor = 0; portals.length = 0; return component(props); },
  };
}

// Portal nodes are deliberately excluded: these helpers inspect only the scrollable body.
function all(node, predicate, found = []) {
  if (Array.isArray(node)) node.forEach(child => all(child, predicate, found));
  else if (React.isValidElement(node)) {
    if (predicate(node)) found.push(node);
    all(node.props.children, predicate, found);
  }
  return found;
}
const buttons = tree => all(tree, node => node.type === "button");
const button = (tree, label) => buttons(tree).find(node => node.props.children === label);
const text = node => Array.isArray(node) ? node.map(text).join("") : React.isValidElement(node) ? text(node.props.children) : typeof node === "string" || typeof node === "number" ? String(node) : "";
const task = {
  id: "learning-one", status: "active", completionMode: "learning", claimed: true,
  answer: "已保存的回答", materials: [{ name: "学习材料", type: "link", url: "https://example.com/learning" }], openedMaterials: [],
};
const footer = { id: "dialog-footer" };
const learningProps = { task, busy: false, hasNext: true, actionsContainer: footer, onComplete: async () => true, onContinue() {} };

test("learning footer contains one completion button while material progress and readiness stay in the body", async () => {
  const completions = [];
  const h = harness("ExplorationLearningActions.tsx", "ExplorationLearningActions", {
    ...learningProps, onComplete: async checkin => { completions.push(checkin); return true; },
  });
  let body = h.render();
  assert.equal(buttons(body).length, 0);
  assert.match(text(body), /材料打开记录|还有 1 份材料尚未打开/);
  assert.equal(h.portals.length, 1);
  assert.equal(h.portals[0].container, footer);
  assert.equal(h.portals[0].children.props.disabled, true);
  h.portals[0].children.props.onClick();
  assert.deepEqual(completions, []);

  body = h.render({ task: { ...task, openedMaterials: [0] } });
  assert.match(text(body), /本板块材料均已打开/);
  assert.equal(h.portals[0].children.props.disabled, false);
  h.portals[0].children.props.onClick();
  assert.deepEqual(completions, [false]);
  h.render();
  assert.equal(h.portals[0].children.props.disabled, true);
  h.portals[0].children.props.onClick();
  assert.deepEqual(completions, [false]);
  await Promise.resolve();
});

test("signout acknowledgement remains in the scrollable body and gates the footer action", () => {
  const completions = [];
  const h = harness("ExplorationLearningActions.tsx", "ExplorationLearningActions", {
    ...learningProps, task: { ...task, completionMode: "checkin" },
    onComplete: async checkin => { completions.push(checkin); return true; },
  });
  let body = h.render();
  const confirmation = all(body, node => node.type === "input" && node.props.type === "checkbox")[0];
  assert.ok(confirmation);
  assert.match(text(body), /我已完成签退，并成功进入项目培训群/);
  assert.equal(all(h.portals[0].children, node => node.type === "input").length, 0);
  assert.equal(h.portals[0].children.props.disabled, true);
  confirmation.props.onChange({ target: { checked: true } });
  body = h.render();
  assert.equal(h.portals[0].children.props.disabled, false);
  h.portals[0].children.props.onClick();
  assert.deepEqual(completions, [true]);
});

test("completed learning keeps its recorded result in the body and portals its original continue action", () => {
  let continuations = 0;
  const h = harness("ExplorationLearningActions.tsx", "ExplorationLearningActions", {
    ...learningProps, task: { ...task, status: "completed" }, hasNext: false, onContinue() { continuations++; },
  });
  const body = h.render();
  assert.match(text(body), /本板块学习已完成.*完成记录已保存/);
  assert.equal(buttons(body).length, 0);
  assert.equal(h.portals[0].children.props.children, "返回任务目录，查看毕业码 →");
  h.portals[0].children.props.onClick();
  assert.equal(continuations, 1);
});

const assessmentProps = {
  task: { ...task, completionMode: "assessment", minimumAnswerLength: 7 }, answer: "待提交的测试结果",
  busy: false, savedMessage: "草稿保存成功", beforeActions: "测试反馈", hasNext: true,
  actionsContainer: footer, onAnswer() {}, onAction: async () => true, onContinue() {},
};
const assessmentHarness = props => harness("ExplorationLearningActions.tsx", "ExplorationAssessmentActions", props, { "./VillageTaskForm": { VillageTaskForm: Form } });

test("an unclaimed assessment portals its single start action and keeps the claim command", () => {
  const commands = [];
  const h = assessmentHarness({
    ...assessmentProps, task: { ...assessmentProps.task, claimed: false },
    onAction: async command => { commands.push(command); return true; },
  });
  const body = h.render();
  assert.match(text(body), /完成测试后，可以填写结果并提交审核/);
  assert.equal(buttons(body).length, 0);
  assert.equal(h.portals.length, 1);
  h.portals[0].children.props.onClick();
  assert.deepEqual(commands, ["claim"]);
});

test("claimed assessments forward the footer and validation limits, and pending/completed continue buttons use it", () => {
  for (const status of ["active", "returned", "pending", "completed"]) {
    let continuations = 0;
    const h = assessmentHarness({ ...assessmentProps, task: { ...assessmentProps.task, status }, onContinue() { continuations++; } });
    const body = h.render();
    const form = all(body, node => node.type === Form)[0];
    assert.equal(form.props.actionsContainer, footer);
    assert.equal(form.props.minLength, 7);
    assert.equal(form.props.beforeActions, "测试反馈");
    assert.equal(form.props.savedMessage, "草稿保存成功");
    assert.equal(form.props.allowCancel, false);
    assert.equal(buttons(body).length, 0);
    assert.equal(h.portals.length, ["pending", "completed"].includes(status) ? 1 : 0);
    if (h.portals.length) {
      assert.match(text(body), status === "pending" ? /测试结果已提交/ : /测试审核已通过/);
      h.portals[0].children.props.onClick();
      assert.equal(continuations, 1);
    }
  }
});

const formProps = { task, answer: task.answer, busy: false, savedMessage: "草稿已保存", beforeActions: "自测反馈", minLength: 7, actionsContainer: footer, onAnswer() {}, onAction: async () => true };

test("exploration manual forms hide cancellation inline and in the footer while retaining save and submit", () => {
  for (const actionsContainer of [undefined, null, footer]) {
    const commands = [];
    const h = harness("VillageTaskForm.tsx", "VillageTaskForm", {
      ...formProps, actionsContainer, allowCancel: false,
      onAction: async command => { commands.push(command); return true; },
    });
    const body = h.render();
    const controls = actionsContainer ? h.portals[0].children : body;
    assert.doesNotMatch(text(body) + text(controls), /取消接取|暂不取消/);
    assert.deepEqual(buttons(controls).map(node => node.props.children), ["保存草稿", "提交审核"]);
    assert.equal(all(body, node => node.type === "textarea")[0].props.disabled, false);
    assert.match(text(body), /自测反馈/);
    button(controls, "保存草稿").props.onClick();
    body.props.onSubmit({ preventDefault() {} });
    assert.deepEqual(commands, ["draft", "submit"]);
  }
});

test("disabling cancellation also removes an existing confirmation without blocking editing", () => {
  const h = harness("VillageTaskForm.tsx", "VillageTaskForm", formProps);
  h.render();
  button(h.portals[0].children, "取消接取").props.onClick();
  h.render();
  assert.match(text(h.portals[0].children), /确认取消接取这个任务/);
  const body = h.render({ allowCancel: false });
  assert.doesNotMatch(text(h.portals[0].children), /取消接取|暂不取消/);
  assert.equal(all(body, node => node.type === "textarea")[0].props.disabled, false);
  assert.equal(button(h.portals[0].children, "保存草稿").props.disabled, false);
  assert.equal(button(h.portals[0].children, "提交审核").props.disabled, false);
  assert.match(text(body), /自测反馈/);
});

test("a portalled form keeps one native submit associated with a stable form and its required answer constraints", () => {
  const commands = [];
  const h = harness("VillageTaskForm.tsx", "VillageTaskForm", { ...formProps, onAction: async command => { commands.push(command); return true; } });
  const body = h.render();
  const formId = body.props.id;
  const textarea = all(body, node => node.type === "textarea")[0];
  assert.ok(formId);
  assert.equal(textarea.props.required, true);
  assert.equal(textarea.props.minLength, 7);
  assert.equal(textarea.props.maxLength, 8000);
  assert.match(text(body), /自测反馈/);
  assert.doesNotMatch(text(body), /草稿已保存/);
  assert.equal(buttons(body).length, 0);
  assert.equal(h.portals.length, 1);
  const portalled = h.portals[0].children;
  assert.match(text(portalled), /草稿已保存/);
  const submitButtons = buttons(portalled).filter(node => node.props.type === "submit");
  assert.equal(submitButtons.length, 1);
  assert.equal(submitButtons[0].props.form, formId);
  assert.equal(submitButtons[0].props.onClick, undefined);
  assert.equal(button(portalled, "保存草稿").props.type, "button");
  assert.equal(button(portalled, "取消接取").props.type, "button");
  button(portalled, "保存草稿").props.onClick();
  assert.deepEqual(commands, ["draft"]);
  let prevented = false;
  body.props.onSubmit({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.deepEqual(commands, ["draft", "submit"]);
  assert.equal(h.render({ answer: "修改后的回答" }).props.id, formId);
  assert.notEqual(harness("VillageTaskForm.tsx", "VillageTaskForm", formProps).render().props.id, formId);
});

test("cancel confirmation and feedback move together while cancellation continues blocking draft and submit", () => {
  const commands = [];
  const h = harness("VillageTaskForm.tsx", "VillageTaskForm", {
    ...formProps, answer: "尚未保存的修改", onAction: async command => { commands.push(command); return true; },
  });
  h.render();
  button(h.portals[0].children, "取消接取").props.onClick();
  let body = h.render(), controls = h.portals[0].children;
  assert.match(text(controls), /确认取消接取这个任务.*取消接取不会自动保存这些修改/);
  assert.doesNotMatch(text(body), /确认取消接取这个任务|自测反馈/);
  assert.equal(all(body, node => node.type === "textarea")[0].props.disabled, true);
  assert.equal(button(controls, "保存草稿").props.disabled, true);
  assert.equal(button(controls, "提交审核").props.disabled, true);
  button(controls, "保存草稿").props.onClick();
  body.props.onSubmit({ preventDefault() {} });
  assert.deepEqual(commands, []);
  button(controls, "确认取消接取").props.onClick();
  assert.deepEqual(commands, ["cancel"]);
  body = h.render({ busy: true });
  controls = h.portals[0].children;
  assert.equal(button(controls, "正在取消…").props.disabled, true);
  button(controls, "正在取消…").props.onClick();
  body.props.onSubmit({ preventDefault() {} });
  assert.deepEqual(commands, ["cancel"]);
  button(controls, "暂不取消").props.onClick();
  h.render({ busy: false, task: { ...task, status: "returned" } });
  assert.equal(button(h.portals[0].children, "确认取消接取"), undefined);
  assert.equal(button(h.portals[0].children, "取消接取"), undefined);
  assert.ok(button(h.portals[0].children, "重新提交审核"));
});

test("busy and read-only portalled forms preserve submission guards", () => {
  for (const patch of [{ busy: true }, ...["pending", "completed", "available", "unavailable"].map(status => ({ task: { ...task, status } }))]) {
    const commands = [];
    const h = harness("VillageTaskForm.tsx", "VillageTaskForm", { ...formProps, ...patch, onAction: async command => { commands.push(command); return true; } });
    const body = h.render();
    const submit = buttons(h.portals[0].children).find(node => node.props.type === "submit");
    assert.equal(submit.props.disabled, true);
    body.props.onSubmit({ preventDefault() {} });
    assert.deepEqual(commands, []);
  }
});

test("absent and null footer containers keep ordinary novice forms and exploration actions inline", () => {
  for (const actionsContainer of [undefined, null]) {
    const learning = harness("ExplorationLearningActions.tsx", "ExplorationLearningActions", { ...learningProps, actionsContainer });
    assert.equal(buttons(learning.render()).length, 1);
    assert.equal(learning.portals.length, 0);
    const assessment = assessmentHarness({ ...assessmentProps, actionsContainer, task: { ...assessmentProps.task, claimed: false } });
    assert.equal(buttons(assessment.render()).length, 1);
    assert.equal(assessment.portals.length, 0);
    const form = harness("VillageTaskForm.tsx", "VillageTaskForm", { ...formProps, actionsContainer });
    const body = form.render();
    assert.deepEqual(buttons(body).map(node => node.props.children), ["取消接取", "保存草稿", "提交审核"]);
    assert.equal(button(body, "提交审核").props.form, undefined);
    assert.match(text(body), /自测反馈.*草稿已保存/);
    assert.equal(form.portals.length, 0);
  }
});
