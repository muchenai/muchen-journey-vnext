import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import * as jsxRuntime from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const source = ts.transpileModule(readFileSync(new URL('../src/app/project29/ExplorationSelfCheck.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const settle = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = items => ({ ok: true, json: async () => ({ items }) });
const task = {
  id: 'first-task', title: 'AI任务', versionId: 'version-one', assignmentId: 'assignment-one',
  revision: 4, status: 'active', reviewMode: 'AI', completionMode: 'assessment', passScore: 60,
};
const record = (extra = {}) => ({
  id: 'running-one', createdAt: '2026-11-18T07:10:00Z', body: '已填写的成果',
  result: '', status: 'RUNNING', commentId: null, mode: 'AI',
  taskVersionId: task.versionId, assignmentId: task.assignmentId, inputKind: 'text',
  commentStatus: 'NOT_REQUIRED', ...extra,
});
const completed = extra => record({ status: 'COMPLETED', result: '已生成的具体评分反馈。', score: 40,
  maxScore: 100, passed: false, taskCompleted: false, ...extra });

function find(node, predicate) {
  if (Array.isArray(node)) return node.map(child => find(child, predicate)).find(Boolean);
  if (!node || typeof node !== 'object') return undefined;
  return predicate(node) ? node : find(node.props?.children, predicate);
}
const runButton = tree => find(tree, node => node.type === 'button' && node.props.className?.includes('ex-self-check-run'));
const same = (left, right) => left && right && left.length === right.length && left.every((item, index) => Object.is(item, right[index]));

function harness({ fetch = async () => response([]), onRun = async () => null, ...initial } = {}) {
  const slots = [], timers = new Map();
  let cursor = 0, effects = [], timerId = 0, mounted = true, updatesAfterUnmount = 0;
  const react = {
    useState(initialValue) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initialValue === 'function' ? initialValue() : initialValue;
      return [slots[index], value => {
        if (!mounted) updatesAfterUnmount++;
        slots[index] = typeof value === 'function' ? value(slots[index]) : value;
      }];
    },
    useRef(initialValue) { return slots[cursor++] ??= { current: initialValue }; },
    useCallback(callback, dependencies) {
      const index = cursor++;
      if (!slots[index] || !same(slots[index].dependencies, dependencies)) slots[index] = { callback, dependencies };
      return slots[index].callback;
    },
    useEffect(callback, dependencies) {
      const index = cursor++;
      if (!slots[index] || !same(slots[index].dependencies, dependencies)) {
        const previous = slots[index];
        effects.push(() => { previous?.cleanup?.(); slots[index].cleanup = callback(); });
        slots[index] = { dependencies };
      }
    },
  };
  const loadedModule = { exports: {} };
  vm.runInNewContext(source, {
    module: loadedModule, exports: loadedModule.exports, URL, fetch,
    window: {
      setTimeout(callback, delay) { assert.equal(delay, 2000); const id = ++timerId; timers.set(id, callback); return id; },
      clearTimeout(id) { timers.delete(id); },
    },
    require: name => ({ react, 'react/jsx-runtime': jsxRuntime })[name] ?? {},
  });
  const props = { task, answer: '已填写的成果', busy: false, onRun, ...initial };
  let tree;
  const paint = (patch = {}) => {
    Object.assign(props, patch); cursor = 0;
    tree = loadedModule.exports.ExplorationSelfCheck(props);
    const pending = effects; effects = []; pending.forEach(effect => effect());
    return tree;
  };
  const flush = async () => { await settle(); paint(); await settle(); return paint(); };
  return {
    paint, flush, tree: () => tree, timers,
    html: () => renderToStaticMarkup(tree),
    async tick() {
      assert.equal(timers.size, 1);
      const [id, callback] = timers.entries().next().value;
      timers.delete(id); callback();
      return flush();
    },
    unmount() {
      mounted = false;
      slots.forEach(slot => slot?.cleanup?.());
    },
    updatesAfterUnmount: () => updatesAfterUnmount,
  };
}

test('reopening during the shared pending request immediately restores the running state without a POST', async () => {
  let reads = 0, runs = 0;
  const h = harness({ pending: true, fetch: async () => { reads++; return response([]); }, onRun: async () => { runs++; return null; } });
  let tree = h.paint();
  assert.match(h.html(), /正在进行 AI 自测/);
  assert.match(h.html(), /可以关闭任务卡/);
  assert.equal(runButton(tree).props.disabled, true);
  runButton(tree).props.onClick();
  tree = await h.flush();
  h.paint({ answer: '重进后不同的补充文字' });
  runButton(h.tree()).props.onClick();
  assert.equal(runs, 0);
  assert.equal(reads, 1);
  assert.equal(h.timers.size, 1);
  h.paint({ pending: false, records: [completed()] });
  await h.flush();
  assert.match(h.html(), /已生成的具体评分反馈/);
  assert.doesNotMatch(h.html(), /正在进行 AI 自测/);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('a server running record automatically resolves to feedback and stops polling without another assessment', async () => {
  let reads = 0, runs = 0;
  const h = harness({ fetch: async () => response(++reads === 1 ? [record()] : [completed()]), onRun: async () => { runs++; return null; } });
  h.paint(); await h.flush();
  assert.match(h.html(), /正在进行 AI 自测/);
  assert.equal(runButton(h.tree()).props.disabled, true);
  h.paint({ answer: '换了一段补充说明，也不能在同一次评测中重复发起' });
  runButton(h.tree()).props.onClick();
  await h.tick();
  assert.match(h.html(), /已生成的具体评分反馈/);
  assert.match(h.html(), /评测未达标/);
  assert.doesNotMatch(h.html(), /正在进行 AI 自测/);
  assert.equal(reads, 2);
  assert.equal(runs, 0);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('automatic polling exposes an explicit failure and stops when the attempt fails', async () => {
  let reads = 0;
  const failed = record({ status: 'FAILED', result: '模型服务暂时不可用。', errorMessage: '模型服务暂时不可用。' });
  const h = harness({ fetch: async () => response(++reads === 1 ? [record()] : [failed]) });
  h.paint(); await h.flush(); await h.tick();
  assert.match(h.html(), /本次 AI 自测未完成/);
  assert.match(h.html(), /模型服务暂时不可用/);
  assert.equal((h.html().match(/模型服务暂时不可用/g) ?? []).length, 1);
  assert.equal(runButton(h.tree()).props.disabled, false);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('a grading commit followed by automatic completion gets a short confirmation read', async () => {
  let reads = 0;
  const passing = completed({ score: 80, passed: true, taskCompleted: false });
  const h = harness({ fetch: async () => response([++reads === 1 ? record()
    : reads === 2 ? passing : { ...passing, taskCompleted: true }]) });
  h.paint(); await h.flush(); await h.tick();
  assert.match(h.html(), /正在确认任务完成状态/);
  assert.doesNotMatch(h.html(), /正在进行 AI 自测/);
  assert.equal(runButton(h.tree()).props.disabled, true);
  await h.tick();
  h.paint({ task: { ...task, status: 'completed' } });
  assert.match(h.html(), /评测达标，任务已自动完成/);
  assert.equal(reads, 3);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('unconfirmed passing scores stop automatic confirmation after three reads and retain honest feedback', async () => {
  let reads = 0;
  const passing = completed({ score: 80, passed: true, taskCompleted: false });
  const h = harness({ fetch: async () => { reads++; return response([passing]); } });
  h.paint(); await h.flush();
  for (let index = 0; index < 3; index++) await h.tick();
  assert.equal(reads, 4);
  assert.equal(h.timers.size, 0);
  assert.doesNotMatch(h.html(), /正在进行 AI 自测|正在确认任务完成状态/);
  assert.match(h.html(), /任务完成状态尚未确认/);
  assert.doesNotMatch(h.html(), /评测达标，任务已自动完成/);
  const reread = find(h.tree(), node => node.type === 'button' && node.props.children === '重新读取自测状态 ↻');
  assert.equal(reread.props.disabled, false);
  reread.props.onClick(); await h.flush();
  assert.equal(reads, 5);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('comment confirmation is tracked separately from scoring and stops after a confirmed delivery', async () => {
  let reads = 0;
  const url = 'https://team.feishu.cn/docx/current';
  const h = harness({ answer: url, fetch: async () => response([completed({
    body: url, inputKind: 'document', documentUrl: url, commentStatus: ++reads === 1 ? 'PENDING' : 'SENT',
  })]) });
  h.paint(); await h.flush();
  assert.match(h.html(), /正在确认文档评论/);
  assert.doesNotMatch(h.html(), /正在进行 AI 自测/);
  assert.equal(runButton(h.tree()).props.disabled, true);
  await h.tick();
  assert.match(h.html(), /反馈已写入文档标题评论/);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('uncertain comment delivery neither polls forever nor claims scoring is still running', async () => {
  let reads = 0;
  const url = 'https://team.feishu.cn/docx/current';
  const h = harness({ answer: url, fetch: async () => { reads++; return response([completed({
    body: url, inputKind: 'document', documentUrl: url, commentStatus: 'UNCERTAIN',
  })]); } });
  h.paint(); await h.flush();
  assert.match(h.html(), /文档评论是否送达暂未确认/);
  assert.doesNotMatch(h.html(), /正在进行 AI 自测|正在确认文档评论/);
  assert.equal(runButton(h.tree()).props.disabled, true);
  assert.equal(reads, 1);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('slow silent polls retain feedback and cannot overlap or replace it with a loading screen', async () => {
  let reads = 0;
  const poll = deferred();
  const h = harness({ fetch: () => ++reads === 1 ? Promise.resolve(response([record()])) : poll.promise });
  h.paint(); await h.flush();
  find(h.tree(), node => node.type === 'button' && node.props.className === 'ex-self-check-history-toggle').props.onClick();
  h.paint();
  await h.tick();
  assert.equal(reads, 2);
  assert.equal(h.timers.size, 0, 'The next poll waits for the current read');
  assert.match(h.html(), /历史自测记录|AI 自测 · 正在处理/);
  assert.doesNotMatch(h.html(), /正在读取历史自测记录/);
  poll.resolve(response([completed()]));
  await h.flush();
  assert.equal(h.timers.size, 0);
  assert.match(h.html(), /已生成的具体评分反馈/);
  h.unmount();
});

test('a terminal result retained by the shared hook supersedes an older in-flight history response', async () => {
  const oldRead = deferred();
  const h = harness({ pending: true, fetch: () => oldRead.promise });
  h.paint();
  h.paint({ pending: false, records: [completed({ id: 'canonical-result' })] });
  oldRead.resolve(response([record()]));
  await h.flush();
  assert.match(h.html(), /已生成的具体评分反馈/);
  assert.doesNotMatch(h.html(), /正在进行 AI 自测/);
  assert.equal(h.timers.size, 0);
  h.unmount();
});

test('switching either the task or its version rejects obsolete running responses', async () => {
  for (const nextTask of [{ ...task, id: 'second-task' }, { ...task, versionId: 'version-two' }]) {
    let reads = 0;
    const previous = deferred(), next = deferred();
    const h = harness({ fetch: () => ++reads === 1 ? previous.promise : next.promise });
    h.paint();
    h.paint({ task: nextTask });
    next.resolve(response([completed({ taskVersionId: nextTask.versionId })]));
    await h.flush();
    previous.resolve(response([record()]));
    await h.flush();
    assert.match(h.html(), /已生成的具体评分反馈/);
    assert.doesNotMatch(h.html(), /正在进行 AI 自测/);
    assert.equal(h.timers.size, 0);
    h.unmount();
  }
});

test('closing during a poll cleans its timer and ignores the response after unmount', async () => {
  let reads = 0;
  const poll = deferred();
  const h = harness({ fetch: () => ++reads === 1 ? Promise.resolve(response([record()])) : poll.promise });
  h.paint(); await h.flush(); await h.tick();
  h.unmount();
  poll.resolve(response([completed()]));
  await settle(); await settle();
  assert.equal(h.timers.size, 0);
  assert.equal(h.updatesAfterUnmount(), 0);
  assert.equal(reads, 2);
});

test('manual tasks and historical running versions never start assessment polling', async () => {
  let reads = 0;
  const manual = harness({ task: { ...task, reviewMode: 'HUMAN' }, pending: true, records: [record()],
    fetch: async () => { reads++; return response([record()]); } });
  assert.equal(manual.paint(), null); await manual.flush();
  assert.equal(reads, 0);
  assert.equal(manual.timers.size, 0);
  manual.unmount();
  const historical = harness({ fetch: async () => response([record({ taskVersionId: 'old-version' })]) });
  historical.paint(); await historical.flush();
  assert.doesNotMatch(historical.html(), /正在进行 AI 自测/);
  assert.equal(runButton(historical.tree()).props.disabled, false);
  assert.equal(historical.timers.size, 0);
  historical.unmount();
});
