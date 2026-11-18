import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import * as jsxRuntime from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const code = ts.transpileModule(readFileSync(new URL('../src/app/project29/ExplorationTreasureExperience.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const catalog = [
  { id: 'compass', name: '晨光罗盘', subtitle: '方向，由你发现', description: '让每一步探索，都有自己的方向。', color: 'cyan' },
  { id: 'crystal', name: '共鸣晶石', subtitle: '让理解产生共鸣', description: '连接你的理解与组织的价值。', color: 'violet' },
  { id: 'starmap', name: '协作星图', subtitle: '看见彼此的连接', description: '找到属于你的协作坐标。', color: 'blue' },
  { id: 'key', name: '远航密钥', subtitle: '下一程，已准备好', description: '带上收获，开启下一段成长。', color: 'gold' },
];
const drop = (id = 'drop-one', treasureId = 'compass') => ({ id, treasureId, taskId: 'task-one', taskTitle: '写给Muchener的信', discoveredAt: '2026-11-16T11:12:13Z', acknowledgedAt: null });
const state = (items = [], pendingDrops = items) => ({ total: 4, count: items.length, items, pendingDrops });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const settle = () => new Promise(resolve => setImmediate(resolve));

function hooks() {
  const slots = []; let cursor = 0; let effects = []; let id = 0; let mounted = true; let updatesAfterUnmount = 0;
  const same = (a, b) => a && b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
  return {
    react: {
      useState(initial) { const index = cursor++; if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial; return [slots[index], value => { if (!mounted) updatesAfterUnmount++; slots[index] = typeof value === 'function' ? value(slots[index]) : value; }]; },
      useRef(initial) { return slots[cursor++] ??= { current: initial }; },
      useId() { return `test-treasure-${++id}`; },
      useEffect(callback, dependencies) { const index = cursor++; if (!slots[index] || !same(slots[index].dependencies, dependencies)) { const previous = slots[index]; slots[index] = { dependencies }; effects.push(() => { previous?.cleanup?.(); slots[index].cleanup = callback(); }); } },
    },
    render(callback) { cursor = 0; return callback(); },
    commit() { const pending = effects; effects = []; pending.forEach(effect => effect()); },
    unmount() { mounted = false; slots.forEach(slot => slot?.cleanup?.()); },
    updatesAfterUnmount: () => updatesAfterUnmount,
  };
}
function find(node, predicate) {
  if (Array.isArray(node)) { for (const item of node) { const found = find(item, predicate); if (found) return found; } return undefined; }
  if (!node || typeof node !== 'object') return undefined;
  return predicate(node) ? node : find(node.props?.children, predicate);
}
const byClass = (tree, className) => find(tree, node => node.props?.className?.split(' ').includes(className));
const byLabel = (tree, label) => find(tree, node => node.props?.['aria-label'] === label);
function harness(initial = {}, { reduced = true } = {}) {
  const h = hooks(); let timer;
  const calls = []; const loadedModule = { exports: {} };
  vm.runInNewContext(code, { module: loadedModule, exports: loadedModule.exports,
    require: name => ({ react: h.react, 'react/jsx-runtime': jsxRuntime, '@/lib/exploration-treasures': { TREASURE_CATALOG: catalog } })[name] ?? {},
    window: { matchMedia: () => ({ matches: reduced }), setTimeout: callback => { timer = callback; return 1; }, clearTimeout() { timer = undefined; } },
  });
  const props = { treasures: state(), collectionOpen: true, canReveal: true, busy: false, onCollectionClose() { calls.push('close-collection'); }, onAcknowledge: async id => { calls.push(id); return true; }, ...initial };
  return { ...h, calls, props, render(patch = {}) { Object.assign(props, patch); return h.render(() => loadedModule.exports.ExplorationTreasureExperience(props)); }, fireTimer() { const callback = timer; timer = undefined; callback?.(); } };
}

test('collection presents four distinct empty slots and explains the exact task and cap rules', () => {
  const h = harness(), tree = h.render(), html = renderToStaticMarkup(tree);
  assert.equal(tree.props['data-mode'], 'collection');
  assert.equal((html.match(/class="treasure-collection-item"/g) || []).length, 4);
  assert.equal((html.match(/data-owned="false"/g) || []).length, 4);
  for (const treasure of catalog) assert.match(html, new RegExp(treasure.name));
  assert.match(html, /按后台排序，首次完成任务时结算/);
  assert.match(html, /首尾任务必掉/);
  assert.match(html, /另外两件宝藏/);
  assert.match(html, /每个任务结算一次，宝藏不重复/);
  assert.match(html, /已探索 0 个宝藏，共 4 个/);
  assert.equal(byLabel(tree, '晨光罗盘，等待探索').props.disabled, true);
});

test('owned treasures open their source and timestamp without fabricating other discoveries', () => {
  const discovery = drop(), h = harness({ treasures: state([discovery], []) });
  byLabel(h.render(), '查看晨光罗盘').props.onClick();
  const html = renderToStaticMarkup(h.render());
  assert.match(html, /收藏手记/);
  assert.match(html, /写给Muchener的信/);
  assert.match(html, /dateTime="2026-11-16T11:12:13Z"/i);
  assert.equal((html.match(/data-owned="true"/g) || []).length, 1);
  assert.equal((html.match(/data-owned="false"/g) || []).length, 3);
});

test('preview opens a sealed chest and returns to the collection without acknowledging or granting a treasure', async () => {
  const h = harness();
  byClass(h.render(), 'treasure-preview-button').props.onClick();
  let tree = h.render();
  assert.equal(tree.props['data-mode'], 'reveal');
  assert.match(renderToStaticMarkup(tree), /效果预览 · 不计入收集/);
  byClass(tree, 'treasure-primary').props.onClick();
  tree = h.render();
  assert.equal(byClass(tree, 'treasure-discovery').props['data-stage'], 'revealed');
  assert.match(renderToStaticMarkup(tree), /当前收集进度/);
  byClass(tree, 'treasure-primary').props.onClick();
  await settle();
  tree = h.render();
  assert.equal(tree.props['data-mode'], 'collection');
  assert.deepEqual(h.calls, []);
  assert.equal(h.props.treasures.count, 0);
});

test('pending discoveries wait for task dialogs and collection pages before they reveal', () => {
  const discovery = drop(), h = harness({ treasures: state([discovery]), collectionOpen: false, canReveal: false });
  let tree = h.render(); h.commit();
  assert.equal(h.render().props['data-mode'], 'closed');
  h.render({ canReveal: true, collectionOpen: true }); h.commit();
  assert.equal(h.render().props['data-mode'], 'collection');
  tree = h.render({ collectionOpen: false }); h.commit();
  tree = h.render();
  assert.equal(tree.props['data-mode'], 'reveal');
  assert.equal(byClass(tree, 'treasure-discovery').props['data-stage'], 'sealed');
  assert.match(renderToStaticMarkup(tree), /任务已完成/);
});

test('opening animation advances once and displays the actual granted treasure', () => {
  const discovery = drop('drop-key', 'key'), h = harness({ treasures: state([discovery]), collectionOpen: false }, { reduced: false });
  h.render(); h.commit();
  let tree = h.render(); h.commit();
  byClass(tree, 'treasure-primary').props.onClick();
  tree = h.render(); h.commit();
  assert.equal(byClass(tree, 'treasure-discovery').props['data-stage'], 'opening');
  assert.equal(byClass(tree, 'treasure-primary').props.disabled, true);
  h.fireTimer();
  tree = h.render();
  assert.equal(byClass(tree, 'treasure-discovery').props['data-stage'], 'revealed');
  assert.match(renderToStaticMarkup(tree), /远航密钥/);
  assert.match(renderToStaticMarkup(tree), /来自任务 · 写给Muchener的信/);
});

test('rapid close or collect clicks acknowledge a real discovery once and stale parent props do not reopen it', async () => {
  const pending = deferred(), calls = [], discovery = drop();
  const h = harness({ treasures: state([discovery]), collectionOpen: false, onAcknowledge: id => { calls.push(id); return pending.promise; } });
  h.render(); h.commit();
  let tree = h.render();
  const close = byClass(tree, 'treasure-close');
  close.props.onClick(); close.props.onClick();
  assert.deepEqual(calls, ['drop-one']);
  tree = h.render();
  assert.equal(byClass(tree, 'treasure-close').props.disabled, true);
  pending.resolve(true); await settle();
  tree = h.render(); h.commit();
  assert.equal(h.render().props['data-mode'], 'closed');
  assert.deepEqual(calls, ['drop-one']);
});

test('failed acknowledgment keeps the same discovery and offers a safe retry', async () => {
  let attempts = 0;
  const h = harness({ treasures: state([drop()]), collectionOpen: false, onAcknowledge: async () => ++attempts > 1 });
  h.render(); h.commit();
  let tree = h.render();
  byClass(tree, 'treasure-close').props.onClick(); await settle();
  tree = h.render();
  assert.equal(tree.props['data-mode'], 'reveal');
  assert.match(renderToStaticMarkup(tree), /宝藏已保留，暂未确认领取结果/);
  byClass(tree, 'treasure-text-button').props.onClick(); await settle();
  assert.equal(h.render().props['data-mode'], 'closed');
  assert.equal(attempts, 2);
});

test('escape delegates to acknowledgment and busy operations cannot dismiss or open the chest', async () => {
  const h = harness({ treasures: state([drop()]), collectionOpen: false });
  h.render(); h.commit();
  let tree = h.render({ busy: true }); let prevented = false;
  tree.props.onCancel({ preventDefault() { prevented = true; } });
  byClass(tree, 'treasure-primary').props.onClick();
  assert.equal(prevented, true);
  assert.equal(byClass(h.render(), 'treasure-discovery').props['data-stage'], 'sealed');
  assert.deepEqual(h.calls, []);
  tree = h.render({ busy: false });
  tree.props.onCancel({ preventDefault() {} }); await settle();
  assert.deepEqual(h.calls, ['drop-one']);
});

test('a failed acknowledgment can be deferred for this session without removing pending or owned data', async () => {
  const treasureState = state([drop()]), calls = [];
  const h = harness({ treasures: treasureState, collectionOpen: false, onAcknowledge: async id => { calls.push(id); return false; } });
  h.render(); h.commit();
  byClass(h.render(), 'treasure-close').props.onClick(); await settle();
  let tree = h.render();
  const deferButton = find(tree, node => node.type === 'button' && node.props.children === '稍后查看');
  assert.ok(deferButton);
  deferButton.props.onClick();
  tree = h.render(); h.commit();
  assert.equal(h.render().props['data-mode'], 'closed');
  assert.deepEqual(calls, ['drop-one']);
  assert.equal(treasureState.pendingDrops.length, 1);
  assert.equal(treasureState.items.length, 1);
  const refreshed = harness({ treasures: treasureState, collectionOpen: false });
  refreshed.render(); refreshed.commit();
  assert.equal(refreshed.render().props['data-mode'], 'reveal');
});

test('controlled presentations show only the coordinated drop and never consume other pending discoveries', () => {
  const discovery = drop(), later = drop('later-drop', 'key');
  const h = harness({ treasures: state([discovery, later]), collectionOpen: false, presentedDrop: null });
  h.render(); h.commit();
  assert.equal(h.render().props['data-mode'], 'closed');
  h.render({ presentedDrop: later }); h.commit();
  let tree = h.render();
  assert.equal(tree.props['data-mode'], 'reveal');
  assert.equal(byClass(tree, 'treasure-discovery').props['data-treasure'], 'key');
  byClass(tree, 'treasure-primary').props.onClick();
  tree = h.render();
  assert.match(renderToStaticMarkup(tree), /远航密钥/);
  assert.equal(h.calls.length, 0);
});

test('a controlled chest settles once only after acknowledgment and ignores stale parent data', async () => {
  const discovery = drop(), pending = deferred(), settled = [], acknowledgments = [];
  const h = harness({ treasures: state([discovery]), collectionOpen: false, presentedDrop: discovery,
    onDropSettled: id => settled.push(id),
    onAcknowledge: id => { acknowledgments.push(id); return pending.promise; } });
  h.render(); h.commit();
  const close = byClass(h.render(), 'treasure-close');
  close.props.onClick(); close.props.onClick();
  assert.deepEqual(acknowledgments, [discovery.id]);
  assert.deepEqual(settled, [], 'Task continuation waits until the acknowledgment succeeds');
  pending.resolve(true); await settle();
  h.render(); h.commit();
  assert.equal(h.render().props['data-mode'], 'closed');
  assert.deepEqual(settled, [discovery.id]);
  close.props.onClick(); await settle();
  assert.deepEqual(acknowledgments, [discovery.id]);
  assert.deepEqual(settled, [discovery.id]);
});

test('controlled acknowledgment failure retains the chest until success or explicit deferral', async () => {
  const discovery = drop(), settled = [];
  const h = harness({ treasures: state([discovery]), collectionOpen: false, presentedDrop: discovery,
    onDropSettled: id => settled.push(id), onAcknowledge: async () => false });
  h.render(); h.commit();
  byClass(h.render(), 'treasure-close').props.onClick(); await settle();
  let tree = h.render();
  assert.equal(tree.props['data-mode'], 'reveal');
  assert.deepEqual(settled, []);
  const later = find(tree, node => node.type === 'button' && node.props.children === '稍后查看');
  later.props.onClick(); later.props.onClick();
  h.render(); h.commit();
  assert.equal(h.render().props['data-mode'], 'closed');
  assert.deepEqual(settled, [discovery.id]);
  assert.equal(h.props.treasures.pendingDrops.length, 1, 'Deferral must not remove the saved discovery');
});

test('a newer controlled drop cannot replace an unopened chest before its current discovery settles', async () => {
  const first = drop(), second = drop('second', 'starmap'), settled = [];
  const h = harness({ treasures: state([first, second]), collectionOpen: false, presentedDrop: first,
    onDropSettled: id => settled.push(id) });
  h.render(); h.commit();
  h.render({ presentedDrop: second }); h.commit();
  let tree = h.render();
  assert.equal(byClass(tree, 'treasure-discovery').props['data-treasure'], first.treasureId);
  byClass(tree, 'treasure-close').props.onClick(); await settle();
  h.render(); h.commit();
  tree = h.render();
  assert.equal(byClass(tree, 'treasure-discovery').props['data-treasure'], second.treasureId);
  assert.deepEqual(settled, [first.id]);
});

test('unmounting during acknowledgment cannot resume a task or update an abandoned chest', async () => {
  const discovery = drop(), pending = deferred(), settled = [];
  const h = harness({ treasures: state([discovery]), collectionOpen: false, presentedDrop: discovery,
    onDropSettled: id => settled.push(id), onAcknowledge: () => pending.promise });
  h.render(); h.commit();
  byClass(h.render(), 'treasure-close').props.onClick();
  h.unmount();
  pending.resolve(true); await settle();
  assert.deepEqual(settled, []);
  assert.equal(h.updatesAfterUnmount(), 0);
});

test('controlled collection preview never settles or acknowledges a real discovery', async () => {
  const settled = [];
  const h = harness({ presentedDrop: null, onDropSettled: id => settled.push(id) });
  byClass(h.render(), 'treasure-preview-button').props.onClick();
  let tree = h.render();
  byClass(tree, 'treasure-primary').props.onClick();
  tree = h.render();
  byClass(tree, 'treasure-primary').props.onClick(); await settle();
  assert.equal(h.render().props['data-mode'], 'collection');
  assert.deepEqual(h.calls, []);
  assert.deepEqual(settled, []);
});
