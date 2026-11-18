import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import * as jsxRuntime from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

function hooks() {
  const slots = []; let cursor = 0; let effects = [];
  const same = (a, b) => a && b && a.length === b.length && a.every((item, index) => Object.is(item, b[index]));
  return {
    react: {
      useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial; return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }]; },
      useRef(initial) { return slots[cursor++] ??= { current: initial }; },
      useCallback(callback, dependencies) { const index = cursor++; if (!slots[index] || !same(slots[index].dependencies, dependencies)) slots[index] = { callback, dependencies }; return slots[index].callback; },
      useEffect(callback, dependencies) { const index = cursor++; if (!slots[index] || !same(slots[index].dependencies, dependencies)) { const previous = slots[index]; effects.push(() => { previous?.cleanup?.(); slots[index].cleanup = callback(); }); slots[index] = { dependencies }; } },
      useLayoutEffect(callback, dependencies) { const index = cursor++; if (!slots[index] || !same(slots[index].dependencies, dependencies)) { const previous = slots[index]; effects.push(() => { previous?.cleanup?.(); slots[index].cleanup = callback(); }); slots[index] = { dependencies }; } },
    },
    render(callback) { cursor = 0; return callback(); },
    commit() { const pending = effects; effects = []; pending.forEach(effect => effect()); },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}
const compiled = new Map();
function load(file, dependencies, globals = {}) {
  const loadedModule = { exports: {} };
  if (!compiled.has(file)) compiled.set(file, ts.transpileModule(readFileSync(new URL(`../src/app/project29/${file}`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText);
  const source = compiled.get(file);
  vm.runInNewContext(source, { window: { setTimeout(callback) { callback(); return 0; } }, clearTimeout() {}, module: loadedModule, exports: loadedModule.exports, URL, require: name => name === './explorationTaskState' ? load('explorationTaskState.ts', {}) : ({ 'react/jsx-runtime': jsxRuntime, './useCanvasDialogBounds': { useCanvasDialogBounds: () => true }, ...dependencies })[name] ?? {}, ...globals });
  return loadedModule.exports;
}
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const response = (data, ok = true) => ({ ok, json: async () => data });
const settle = () => new Promise(resolve => setImmediate(resolve));
const answer = '通过阅读任务材料，我记录了对公司业务和价值观的理解，并准备结合自己的岗位实践，补充具体行动和待确认的问题。';
const task = { id: 'task-one', title: '后台配置任务', versionId: 'version-one', assignmentId: 'assignment-one', revision: 4, status: 'active', reviewMode: 'AI', passScore: 60, completionMode: 'assessment', answer };
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
    assert.match(html, /AI 评测 · 维度评分/);
    assert.match(html, /达到 60 分后自动完成任务/);
    assert.doesNotMatch(html, /最终结果以人工审核为准/);
    assert.match(html, /历史自测记录/);
  }
  const h = uiHarness();
  assert.equal(button(h.render({ answer: ' '.repeat(50) }), 'ex-self-check-run').props.disabled, true);
  assert.equal(button(h.render({ answer: '简短说明' }), 'ex-self-check-run').props.disabled, false);
  assert.equal(button(h.render({ answer: '学'.repeat(40) }), 'ex-self-check-run').props.disabled, false);
  assert.equal(button(h.render({ answer: '学'.repeat(8001) }), 'ex-self-check-run').props.disabled, true);
  assert.match(renderToStaticMarkup(h.render()), /不能超过 8000 字/);
  assert.equal(button(h.render({ answer, busy: true }), 'ex-self-check-run').props.disabled, true);
});

test('text and Feishu URLs share the input without applying submission length to the self check', () => {
  const h = uiHarness({ task: { ...task, minimumAnswerLength: 100 } });
  for (const input of ['简短结果', 'https://team.feishu.cn/docx/abc', '我的补充说明：https://team.feishu.cn/docx/abc']) {
    const tree = h.render({ answer: input });
    assert.equal(button(tree, 'ex-self-check-run').props.disabled, false);
    assert.match(renderToStaticMarkup(tree), /链接旁的文字会作为补充说明/);
  }
});

test('manual, unconfigured, learning and signout tasks neither show AI controls nor load AI records', async () => {
  for (const extra of [{ reviewMode: 'HUMAN' }, { reviewMode: 'NONE' }, { reviewMode: undefined },
    { completionMode: 'learning' }, { completionMode: 'checkin' }]) {
    let reads = 0, runs = 0;
    const h = uiHarness({ task: { ...task, ...extra }, fetch: async () => { reads++; return response({ items: [] }); },
      onRun: async () => { runs++; return null; } });
    assert.equal(h.render(), null);
    h.commit(); await settle();
    assert.equal(h.render(), null);
    assert.equal(reads, 0);
    assert.equal(runs, 0);
    h.unmount();
  }
});

test('scored AI results show configured dimension scores, total and threshold with confirmed automatic completion', async () => {
  const completed = record('graded', { score: 82, maxScore: 100, passed: true, taskCompleted: true,
    dimensions: [{ id: 'correctness', name: '回答准确性', score: 47, maxScore: 60, feedback: '关键事实正确。' },
      { id: 'action', name: '行动方案', score: 35, maxScore: 40, feedback: '行动步骤明确。' }] });
  const h = uiHarness({ task: { ...task, status: 'completed', passScore: 75 }, fetch: async () => response({ items: [completed] }) });
  h.render(); h.commit(); await settle();
  const tree = h.render(), html = renderToStaticMarkup(tree);
  assert.match(html, /总分 82 \/ 100/);
  assert.match(html, /通过线 75 分/);
  assert.match(html, /回答准确性：47 \/ 60/);
  assert.match(html, /行动方案：35 \/ 40/);
  assert.match(html, /行动步骤明确/);
  assert.match(html, /评测达标，任务已自动完成/);
  assert.equal(button(tree, 'ex-self-check-run').props.disabled, true);
  h.unmount();
});

test('below-threshold AI feedback stays editable and a revised answer can be reassessed', async () => {
  let runs = 0;
  const below = record('below', { score: 59, maxScore: 100, passed: false, taskCompleted: false,
    dimensions: [{ id: 'answer', name: '答案完整性', score: 59, maxScore: 100, feedback: '请补充原因和处理步骤。' }] });
  const h = uiHarness({ fetch: async () => response({ items: [below] }), onRun: async () => { runs++; return { record: below, items: [below] }; } });
  h.render(); h.commit(); await settle();
  let tree = h.render(), html = renderToStaticMarkup(tree);
  assert.match(html, /评测未达标，请根据维度反馈修改成果后重新评测/);
  assert.match(html, /通过线 60 分/);
  assert.doesNotMatch(html, /评测达标，任务已自动完成/);
  assert.equal(button(tree, 'ex-self-check-run').props.disabled, false);
  tree = h.render({ answer: `${answer}我已补充原因和具体处理步骤。` });
  button(tree, 'ex-self-check-run').props.onClick(); await settle();
  assert.equal(runs, 1);
  h.unmount();
});

test('AI failures and inconsistent scores never claim an assessment passed or automatically completed', async () => {
  for (const extra of [{ status: 'FAILED', score: 100, passed: true, taskCompleted: true },
    { score: 30, passed: true, taskCompleted: true }, { score: 99, passed: false, taskCompleted: true },
    { score: NaN, passed: true, taskCompleted: true }, { score: 101, passed: true, taskCompleted: true }]) {
    const h = uiHarness({ fetch: async () => response({ items: [record('invalid-grade', extra)] }) });
    h.render(); h.commit(); await settle();
    assert.doesNotMatch(renderToStaticMarkup(h.render()), /评测达标，任务已自动完成/);
    h.unmount();
  }
  const h = uiHarness({ fetch: async () => response({ items: [record('not-persisted', { score: 90, passed: true, taskCompleted: true })] }) });
  h.render(); h.commit(); await settle();
  assert.match(renderToStaticMarkup(h.render()), /任务完成状态尚未确认/);
  assert.doesNotMatch(renderToStaticMarkup(h.render()), /评测达标，任务已自动完成/);
  h.unmount();
});

test('text results stay on the page and never claim a document comment was sent', async () => {
  const h = uiHarness({ fetch: async () => response({ items: [record('text', { inputKind: 'text', commentStatus: 'NOT_REQUIRED' })] }) });
  h.render(); h.commit(); await settle();
  const html = renderToStaticMarkup(h.render());
  assert.match(html, /真实AI反馈 text/);
  assert.doesNotMatch(html, /反馈已写入文档标题评论|打开结果文档/);
});

test('a completed analysis survives a failed document comment and remains retryable', async () => {
  const doc = 'https://team.feishu.cn/docx/abc';
  const current = record('document', { body: doc, inputKind: 'document', documentUrl: doc,
    commentStatus: 'FAILED', commentMessage: '当前应用没有评论权限，请联系文档所有者授权。' });
  const h = uiHarness({ answer: doc, fetch: async () => response({ items: [current] }) });
  h.render(); h.commit(); await settle();
  const tree = h.render(), html = renderToStaticMarkup(tree);
  assert.match(html, /真实AI反馈 document/);
  assert.match(html, /分析已完成，文档评论发送失败/);
  assert.match(html, /没有评论权限/);
  assert.doesNotMatch(html, /本次 AI 自测未完成|反馈已写入文档标题评论/);
  assert.equal(button(tree, 'ex-self-check-run').props.disabled, false);
});

test('a failed analysis shows one concrete reason instead of repeating it as feedback and comment errors', async () => {
  const doc = 'https://team.feishu.cn/wiki/answerdocument';
  const reason = 'AI 未返回完整评价，尚未发表评论，请稍后重试。';
  const failed = record('incomplete-analysis', { body: doc, status: 'FAILED', inputKind: 'document',
    documentUrl: doc, result: reason, errorMessage: reason, commentMessage: reason, commentStatus: 'FAILED' });
  const h = uiHarness({ answer: doc, fetch: async () => response({ items: [failed] }) });
  h.render(); h.commit(); await settle();
  let tree = h.render(), html = renderToStaticMarkup(tree);
  assert.equal(html.split(reason).length - 1, 1);
  assert.match(html, /本次 AI 自测未完成/);
  assert.doesNotMatch(html, /class="ex-self-check-result"|文档评论未发送，请先处理|文档评论发送失败|查看标题评论/);
  assert.match(html, /打开答题文档/);
  assert.equal(button(tree, 'ex-self-check-run').props.disabled, false);

  button(tree, 'ex-self-check-history-toggle').props.onClick();
  tree = h.render();
  const history = find(tree, node => node.props?.role === 'region' && node.props?.['aria-label'] === '历史自测记录');
  html = renderToStaticMarkup(history);
  assert.equal(html.split(reason).length - 1, 1, 'The historical copy also explains each failed attempt only once');
  assert.doesNotMatch(html, /class="ex-self-check-result"/);
  h.unmount();
});

test('a successful analysis keeps its result while duplicate comment delivery reasons appear once', async () => {
  const doc = 'https://team.feishu.cn/docx/answerdocument';
  const reason = '当前应用没有评论权限，请联系文档所有者授权。';
  const current = record('analysis-kept', { body: doc, inputKind: 'document', documentUrl: doc,
    commentStatus: 'FAILED', errorMessage: reason, commentMessage: reason });
  const h = uiHarness({ answer: doc, fetch: async () => response({ items: [current] }) });
  h.render(); h.commit(); await settle();
  const html = renderToStaticMarkup(h.render());
  assert.match(html, /真实AI反馈 analysis-kept/);
  assert.match(html, /分析已完成，文档评论发送失败/);
  assert.equal(html.split(reason).length - 1, 1);
  assert.doesNotMatch(html, /本次 AI 自测未完成|反馈已写入文档标题评论/);
  h.unmount();
});

test('only an explicitly sent document comment is shown as delivered and mentions the document owner', async () => {
  const doc = 'https://team.feishu.cn/docx/abc';
  for (const status of ['SENT', undefined]) {
    const h = uiHarness({ answer: doc, fetch: async () => response({ items: [record('document', {
      body: doc, mode: 'DOCUMENT_AI', documentUrl: doc, commentId: 'comment-one', commentStatus: status,
    })] }) });
    h.render(); h.commit(); await settle();
    const html = renderToStaticMarkup(h.render());
    if (status === 'SENT') assert.match(html, /反馈已写入文档标题评论，并 @ 文档所有者/);
    else { assert.match(html, /未保存评论送达状态/); assert.doesNotMatch(html, /反馈已写入文档标题评论/); }
    assert.match(html, /href="https:\/\/team.feishu.cn\/docx\/abc" target="_blank" rel="noopener noreferrer"/);
  }
});

test('unconfirmed document delivery blocks repeats even after supplementary text changes and can be refreshed', async () => {
  const doc = 'https://team.feishu.cn/docx/abc?from=journey';
  for (const commentStatus of ['PENDING', 'UNCERTAIN']) {
    let reads = 0, runs = 0;
    const current = record('uncertain', { body: doc, inputKind: 'document', documentUrl: doc, commentStatus });
    const h = uiHarness({ answer: `新增的补充说明 https://team.feishu.cn/docx/abc`,
      fetch: async () => response({ items: [{ ...current, commentStatus: ++reads === 1 ? commentStatus : 'SENT' }] }),
      onRun: async () => { runs++; return null; } });
    h.render(); h.commit(); await settle();
    let tree = h.render(), html = renderToStaticMarkup(tree);
    assert.equal(button(tree, 'ex-self-check-run').props.disabled, true);
    button(tree, 'ex-self-check-run').props.onClick(); await settle();
    assert.equal(runs, 0);
    assert.match(html, /真实AI反馈 uncertain/);
    assert.match(html, /暂勿重复/);
    assert.doesNotMatch(html, /反馈已写入文档标题评论/);
    find(tree, node => node.type === 'button' && node.props.children === '重新读取自测状态 ↻').props.onClick(); await settle();
    tree = h.render();
    assert.equal(button(tree, 'ex-self-check-run').props.disabled, false);
    assert.match(renderToStaticMarkup(tree), /反馈已写入文档标题评论/);
    assert.equal(button(h.render({ answer: '文字任务的新结果' }), 'ex-self-check-run').props.disabled, false);
  }
});

test('history preserves individual document delivery outcomes and never creates unsafe document links', async () => {
  const h = uiHarness({ fetch: async () => response({ items: [
    record('latest', { inputKind: 'document', commentStatus: 'SENT', documentUrl: 'https://team.feishu.cn/docx/abc' }),
    record('old-failed', { inputKind: 'document', commentStatus: 'FAILED', documentUrl: 'javascript:alert(1)', commentMessage: '旧评论被拒绝' }),
    record('old-uncertain', { inputKind: 'document', commentStatus: 'UNCERTAIN', documentUrl: 'https://feishu.cn.evil.test/docx/abc' }),
  ] }) });
  h.render(); h.commit(); await settle();
  button(h.render(), 'ex-self-check-history-toggle').props.onClick();
  const html = renderToStaticMarkup(h.render());
  assert.match(html, /真实AI反馈 old-failed/);
  assert.match(html, /旧评论被拒绝/);
  assert.match(html, /文档评论是否送达暂未确认/);
  assert.doesNotMatch(html, /href="(?:javascript:|https:\/\/feishu.cn.evil.test)/);
});

test('refreshing a result after a lost response clears the obsolete unconfirmed error without rerunning AI', async () => {
  let reads = 0, runs = 0;
  const h = uiHarness({
    fetch: async () => response({ items: ++reads === 1 ? [] : [record('recovered', { inputKind: 'text', commentStatus: 'NOT_REQUIRED' })] }),
    onRun: async () => { runs++; throw new Error('Connection lost'); },
  });
  h.render(); h.commit(); await settle();
  button(h.render(), 'ex-self-check-run').props.onClick(); await settle();
  let tree = h.render();
  assert.match(renderToStaticMarkup(tree), /暂未确认自测结果/);
  find(tree, node => node.type === 'button' && node.props.children === '重新读取自测状态 ↻').props.onClick(); await settle();
  tree = h.render();
  assert.match(renderToStaticMarkup(tree), /真实AI反馈 recovered/);
  assert.doesNotMatch(renderToStaticMarkup(tree), /暂未确认自测结果/);
  assert.equal(runs, 1);
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

test('a passing AI assessment refreshes unlocked tasks and treasures without replaying a completed assessment', async () => {
  const h = hooks(), posts = [];
  let reads = 0;
  const next = { ...task, id: 'next-task', status: 'locked', assignmentId: null, claimed: false };
  const completed = { ...task, status: 'completed', revision: 5, answer: '已达标的作答' };
  const passed = record('passed', { score: 80, maxScore: 100, passed: true, taskCompleted: true });
  const treasures = { total: 4, count: 1, items: [{ id: 'new-treasure' }], pendingDrops: [{ id: 'new-treasure' }] };
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    crypto: { randomUUID: () => 'grade-key' },
    fetch: async (_url, options) => {
      if (options?.method === 'POST') { posts.push(JSON.parse(options.body)); return response({ record: passed, items: [passed], task: completed }); }
      reads++;
      return reads === 1 ? response({ items: [task, next] })
        : response({ items: [{ ...task, revision: 4 }, { ...next, status: 'active', assignmentId: 'next-assignment' }], treasures });
    },
    window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  render(); h.commit(); await settle();
  assert.equal((await render().runSelfCheck(task, answer)).record.taskCompleted, true);
  const flow = render();
  assert.equal(reads, 2);
  assert.equal(flow.tasks[0].status, 'completed', 'A stale catalog cannot revert the persisted completion');
  assert.equal(flow.tasks[0].revision, 5);
  assert.equal(flow.tasks[1].status, 'active');
  assert.equal(flow.treasures.count, 1);
  assert.equal(await flow.runSelfCheck(task, answer), null, 'A stale open card cannot rerun a now completed task');
  assert.equal(await flow.mutate(completed, 'submit', answer), null, 'A graded task has no manual-submit bypass');
  assert.equal(posts.length, 1);
  h.unmount();
});

test('AI assessments preserve saved completion when the catalog refresh fails', async () => {
  const h = hooks(); let reads = 0;
  const completed = { ...task, status: 'completed', revision: 5 };
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    crypto: { randomUUID: () => 'completion-key' },
    fetch: async (_url, options) => {
      if (options?.method === 'POST') return response({ record: record('passed', { score: 90, passed: true, taskCompleted: true }), items: [], task: completed });
      if (++reads === 1) return response({ items: [task] });
      throw new Error('Catalog unavailable');
    },
    window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  render(); h.commit(); await settle();
  assert.equal((await render().runSelfCheck(task, answer)).task.status, 'completed');
  assert.equal(render().tasks[0].status, 'completed');
  assert.match(render().error, /评测结果已保存，任务目录暂未刷新/);
  assert.equal(await render().runSelfCheck(task, answer), null);
  h.unmount();
});

test('the shared hook refuses AI requests for manual and learning tasks before any network write', async () => {
  for (const extra of [{ reviewMode: 'HUMAN' }, { reviewMode: 'NONE' }, { completionMode: 'learning' }, { completionMode: 'checkin' }]) {
    const h = hooks(), requests = [], current = { ...task, ...extra };
    const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
      fetch: async (url, options) => { requests.push({ url, options }); return response({ items: [current] }); },
      window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
      document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
    });
    const render = () => h.render(() => useExplorationTasks(true));
    render(); h.commit(); await settle();
    assert.equal(await render().runSelfCheck(current, answer), null);
    assert.equal(requests.filter(request => request.options?.method === 'POST').length, 0);
    h.unmount();
  }
});

test('exploration cancellation never sends a write or changes the claimed task or saved answer', async () => {
  for (const extra of [{ reviewMode: 'AI' }, { reviewMode: 'HUMAN' }, { completionMode: 'learning' }, { completionMode: 'checkin' }]) {
    const h = hooks(), posts = [], current = { ...task, ...extra };
    const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
      fetch: async (_url, options) => {
        if (options?.method === 'POST') posts.push(JSON.parse(options.body));
        return response({ items: [current] });
      },
      window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
      document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
    });
    const render = () => h.render(() => useExplorationTasks(true));
    render(); h.commit(); await settle();
    const before = render().tasks[0];
    assert.equal(await render().mutate(current, 'cancel', '尚未保存的修改'), null);
    assert.equal(await render().mutate(current, 'cancel', ''), null);
    const after = render();
    assert.equal(posts.length, 0);
    assert.equal(after.tasks[0], before);
    assert.equal(after.tasks[0].answer, answer);
    assert.equal(after.tasks[0].status, 'active');
    assert.equal(after.busy, false);
    assert.match(after.error, /探索营任务接取后不能取消/);
    h.unmount();
  }
});

test('AI assessment actions retain drafts and document input without rendering a manual submit button', async () => {
  const h = hooks(), SelfCheck = () => null, commands = [], edits = [];
  const { ExplorationAiAssessmentActions } = load('ExplorationTaskHall.tsx', { react: h.react,
    './ExplorationSelfCheck': { ExplorationSelfCheck: SelfCheck }, 'react-dom': { createPortal: node => node },
  });
  const props = { task, answer, busy: false, savedMessage: '', hasNext: true,
    onAnswer: value => edits.push(value), onAction: async command => { commands.push(command); return true; }, onRun: async () => null, onContinue() {} };
  const render = patch => h.render(() => ExplorationAiAssessmentActions({ ...props, ...patch }));
  let tree = render();
  assert.equal(find(tree, node => node.type === 'button' && node.props.type === 'submit'), undefined);
  const html = renderToStaticMarkup(tree);
  assert.doesNotMatch(html, /提交审核|人工审核|取消接取|暂不取消/);
  const input = find(tree, node => node.type === 'textarea');
  assert.equal(input.props.disabled, false);
  input.props.onChange({ target: { value: 'https://team.feishu.cn/wiki/answer' } });
  assert.deepEqual(edits, ['https://team.feishu.cn/wiki/answer']);
  find(tree, node => node.type === 'button' && node.props.children === '保存草稿').props.onClick();
  assert.deepEqual(commands, ['draft']);
  assert.equal(find(tree, node => node.type === SelfCheck).key, `${task.id}:${task.versionId}`);
  tree = render({ task: { ...task, status: 'completed' } });
  assert.equal(find(tree, node => node.type === 'textarea').props.disabled, true);
  assert.match(renderToStaticMarkup(tree), /任务已完成，评测及完成记录已保存/);
  assert.equal(find(tree, node => node.type === 'button' && node.props.children === '保存草稿'), undefined);
  assert.match(renderToStaticMarkup(tree), /进入下一板块/);
  h.unmount();
});

test('an unconfirmed self-check request reuses its key and original revision until a terminal result arrives', async () => {
  const h = hooks(), posts = []; let sequence = 0;
  const doc = 'https://team.feishu.cn/docx/answer';
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    crypto: { randomUUID: () => `check-${++sequence}` },
    fetch: async (_url, options) => {
      if (options?.method !== 'POST') return response({ items: [{ ...task, revision: 8 }] });
      posts.push(JSON.parse(options.body));
      if (posts.length === 1) throw new Error('Connection lost after the server accepted the request');
      return response({ record: record('retry', { body: doc, inputKind: 'document', commentStatus: posts.length === 2 ? 'SENT' : 'UNCERTAIN' }),
        items: [record('retry')], task: { ...task, revision: 9 } });
    },
    window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  render(); h.commit(); await settle();
  assert.equal(await render().runSelfCheck(task, doc), null);
  await render().refresh();
  assert.equal(render().tasks[0].revision, 8);
  await render().runSelfCheck({ ...task, revision: 8 }, doc);
  assert.equal(posts[0].key, posts[1].key);
  assert.equal(posts[1].revision, task.revision, 'Replay uses the original revision after a catalog refresh');
  await render().runSelfCheck({ ...task, revision: 9 }, doc);
  assert.notEqual(posts[2].key, posts[1].key, 'A completed check permits a new intentional check');
  await render().runSelfCheck({ ...task, revision: 10 }, doc);
  assert.equal(posts[3].key, posts[2].key, 'Uncertain delivery only queries its original idempotent request');
  assert.equal(posts[3].revision, 9);
  await render().runSelfCheck(task, '新的文字成果');
  assert.notEqual(posts[4].key, posts[3].key, 'A different input has an independent request');
  h.unmount();
});

test('a rejected stale-revision self check can retry with the refreshed revision and a new key', async () => {
  const h = hooks(), posts = []; let sequence = 0;
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    crypto: { randomUUID: () => `check-${++sequence}` },
    fetch: async (_url, options) => {
      if (options?.method !== 'POST') return response({ items: [{ ...task, revision: 8 }] });
      posts.push(JSON.parse(options.body));
      if (posts.length === 1) return { ...response({ error: 'VERSION_CONFLICT' }, false), status: 409 };
      if (posts.length === 2) return { ...response({ error: 'Unexpected response after processing' }, false), status: 502 };
      return response({ record: record(), items: [record()], task: { ...task, revision: 9 } });
    },
    window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  render(); h.commit(); await settle();
  assert.equal(await render().runSelfCheck(task, answer), null);
  await render().refresh();
  assert.equal(await render().runSelfCheck(render().tasks[0], answer), null);
  assert.notEqual(posts[1].key, posts[0].key);
  assert.equal(posts[1].revision, 8);
  await render().runSelfCheck({ ...task, revision: 10 }, answer);
  assert.equal(posts[2].key, posts[1].key, 'A 5xx response still preserves the possible side effect request');
  assert.equal(posts[2].revision, 8);
  h.unmount();
});

test('AI assessment uses its own scoring form while manual assessments retain submission without an AI slot', () => {
  const h = hooks(), Form = () => null, SelfCheck = () => null;
  const { ExplorationTaskHall, ExplorationAiAssessmentActions } = load('ExplorationTaskHall.tsx', { react: h.react,
    './ExplorationLearningActions': { ExplorationAssessmentActions: Form }, './ExplorationSelfCheck': { ExplorationSelfCheck: SelfCheck },
    './useVillageTasks': { isVillageTaskClaimed: item => item.status !== 'available' },
  });
  const runCalls = [];
  const shared = { tasks: [{ ...task, materials: [], requirements: [], criteria: [] }], loading: false, error: '', busy: false, refresh() {}, mutate() {}, runSelfCheck(...args) { runCalls.push(args); return Promise.resolve(null); } };
  const render = () => h.render(() => ExplorationTaskHall({ detailOnly: true, initialTaskId: task.id, sharedExploration: shared }));
  const form = find(render(), node => node.type === ExplorationAiAssessmentActions);
  assert.equal(form.key, task.id);
  assert.equal(find(render(), node => node.type === Form), undefined);
  form.props.onRun();
  assert.equal(runCalls[0][0].id, task.id); assert.equal(runCalls[0][1], answer);
  shared.tasks[0] = { ...shared.tasks[0], revision: 5 };
  assert.equal(find(render(), node => node.type === ExplorationAiAssessmentActions).key, form.key);
  shared.tasks[0] = { ...shared.tasks[0], reviewMode: 'HUMAN' };
  const manual = find(render(), node => node.type === Form);
  assert.equal(manual.props.beforeActions, null);
  assert.equal(find(render(), node => node.type === ExplorationAiAssessmentActions), undefined);
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
  const { ExplorationTaskHall, ExplorationAiAssessmentActions } = load('ExplorationTaskHall.tsx', { react: h.react,
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
  return { ...h, shared, Learning, Assessment, Entry, Material, AiAssessment: ExplorationAiAssessmentActions,
    get blocked() { return blocked; }, get closed() { return closed; },
    render: (patch = {}) => { Object.assign(props, patch); return h.render(() => ExplorationTaskHall(props)); } };
}

test('closing and reopening an in-flight AI task preserves the single request and restores its final feedback', async () => {
  const owner = hooks(), post = deferred(), posts = [];
  const currentTask = { ...task, materials: [], requirements: [], criteria: [] };
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: owner.react }, {
    crypto: { randomUUID: () => 'retained-check' },
    fetch: async (_url, options) => {
      if (options?.method === 'POST') { posts.push(options); return post.promise; }
      return response({ items: [currentTask] });
    },
    window: { setInterval: () => 1, addEventListener() {}, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const flow = () => owner.render(() => useExplorationTasks(true));
  flow(); owner.commit(); await settle();
  const hall = detailHarness([currentTask], currentTask.id, flow());
  const operation = flow().runSelfCheck(currentTask, answer);
  Object.assign(hall.shared, flow());
  let tree = hall.render();
  let form = find(tree, node => node.type === hall.AiAssessment);
  assert.equal(form.props.busy, true);
  assert.equal(form.props.selfCheckPending, true);
  const close = find(tree, node => node.props?.['aria-label'] === '关闭探索任务详情');
  assert.equal(close.props.disabled, false);
  close.props.onClick();
  tree = hall.render({ initialTaskId: undefined }); hall.commit();
  assert.equal(find(tree, node => node.type === hall.AiAssessment), undefined);
  assert.equal(hall.closed, 1);
  assert.equal(flow().selfCheckState.pending, true);
  assert.equal(await flow().runSelfCheck(currentTask, answer), null);
  assert.equal(posts.length, 1);
  assert.equal(posts[0].signal, undefined, 'Closing the modal must not abort its retained request');

  hall.render({ initialTaskId: currentTask.id }); hall.commit();
  form = find(hall.render(), node => node.type === hall.AiAssessment);
  assert.equal(form.props.selfCheckPending, true);
  find(hall.render(), node => node.props?.['aria-label'] === '关闭探索任务详情').props.onClick();
  hall.render({ initialTaskId: undefined }); hall.commit();
  const completedRecord = record('finished-while-closed', { score: 40, passed: false });
  post.resolve(response({ record: completedRecord, items: [completedRecord], task: currentTask }));
  await operation;
  Object.assign(hall.shared, flow());
  assert.equal(hall.shared.busy, false);
  assert.equal(hall.shared.selfCheckState.pending, false);
  hall.render({ initialTaskId: currentTask.id }); hall.commit();
  form = find(hall.render(), node => node.type === hall.AiAssessment);
  assert.equal(form.props.selfCheckPending, false);
  assert.equal(form.props.selfCheckRecords[0].id, 'finished-while-closed');
  assert.equal(posts.length, 1, 'Reopening only retrieves the existing evaluation');
  hall.unmount(); owner.unmount();
});

test('only AI generation unlocks modal dismissal while submission and draft writes remain protected', () => {
  const currentTask = { ...task, materials: [], requirements: [], criteria: [] };
  for (const pending of [false, true]) {
    const hall = detailHarness([currentTask], currentTask.id, {
      busy: true, selfCheckState: { taskId: task.id, versionId: task.versionId, pending },
    });
    const tree = hall.render();
    const close = find(tree, node => node.props?.['aria-label'] === '关闭探索任务详情');
    assert.equal(close.props.disabled, !pending);
    let prevented = false;
    find(tree, node => node.type === 'dialog').props.onCancel({ preventDefault() { prevented = true; } });
    assert.equal(prevented, !pending);
    assert.equal(hall.closed, pending ? 1 : 0);
    hall.unmount();
  }
});

test('a running evaluation is restored only for its own task and published version', () => {
  const otherTask = { ...task, id: 'other-task', materials: [], requirements: [], criteria: [] };
  for (const state of [
    { taskId: task.id, versionId: task.versionId, pending: true, items: [record()] },
    { taskId: otherTask.id, versionId: 'old-version', pending: true, items: [record()] },
  ]) {
    const hall = detailHarness([otherTask], otherTask.id, { busy: true, selfCheckState: state });
    const form = find(hall.render(), node => node.type === hall.AiAssessment);
    assert.equal(form.props.selfCheckPending, undefined);
    assert.equal(form.props.selfCheckRecords, undefined);
    hall.unmount();
  }
});

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

test('review notification opens and focuses only the explicitly requested task feedback', () => {
  const h = hooks(), calls = [];
  const { ExplorationTaskHall } = load('ExplorationTaskHall.tsx', { react: h.react,
    './useVillageTasks': { isVillageTaskClaimed: item => !!item.assignmentId } });
  const reviewed = { ...task, status: 'returned', reviewMode: 'HUMAN', completionMode: 'assessment', materials: [], requirements: [], criteria: [],
    feedback: { text: '请补充你的实际行动', at: '2026-11-18T10:00:00Z', decision: 'REQUEST_REVISION' } };
  const props = { detailOnly: true, initialTaskId: task.id, openFeedback: true,
    sharedExploration: { tasks: [reviewed], loading: false, error: '', busy: false } };
  const render = () => h.render(() => ExplorationTaskHall(props));
  let tree = render();
  const panel = find(tree, node => node.props?.className === 'ex-review-feedback');
  assert.equal(panel.props.tabIndex, -1);
  assert.equal(panel.props['aria-label'], '人工审核反馈');
  assert.match(renderToStaticMarkup(panel), /请补充你的实际行动/);
  const body = { scrollTop: 20 };
  const element = { open: false, querySelector: () => body, showModal() { this.open = true; }, close() { this.open = false; } };
  find(tree, node => node.type === 'dialog').props.ref.current = element;
  panel.props.ref.current = { scrollIntoView: options => calls.push(['scroll', options.block]), focus: options => calls.push(['focus', options.preventScroll]) };
  h.commit();
  assert.equal(element.open, true);
  assert.deepEqual(calls, [['scroll', 'center'], ['focus', true]]);
  props.openFeedback = false;
  tree = render(); h.commit();
  assert.equal(calls.length, 2, 'Opening a task normally does not jump to review feedback');
  props.openFeedback = true;
  props.initialTaskId = 'other-task';
  render(); h.commit();
  assert.equal(calls.length, 2, 'The previous task feedback must not be focused for a different notification target');
  h.unmount();
});

test('exploration feedback titles respect immutable AI or human source and fall back for older records', () => {
  for (const [reviewMode, source, ai] of [['HUMAN', 'AI', true], ['AI', 'HUMAN', false],
    ['AI', undefined, true], ['HUMAN', undefined, false]]) {
    const current = { ...task, status: 'completed', reviewMode, materials: [], requirements: [], criteria: [],
      feedback: { text: '按真实评分标准完成。', at: '2026-11-18T10:00:00Z', decision: 'PASS', source } };
    const h = detailHarness([current], current.id);
    const panel = find(h.render(), node => node.props?.className === 'ex-review-feedback');
    assert.equal(panel.props['aria-label'], ai ? 'AI 评测反馈' : '人工审核反馈');
    const html = renderToStaticMarkup(panel);
    assert.match(html, ai ? /AI 评测通过 · 这一步完成了/ : /审核通过 · 这一步完成了/);
    if (!ai) assert.doesNotMatch(html, /AI 评测通过/);
    h.unmount();
  }
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
  h.render(); h.commit();
  const continued = find(h.render(), node => node.type === h.Learning);
  assert.equal(continued.props.task.id, next.id);
  assert.equal(continued.props.task.status, 'active');
  assert.equal(continued.props.busy, false);
  h.unmount();
});

test('a learning reward suspends the completed task and waits for collection before entering the next task once', async () => {
  const first = { ...task, id: 'first', order: 1, completionMode: 'learning', materials: [] };
  const next = { ...task, id: 'next', order: 2, status: 'locked', completionMode: 'learning', materials: [] };
  let completions = 0, refreshes = 0;
  const h = detailHarness([first, next], first.id, {
    completeLearning: async () => { completions++; return { ...first, status: 'completed' }; },
    refresh: async () => {
      refreshes++;
      h.shared.tasks = [{ ...first, status: 'completed' }, { ...next, status: 'active' }];
      return h.shared.tasks;
    },
  });
  const events = [];
  const nativeDialog = {
    open: false,
    showModal() { this.open = true; events.push('open-task'); },
    close() { this.open = false; events.push('hide-task'); },
    querySelector: () => null,
  };
  let tree = h.render();
  find(tree, node => node.type === 'dialog').props.ref.current = nativeDialog;
  h.commit();
  assert.equal(nativeDialog.open, true);
  await find(tree, node => node.type === h.Learning).props.onComplete(false);
  tree = h.render({ suspended: true }); h.commit();
  assert.equal(nativeDialog.open, false, 'The task dialog must leave the top layer for the chest');
  assert.equal(find(tree, node => node.type === h.Learning).props.task.id, first.id);
  assert.equal(find(tree, node => node.type === h.Learning).props.task.status, 'completed');
  assert.equal(find(tree, node => node.type === h.Learning).props.busy, true);
  h.shared.busy = true;
  tree = h.render(); h.commit();
  assert.equal(nativeDialog.open, false, 'Acknowledgment writes must not reopen the task over the chest');
  assert.equal(find(tree, node => node.type === h.Learning).props.task.id, first.id);
  h.shared.busy = false;
  tree = h.render(); h.commit();
  assert.equal(find(tree, node => node.type === h.Learning).props.task.id, first.id, 'A failed acknowledgment still waits');
  h.render({ suspended: false }); h.commit();
  tree = h.render(); h.commit();
  assert.equal(find(tree, node => node.type === h.Learning).props.task.id, next.id);
  assert.equal(nativeDialog.open, true);
  h.render(); h.commit();
  assert.equal(completions, 1);
  assert.equal(refreshes, 1);
  assert.deepEqual(events, ['open-task', 'hide-task', 'open-task']);
  h.unmount();
});

test('completion holds the treasure gate through catalog refresh and waits for the parent presentation decision', async () => {
  for (const dropped of [false, true]) {
    const first = { ...task, id: 'first', order: 1, completionMode: 'learning', materials: [] };
    const next = { ...first, id: 'next', order: 2, status: 'locked' };
    const fresh = deferred(), transitions = [];
    const report = busy => transitions.push(busy);
    const h = detailHarness([first, next], first.id, {
      completeLearning: async () => {
        h.shared.tasks = [{ ...first, status: 'completed' }, next];
        return h.shared.tasks[0];
      },
      refresh: async () => { h.shared.tasks = await fresh.promise; return h.shared.tasks; },
    });
    let tree = h.render({ onTransitionBusyChange: report });
    h.commit();
    const completing = find(tree, node => node.type === h.Learning).props.onComplete(false);
    await settle();
    tree = h.render(); h.commit();
    assert.equal(transitions.at(-1), true, 'The parent cannot start chest acknowledgment during catalog refresh');
    assert.equal(find(tree, node => node.type === h.Learning).props.task.id, first.id);
    fresh.resolve([{ ...first, status: 'completed' }, { ...next, status: 'active' }]);
    await completing;
    h.render({ continuationReady: false }); h.commit();
    assert.equal(transitions.at(-1), false);
    assert.equal(find(h.render(), node => node.type === h.Learning).props.task.id, first.id,
      'The old render must not continue before the parent decides whether to present a treasure');
    h.render({ continuationReady: true, suspended: dropped }); h.commit();
    tree = h.render();
    assert.equal(find(tree, node => node.type === h.Learning).props.task.id, dropped ? first.id : next.id);
    if (dropped) {
      h.render({ suspended: false }); h.commit();
      assert.equal(find(h.render(), node => node.type === h.Learning).props.task.id, next.id);
    }
    h.unmount();
  }
});

test('resuming after a chest uses the current task catalog when the next task was archived', async () => {
  const first = { ...task, id: 'first', order: 1, completionMode: 'learning', materials: [] };
  const next = { ...first, id: 'next', order: 2 };
  const remaining = { ...first, id: 'remaining', order: 3 };
  const done = { ...first, status: 'completed' };
  const h = detailHarness([first, next, remaining], first.id, {
    completeLearning: async () => { h.shared.tasks = [done, next, remaining]; return done; },
  });
  await find(h.render(), node => node.type === h.Learning).props.onComplete(false);
  h.render({ suspended: true }); h.commit();
  h.shared.tasks = [done, remaining];
  h.render({ suspended: false }); h.commit();
  assert.equal(find(h.render(), node => node.type === h.Learning).props.task.id, remaining.id);
  h.unmount();
});

test('a reward pauses AI and human task dialogs without losing input or advancing their selection', () => {
  for (const reviewMode of ['AI', 'HUMAN']) {
    const current = { ...task, reviewMode, materials: [], requirements: [], criteria: [] };
    const h = detailHarness([current], current.id);
    const formType = reviewMode === 'AI' ? h.AiAssessment : h.Assessment;
    let tree = h.render();
    find(tree, node => node.type === formType).props.onAnswer('尚未保存的输入需要保留');
    tree = h.render({ suspended: true }); h.commit();
    assert.equal(find(tree, node => node.type === formType).props.answer, '尚未保存的输入需要保留');
    assert.equal(find(tree, node => node.type === formType).props.busy, true);
    tree = h.render({ suspended: false }); h.commit();
    const resumed = find(h.render(), node => node.type === formType);
    assert.equal(resumed.props.task.id, current.id);
    assert.equal(resumed.props.answer, '尚未保存的输入需要保留');
    assert.equal(resumed.props.busy, false);
    assert.equal(h.closed, 0);
    h.unmount();
  }
});

test('closing or selecting another task while a reward waits cancels the old automatic continuation', async () => {
  for (const leave of ['close', 'switch', 'switch-on-resume', 'version']) {
    const first = { ...task, id: 'first', order: 1, completionMode: 'learning', materials: [] };
    const next = { ...task, id: 'next', order: 2, status: 'active', completionMode: 'learning', materials: [] };
    const other = { ...next, id: 'other', order: 3 };
    const h = detailHarness([first, next, other], first.id, {
      completeLearning: async () => { const done = { ...first, status: 'completed' }; h.shared.tasks = [done, next, other]; return done; },
    });
    const initial = h.render(); h.commit();
    await find(initial, node => node.type === h.Learning).props.onComplete(false);
    if (leave === 'close') {
      find(h.render(), node => node.props?.['aria-label'] === '关闭探索任务详情').props.onClick();
      h.render({ initialTaskId: undefined, suspended: true }); h.commit();
    } else if (leave === 'switch') {
      h.render({ initialTaskId: other.id, suspended: true }); h.commit();
      h.render(); h.commit();
    } else if (leave === 'switch-on-resume') {
      h.render({ suspended: true }); h.commit();
      h.render({ initialTaskId: other.id, suspended: false }); h.commit();
    } else {
      h.shared.tasks = h.shared.tasks.map(item => item.id === first.id ? { ...item, versionId: 'new-version' } : item);
      h.render({ suspended: true }); h.commit();
    }
    h.render({ suspended: false }); h.commit();
    const form = find(h.render(), node => node.type === h.Learning);
    if (leave === 'close') assert.equal(form, undefined);
    else assert.equal(form.props.task.id, leave.startsWith('switch') ? other.id : first.id);
    h.unmount();
  }
});

test('collecting the final signout reward closes the finished task without repeating completion', async () => {
  const last = { ...task, id: 'signout', order: 8, completionMode: 'checkin', materials: [] };
  let completions = 0;
  const h = detailHarness([last], last.id, {
    completeLearning: async (_task, confirmed) => {
      assert.equal(confirmed, true);
      completions++;
      h.shared.tasks = [{ ...last, status: 'completed' }];
      return h.shared.tasks[0];
    },
  });
  await find(h.render(), node => node.type === h.Learning).props.onComplete(true);
  h.render({ suspended: true }); h.commit();
  assert.equal(h.closed, 0);
  h.render({ suspended: false }); h.commit();
  assert.equal(h.closed, 1);
  assert.equal(find(h.render(), node => node.type === h.Learning), undefined);
  assert.equal(completions, 1);
  h.unmount();
});

test('assessment submission refreshes the next lock state before the learner can continue', async () => {
  const first = { ...task, order: 1, reviewMode: 'HUMAN', completionMode: 'assessment', claimed: true };
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
  const manual = { ...task, reviewMode: 'HUMAN' };
  const updated = { ...manual, status: 'pending', revision: 5 };
  const fresh = [updated, { ...next, status: 'active' }];
  const { useExplorationTasks } = load('ExplorationTaskHall.tsx', { react: h.react }, {
    crypto: { randomUUID: () => 'submission-key' },
    fetch: (_url, options) => {
      if (options?.method === 'POST') return Promise.resolve(response(updated));
      reads++;
      return reads === 1 ? Promise.resolve(response({ items: [manual, next] })) : reads === 2 ? oldRead.promise : freshRead.promise;
    },
    window: { setInterval: callback => { poll = callback; return 1; }, addEventListener: (event, callback) => { listeners[event] = callback; }, removeEventListener() {} },
    document: { hidden: false, addEventListener() {}, removeEventListener() {} }, clearInterval() {},
  });
  const render = () => h.render(() => useExplorationTasks(true));
  render(); h.commit(); await settle();
  const flow = render();
  const obsolete = flow.refresh();
  assert.equal((await flow.mutate(manual, 'submit', answer)).status, 'pending');
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
    const current = { ...task, status, reviewMode: 'HUMAN', claimed: status !== 'locked', completionMode: 'assessment',
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
