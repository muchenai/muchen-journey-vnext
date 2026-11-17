import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import React from 'react';
import * as jsxRuntime from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

function hooks() {
  const slots = []; let cursor = 0; let effects = [];
  const same = (a, b) => a && b && a.length === b.length && a.every((item, index) => Object.is(item, b[index]));
  const effectHook = (callback, dependencies) => { const index = cursor++; if (!slots[index] || !same(slots[index].dependencies, dependencies)) { const previous = slots[index]; effects.push(() => { previous?.cleanup?.(); slots[index].cleanup = callback(); }); slots[index] = { dependencies }; } };
  return {
    react: {
      useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial; return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }]; },
      useRef(initial) { return slots[cursor++] ??= { current: initial }; },
      useCallback(callback, dependencies) { const index = cursor++; if (!slots[index] || !same(slots[index].dependencies, dependencies)) slots[index] = { callback, dependencies }; return slots[index].callback; },
      useEffect: effectHook, useLayoutEffect: effectHook,
    },
    render(callback) { cursor = 0; return callback(); },
    commit() { const pending = effects; effects = []; pending.forEach(effect => effect()); },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}
const compiled = new Map();
function load(file, dependencies, globals = {}) {
  const compiledModule = { exports: {} };
  if (!compiled.has(file)) compiled.set(file, ts.transpileModule(readFileSync(new URL(`../src/app/project29/${file}`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText);
  const source = compiled.get(file);
  vm.runInNewContext(source, { window: { setTimeout(callback) { callback(); return 0; } }, clearTimeout() {}, module: compiledModule, exports: compiledModule.exports, require: name => name === './explorationTaskState' ? load('explorationTaskState.ts', {}) : ({ 'react/jsx-runtime': jsxRuntime, './useCanvasDialogBounds': { useCanvasDialogBounds: () => true }, ...dependencies })[name] ?? {}, ...globals });
  return compiledModule.exports;
}
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (data, ok = true) => ({ ok, json: async () => data });
const settle = () => new Promise(resolve => setImmediate(resolve));
const answer = '通过阅读任务材料，我记录了对公司业务和价值观的理解，并准备结合自己的岗位实践，补充具体行动和待确认的问题。';
const task = { id: 'task-one', title: '后台配置任务', versionId: 'version-one', assignmentId: 'assignment-one', revision: 4, status: 'active', answer };
const record = (id = 'check-one', extra = {}) => ({ id, body: answer, result: `真实AI反馈 ${id}。`, createdAt: '2026-11-16T06:07:08Z', status: 'COMPLETED', commentId: null, mode: 'AI', taskVersionId: task.versionId, assignmentId: task.assignmentId, ...extra });
function find(node, predicate) {
  if (Array.isArray(node)) { for (const child of node) { const found = find(child, predicate); if (found) return found; } return undefined; }
  if (!node || typeof node !== 'object') return undefined;
  if (predicate(node)) return node;
  return find(node.props?.children, predicate);
}
const button = (tree, className) => find(tree, node => node.type === 'button' && node.props.className?.includes(className));
function uiHarness({ fetch = async () => response({ items: [] }), onRun = async () => ({ record: record(), items: [record()] }), ...initial } = {}) {
  const h = hooks();
  const { ExplorationSelfCheck } = load('ExplorationSelfCheck.tsx', { react: h.react }, { fetch });
  const props = { task, answer, busy: false, onRun, ...initial };
  return { ...h, render(patch = {}) { Object.assign(props, patch); return h.render(() => ExplorationSelfCheck(props)); } };
}

test('self check appears with a real AI feedback label and validates nonblank input and edit status', () => {
  for (const status of ['active', 'returned', 'pending', 'completed', 'unavailable']) {
    const h = uiHarness({ task: { ...task, status } });
    const tree = h.render();
    assert.equal(button(tree, 'ex-self-check-run').props.disabled, !['active', 'returned'].includes(status));
    const html = renderToStaticMarkup(tree);
    assert.match(html, /AI 自测 · 成果反馈/);
    assert.match(html, /最终结果以人工审核为准/);
    assert.match(html, /历史自测记录/);
  }
  const h = uiHarness();
  assert.equal(button(h.render({ answer: `说明${' '.repeat(50)}` }), 'ex-self-check-run').props.disabled, true);
  assert.equal(button(h.render({ answer: '学'.repeat(40) }), 'ex-self-check-run').props.disabled, false);
  assert.equal(button(h.render({ answer: '学'.repeat(8001) }), 'ex-self-check-run').props.disabled, true);
  assert.match(renderToStaticMarkup(h.render()), /不能超过 8000 字/);
  assert.equal(button(h.render({ answer, busy: true }), 'ex-self-check-run').props.disabled, true);
});

test('history loads for the selected task and exposes feedback, timestamps and the input snapshot', async () => {
  const urls = [];
  const h = uiHarness({ fetch: async url => { urls.push(url); return response({ items: [record('second'), record('first', { body: '旧输入快照' })] }); } });
  h.render(); h.commit(); await settle();
  let tree = h.render();
  assert.match(renderToStaticMarkup(tree), /最近一次自测反馈/);
  button(tree, 'ex-self-check-history-toggle').props.onClick();
  tree = h.render();
  const html = renderToStaticMarkup(tree);
  assert.match(html, /第 2 次自测/);
  assert.match(html, /第 1 次自测/);
  assert.match(html, /datetime="2026-11-16T06:07:08Z"/i);
  assert.match(html, /查看当时的学习成果/);
  assert.match(html, /旧输入快照/);
  assert.equal(urls[0], '/api/learner/exploration?task=task-one&selfChecks=1');
  assert.ok(html.indexOf('真实AI反馈 second') < html.indexOf('真实AI反馈 first'));
  assert.match(renderToStaticMarkup(h.render({ answer: `${answer}已修改` })), /反馈对应上一次自测时的内容/);
});

test('a previous task version is identified even when the answer has not changed', async () => {
  const h = uiHarness({ fetch: async () => response({ items: [record('old', { taskVersionId: 'older-version' })] }) });
  h.render(); h.commit(); await settle();
  assert.match(renderToStaticMarkup(h.render()), /这条反馈来自历史任务版本/);
});

test('empty and failed history remain readable and can be retried', async () => {
  let reads = 0;
  const h = uiHarness({ fetch: async () => ++reads === 1 ? response({ error: '历史暂时不可读' }, false) : response({ items: [] }) });
  let tree = h.render();
  button(tree, 'ex-self-check-history-toggle').props.onClick();
  assert.match(renderToStaticMarkup(h.render()), /正在读取历史自测记录/);
  h.commit(); await settle(); tree = h.render();
  assert.match(renderToStaticMarkup(tree), /历史暂时不可读/);
  const retry = find(tree, node => node.type === 'button' && node.props.children === '重试读取');
  retry.props.onClick(); await settle();
  assert.match(renderToStaticMarkup(h.render()), /暂无自测记录/);
  assert.equal(reads, 2);
});

test('an in-flight old history response cannot overwrite a new task or a newly created check', async () => {
  const first = deferred(), second = deferred(); let reads = 0;
  const h = uiHarness({ fetch: () => ++reads === 1 ? first.promise : second.promise });
  h.render(); h.commit();
  h.render({ task: { ...task, id: 'task-two' } }); h.commit();
  second.resolve(response({ items: [record('task-two-result')] })); await settle();
  first.resolve(response({ items: [record('stale-task-one-result')] })); await settle();
  let html = renderToStaticMarkup(h.render());
  assert.match(html, /task-two-result/);
  assert.doesNotMatch(html, /stale-task-one-result/);
  h.unmount();

  const oldRead = deferred(); let runs = 0;
  const next = uiHarness({ fetch: () => oldRead.promise, onRun: async () => { runs++; return { record: record('new-check'), items: [record('new-check')] }; } });
  let tree = next.render(); next.commit();
  button(tree, 'ex-self-check-run').props.onClick(); await settle();
  oldRead.resolve(response({ items: [] })); await settle();
  html = renderToStaticMarkup(next.render());
  assert.match(html, /new-check/);
  assert.equal(runs, 1);
});

test('double clicks share one check and make the newest feedback immediately visible', async () => {
  const pending = deferred(); let runs = 0;
  const h = uiHarness({ onRun: () => { runs++; return pending.promise; } });
  let tree = h.render();
  const run = button(tree, 'ex-self-check-run');
  run.props.onClick(); run.props.onClick();
  tree = h.render();
  assert.equal(runs, 1);
  assert.equal(button(tree, 'ex-self-check-run').props.disabled, true);
  assert.match(renderToStaticMarkup(tree), /正在进行 AI 自测/);
  pending.resolve({ record: record('just-created'), items: [record('just-created')] }); await settle();
  tree = h.render();
  assert.match(renderToStaticMarkup(tree), /just-created/);
  assert.equal(button(tree, 'ex-self-check-run').props.disabled, false);
});

test('the shared task hook locks other writes, ignores stale reads and replaces the saved revision', async () => {
  const h = hooks(), oldRead = deferred(), post = deferred(), requests = []; let reads = 0;
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    crypto: { randomUUID: () => 'self-check-key' },
    fetch: (url, options) => { requests.push({ url, options }); return options?.method === 'POST' ? post.promise : ++reads === 1 ? Promise.resolve(response({ items: [task] })) : oldRead.promise; },
    window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  let flow = render(); h.commit(); await settle(); flow = render();
  assert.equal(flow.tasks[0].revision, 4);
  const reading = flow.refresh();
  const running = flow.runSelfCheck(task, answer);
  assert.equal(await flow.mutate(task, 'submit', answer), null);
  await flow.refresh();
  flow = render(); assert.equal(flow.busy, true);
  assert.equal(requests.length, 3);
  const payload = JSON.parse(requests[2].options.body);
  assert.equal(payload.command, 'selfCheck'); assert.equal(payload.revision, 4); assert.equal(payload.versionId, task.versionId);
  assert.equal(payload.answer, answer); assert.equal(payload.key, 'self-check-key');
  post.resolve(response({ record: record(), items: [record()], task: { ...task, revision: 5 } }));
  assert.equal((await running).task.revision, 5);
  oldRead.resolve(response({ items: [{ ...task, revision: 1 }] })); await reading;
  flow = render();
  assert.equal(flow.busy, false); assert.equal(flow.error, '');
  // The old catalog request must not add an obsolete revision after the self check.
  assert.equal(flow.tasks[0].revision, 5);
  h.unmount();
});

test('the self check slot sits after the answer and survives revision updates in exploration details', () => {
  const h = hooks(), Form = () => null, SelfCheck = () => null;
  const { ExplorationTaskHall } = load('ExplorationTaskHall.tsx', { react: h.react,
    './ExplorationLearningActions': { ExplorationAssessmentActions: Form }, './ExplorationSelfCheck': { ExplorationSelfCheck: SelfCheck },
    './useVillageTasks': { isVillageTaskClaimed: item => item.status !== 'available' },
  });
  const runCalls = [];
  const shared = { tasks: [{ ...task, materials: [], requirements: [], criteria: [] }], loading: false, error: '', busy: false, refresh() {}, mutate() {}, runSelfCheck(...args) { runCalls.push(args); return Promise.resolve(null); } };
  const render = () => h.render(() => ExplorationTaskHall({ detailOnly: true, initialTaskId: task.id, sharedExploration: shared }));
  const form = find(render(), node => node.type === Form);
  assert.equal(form.key, 'task-one:active');
  assert.equal(form.props.beforeActions.type, SelfCheck);
  assert.equal(form.props.beforeActions.key, task.id);
  form.props.beforeActions.props.onRun();
  assert.equal(runCalls[0][0].id, task.id); assert.equal(runCalls[0][1], answer);
  shared.tasks[0] = { ...shared.tasks[0], revision: 5 };
  assert.equal(find(render(), node => node.type === Form).key, form.key);
  const formSource = readFileSync(new URL('../src/app/project29/VillageTaskForm.tsx', import.meta.url), 'utf8');
  assert.ok(formSource.indexOf('beforeActions}') > formSource.indexOf('</label>'));
  assert.ok(formSource.indexOf('beforeActions}') < formSource.indexOf('{actionsContainer ? createPortal(actions, actionsContainer) : actions}'));
});

test('a real failed AI check stays in history and remains explicit about the failed attempt', async () => {
  const failed = record('failed-check', { status: 'FAILED', result: 'AI 服务暂时不可用，请稍后重试。' });
  const h = uiHarness({ fetch: async () => response({ items: [failed] }) });
  h.render(); h.commit(); await settle();
  const tree = h.render();
  assert.match(renderToStaticMarkup(tree), /本次 AI 自测未完成/);
  assert.match(renderToStaticMarkup(tree), /AI 服务暂时不可用/);
  button(tree, 'ex-self-check-history-toggle').props.onClick();
  assert.match(renderToStaticMarkup(h.render()), /AI 自测 · 暂未完成/);
  assert.equal(button(h.render(), 'ex-self-check-run').props.disabled, false);
  h.unmount();
});

function detailHarness(tasks, selectedId, overrides = {}) {
  const h = hooks();
  const Learning = () => null;
  const Assessment = () => null;
  const Entry = () => null;
  const Material = () => null;
  const { ExplorationTaskHall } = load('ExplorationTaskHall.tsx', { react: h.react,
    './ExplorationLearningActions': { ExplorationLearningActions: Learning, ExplorationAssessmentActions: Assessment, ExplorationAssessmentEntry: Entry },
    './ExplorationLearningMaterial': { ExplorationLearningMaterial: Material },
    './useVillageTasks': { isVillageTaskClaimed: item => item.claimed ?? !!item.assignmentId },
  });
  let blocked = 0;
  let closed = 0;
  const shared = { tasks, loading: false, error: '', busy: false, refresh: async () => shared.tasks,
    mutate: async () => null, completeLearning: async () => null, ...overrides };
  const props = { detailOnly: true, initialTaskId: selectedId, sharedExploration: shared,
    onTaskClose() { closed++; }, onTaskBlocked() { blocked++; } };
  return { ...h, shared, Learning, Assessment, Entry, Material, get blocked() { return blocked; }, get closed() { return closed; },
    render: () => h.render(() => ExplorationTaskHall(props)) };
}

test('a locked task deep link never renders learning materials or a result form', () => {
  const h = detailHarness([{ ...task, status: 'locked', claimed: false, assignmentId: null,
    materials: [{ name: '锁定二维码', type: 'image' }], completionMode: 'learning' }], task.id);
  let tree = h.render();
  assert.equal(find(tree, node => node.type === h.Material || node.type === h.Learning || node.type === h.Assessment), undefined);
  h.commit();
  assert.equal(h.blocked, 1);
  assert.equal(h.closed, 1);
  tree = h.render();
  assert.equal(find(tree, node => node.type === h.Material), undefined);
  h.unmount();
});

test('learning completion waits for the fresh catalog and uses it to enter the newly unlocked next task', async () => {
  const first = { ...task, id: 'first', order: 1, completionMode: 'learning', materials: [] };
  const next = { ...task, id: 'next', order: 2, status: 'locked', claimed: false, assignmentId: null,
    completionMode: 'learning', materials: [] };
  const fresh = deferred();
  let reads = 0;
  const h = detailHarness([first, next], first.id, {
    completeLearning: async () => ({ ...first, status: 'completed' }),
    refresh: async () => { reads++; h.shared.tasks = await fresh.promise; return h.shared.tasks; },
  });
  const completing = find(h.render(), node => node.type === h.Learning).props.onComplete(false);
  await settle();
  assert.equal(reads, 1);
  const waiting = find(h.render(), node => node.type === h.Learning);
  assert.equal(waiting.props.task.id, first.id);
  assert.equal(waiting.props.busy, true);
  fresh.resolve([{ ...first, status: 'completed' }, { ...next, status: 'active' }]);
  assert.equal(await completing, true);
  const continued = find(h.render(), node => node.type === h.Learning);
  assert.equal(continued.props.task.id, next.id);
  assert.equal(continued.props.task.status, 'active');
  assert.equal(continued.props.busy, false);
  h.unmount();
});

test('assessment submission refreshes the next lock state before the learner can continue', async () => {
  const first = { ...task, order: 1, completionMode: 'assessment', claimed: true };
  const next = { ...task, id: 'next', order: 2, status: 'locked', claimed: false, assignmentId: null };
  const calls = [];
  const h = detailHarness([first, next], first.id, {
    mutate: async (_task, command) => { calls.push(command); return { ...first, status: 'pending' }; },
    refresh: async () => { calls.push('refresh'); h.shared.tasks = [{ ...first, status: 'pending' }, { ...next, status: 'active' }]; return h.shared.tasks; },
  });
  assert.equal(await find(h.render(), node => node.type === h.Assessment).props.onAction('submit'), true);
  assert.deepEqual(calls, ['submit', 'refresh']);
  const submitted = find(h.render(), node => node.type === h.Assessment);
  assert.equal(submitted.props.task.status, 'pending');
  assert.equal(h.shared.tasks[1].status, 'active');
  assert.equal(submitted.props.busy, false);
  h.unmount();
});

test('locked tasks cannot send claim, material, completion or AI commands from the shared hook', async () => {
  const h = hooks();
  const requests = [];
  const locked = { ...task, status: 'locked', claimed: false, assignmentId: null };
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    fetch: async (url, options) => { requests.push({ url, options }); return response({ items: [locked] }); },
    window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  render(); h.commit(); await settle();
  const flow = render();
  assert.equal(await flow.mutate(locked, 'claim', ''), null);
  assert.equal(await flow.readMaterial(locked, 0), null);
  assert.equal(await flow.completeLearning(locked), null);
  assert.equal(await flow.runSelfCheck(locked, answer), null);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].options.method, undefined);
  h.unmount();
});

test('foreground catalog refresh shares polling reads and survives an obsolete pre-submission read', async () => {
  const h = hooks();
  const oldRead = deferred();
  const freshRead = deferred();
  const listeners = {};
  let poll;
  let reads = 0;
  const next = { ...task, id: 'next', status: 'locked', claimed: false, assignmentId: null };
  const updated = { ...task, status: 'pending', revision: 5 };
  const fresh = [updated, { ...next, status: 'active' }];
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    crypto: { randomUUID: () => 'submission-key' },
    fetch: (_url, options) => {
      if (options?.method === 'POST') return Promise.resolve(response(updated));
      reads++;
      return reads === 1 ? Promise.resolve(response({ items: [task, next] })) : reads === 2 ? oldRead.promise : freshRead.promise;
    },
    window: { setInterval: callback => { poll = callback; return 1; }, addEventListener: (event, callback) => { listeners[event] = callback; }, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  render(); h.commit(); await settle();
  const flow = render();
  const obsolete = flow.refresh();
  assert.equal((await flow.mutate(task, 'submit', answer)).status, 'pending');
  const foreground = flow.refresh();
  listeners.focus();
  poll();
  assert.equal(flow.refresh(), foreground);
  assert.equal(reads, 3);
  oldRead.resolve(response({ items: [task, next] }));
  assert.equal(await obsolete, undefined);
  assert.equal(flow.refresh(), foreground, 'An obsolete request must not clear the current shared request');
  freshRead.resolve(response({ items: fresh }));
  assert.deepEqual(JSON.parse(JSON.stringify(await foreground)), fresh);
  assert.equal(render().tasks[1].status, 'active');
  h.unmount();
});

test('a failed post-completion refresh preserves completion and never continues from the stale locked catalog', async () => {
  const first = { ...task, id: 'first', order: 1, completionMode: 'learning', materials: [] };
  const next = { ...task, id: 'next', order: 2, status: 'locked', completionMode: 'learning', materials: [] };
  const h = detailHarness([first, next], first.id, {
    completeLearning: async () => { const done = { ...first, status: 'completed' }; h.shared.tasks = [done, next]; return done; },
    refresh: async () => undefined,
  });
  assert.equal(await find(h.render(), node => node.type === h.Learning).props.onComplete(false), true);
  const tree = h.render();
  assert.equal(find(tree, node => node.type === h.Learning).props.task.id, first.id);
  assert.equal(find(tree, node => node.type === h.Learning).props.task.status, 'completed');
  assert.equal(find(tree, node => node.props?.className === 'ex-detail-notice').props.children,
    '完成记录已保存，任务状态暂未刷新，请稍后重试。');
  h.unmount();
});

test('a file-only assessment claims its real pinned task before exposing question downloads', async () => {
  const assessment = { ...task, claimed: false, assignmentId: null, completionMode: 'assessment',
    materials: [{ name: '学习材料.pdf', type: 'file' }], taskFiles: [{ name: '入营题目.docx', type: 'file' }] };
  const calls = [];
  const claim = deferred();
  const h = detailHarness([assessment], task.id, {
    mutate: async (selected, command) => {
      calls.push({ selected, command });
      const updated = await claim.promise;
      h.shared.tasks = [updated];
      return updated;
    },
    readMaterial: async () => { throw new Error('Question documents must not record learning material indices'); },
  });
  let tree = h.render();
  assert.equal(find(tree, node => node.type === h.Entry), undefined, 'A file-only assessment has no missing test-link warning');
  assert.equal(find(tree, node => node.type === h.Material && node.props.group === 'task'), undefined);
  const section = find(tree, node => node.props?.className === 'ex-detail-section ex-task-files-section');
  const start = find(section, node => node.type === 'button');
  start.props.onClick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, 'claim');
  assert.equal(calls[0].selected.versionId, task.versionId);
  assert.equal(calls[0].selected.revision, task.revision);
  tree = h.render();
  assert.equal(find(tree, node => node.type === h.Material && node.props.group === 'task'), undefined);
  assert.equal(find(find(tree, node => node.props?.className?.includes('ex-task-files-section')),
    node => node.type === 'button').props.disabled, true);
  claim.resolve({ ...assessment, claimed: true, assignmentId: 'new-assignment', revision: 1 });
  await settle();
  tree = h.render();
  const question = find(tree, node => node.type === h.Material && node.props.group === 'task');
  assert.equal(question.props.taskId, task.id);
  assert.equal(question.props.index, 0);
  assert.equal(question.props.material.name, '入营题目.docx');
  assert.equal(question.props.onOpened, undefined);
  assert.equal(question.props.opened, undefined);
  assert.match(question.key, /version-one:task:0:/);
  const reading = find(tree, node => node.type === h.Material && !node.props.group);
  assert.equal(reading.props.index, 0, 'Learning and question documents have independent indices');
  assert.equal(reading.props.material.name, '学习材料.pdf');
  assert.equal(reading.props.onOpened, undefined, 'Assessment learning attachments preserve the existing non-reading-completion flow');
  h.unmount();
});

test('a failed claim does not expose question documents and remains retryable', async () => {
  const assessment = { ...task, claimed: false, assignmentId: null, completionMode: 'assessment',
    materials: [], taskFiles: [{ name: '题目.pdf', type: 'file' }] };
  let claims = 0;
  const h = detailHarness([assessment], task.id, { mutate: async () => { claims++; return null; } });
  let tree = h.render();
  find(find(tree, node => node.props?.className?.includes('ex-task-files-section')),
    node => node.type === 'button').props.onClick();
  await settle();
  tree = h.render();
  assert.equal(claims, 1);
  assert.equal(find(tree, node => node.type === h.Material && node.props.group === 'task'), undefined);
  assert.equal(find(find(tree, node => node.props?.className?.includes('ex-task-files-section')),
    node => node.type === 'button').props.disabled, false);
  h.unmount();
});

test('learning and signout never expose stale question files or count them as reading materials', async () => {
  for (const completionMode of ['learning', 'checkin']) {
    const current = { ...task, completionMode, materials: [{ name: '学习说明', type: 'link' }],
      taskFiles: [{ name: '旧题目.pdf', type: 'file' }], assessmentUrl: 'https://example.com/old-test' };
    const reads = [];
    const h = detailHarness([current], current.id, {
      readMaterial: async (selected, index) => { reads.push({ id: selected.id, index }); return current; },
    });
    const tree = h.render();
    assert.equal(find(tree, node => node.type === h.Entry), undefined);
    assert.equal(find(tree, node => node.props?.className?.includes('ex-task-files-section')), undefined);
    assert.equal(find(tree, node => node.type === h.Material && node.props.group === 'task'), undefined);
    await find(tree, node => node.type === h.Material).props.onOpened();
    assert.deepEqual(reads, [{ id: task.id, index: 0 }]);
    assert.equal(find(tree, node => node.type === h.Assessment), undefined);
    h.unmount();
  }
});

test('owned assessment files remain readable through review and history while locked deep links expose none', () => {
  for (const status of ['active', 'returned', 'pending', 'completed', 'locked']) {
    const current = { ...task, status, claimed: status !== 'locked', completionMode: 'assessment',
      versionId: 'owned-original-version', materials: [], taskFiles: [{ name: '原版本题目.pdf', type: 'file' }],
      assessmentUrl: 'https://example.com/original-test' };
    const h = detailHarness([current], current.id);
    const tree = h.render();
    const file = find(tree, node => node.type === h.Material && node.props.group === 'task');
    if (status === 'locked') {
      assert.equal(file, undefined);
      assert.equal(find(tree, node => node.type === h.Entry || node.type === h.Assessment), undefined);
    } else {
      assert.equal(file.props.material.name, '原版本题目.pdf');
      assert.match(file.key, /owned-original-version:task:0:/);
      assert.equal(find(tree, node => node.type === h.Entry).props.url, current.assessmentUrl);
      assert.equal(find(tree, node => node.type === h.Entry).props.onStart, undefined);
      assert.equal(find(find(tree, node => node.props?.className?.includes('ex-task-files-section')),
        node => node.type === 'button'), undefined);
    }
    h.unmount();
  }
});
