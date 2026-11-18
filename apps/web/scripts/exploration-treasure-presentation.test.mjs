import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';

const code = ts.transpileModule(readFileSync(new URL('../src/app/project29/useExplorationTreasurePresentation.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const drop = (id = 'first', taskId = 'task-one') => ({
  id, taskId, taskTitle: taskId, treasureId: 'compass', discoveredAt: '2026-11-18T08:00:00Z', acknowledgedAt: null,
});
const treasures = (items = [], pendingDrops = items) => ({ total: 4, count: items.length, items, pendingDrops });
const same = (left, right) => left && right && left.length === right.length && left.every((item, index) => Object.is(item, right[index]));

function harness(initial = {}) {
  const slots = [];
  let cursor = 0, effects = [];
  const react = {
    useState(initialValue) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initialValue === 'function' ? initialValue() : initialValue;
      return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
    },
    useCallback(callback, dependencies) {
      const index = cursor++;
      if (!slots[index] || !same(slots[index].dependencies, dependencies)) slots[index] = { callback, dependencies };
      return slots[index].callback;
    },
    useEffect(callback, dependencies) {
      const index = cursor++;
      if (!slots[index] || !same(slots[index].dependencies, dependencies)) {
        const previous = slots[index];
        slots[index] = { dependencies };
        effects.push(() => { previous?.cleanup?.(); slots[index].cleanup = callback(); });
      }
    },
  };
  const loaded = { exports: {} };
  vm.runInNewContext(code, { module: loaded, exports: loaded.exports, require: name => ({ react })[name] ?? {} });
  const props = { treasures: treasures(), enabled: true, busy: false, collectionOpen: false, ...initial };
  return {
    props,
    render(patch = {}) {
      Object.assign(props, patch); cursor = 0;
      return loaded.exports.useExplorationTreasurePresentation(props);
    },
    commit() { const pending = effects; effects = []; pending.forEach(effect => effect()); },
  };
}

test('a new drop blocks continuation in its first render before any modal effect runs', () => {
  const first = drop(), h = harness();
  assert.equal(h.render().blocking, false);
  h.commit();
  const presentation = h.render({ treasures: treasures([first]) });
  assert.equal(presentation.drop, first);
  assert.equal(presentation.blocking, true, 'The task may not advance before the chest effect opens');
});

test('no drop, busy writes, disabled sections and an open collection do not start a new presentation', () => {
  for (const patch of [{ busy: true }, { enabled: false }, { collectionOpen: true }]) {
    const h = harness({ treasures: treasures([drop()]), ...patch });
    assert.equal(h.render().drop, null);
    assert.equal(h.render().blocking, false);
    h.commit();
  }
  const h = harness();
  h.render(); h.commit();
  assert.equal(h.render().blocking, false);
});

test('an active chest stays blocking during acknowledgment even if the server removes its pending record', () => {
  const first = drop(), h = harness({ treasures: treasures([first]) });
  h.render(); h.commit();
  let presentation = h.render({ busy: true, treasures: treasures([{ ...first, acknowledgedAt: '2026-11-18T08:01:00Z' }], []) });
  assert.equal(presentation.drop.id, first.id);
  assert.equal(presentation.blocking, true);
  h.commit();
  presentation = h.render({ busy: false });
  assert.equal(presentation.blocking, true, 'Only the settled callback releases the task');
  presentation.dismiss(first.id);
  assert.equal(h.render().blocking, false);
});

test('multiple pending discoveries stay in order without an unblocked frame between chests', () => {
  const first = drop(), second = drop('second', 'task-two');
  const h = harness({ treasures: treasures([first, second]) });
  h.render(); h.commit();
  h.render().dismiss(first.id);
  let presentation = h.render();
  assert.equal(presentation.drop.id, second.id);
  assert.equal(presentation.blocking, true);
  h.commit();
  presentation = h.render();
  presentation.dismiss(second.id);
  assert.equal(h.render().blocking, false);
  h.commit();
  assert.equal(h.render({ treasures: treasures([first, second]) }).blocking, false, 'Stale polls do not reopen acknowledged discoveries');
});

test('a deferred discovery is skipped only in the current presentation session', () => {
  const first = drop(), h = harness({ treasures: treasures([first]) });
  h.render(); h.commit();
  h.render().dismiss(first.id);
  assert.equal(h.render().blocking, false);
  assert.equal(h.props.treasures.count, 1);
  assert.equal(h.props.treasures.pendingDrops.length, 1);
  const reopened = harness({ treasures: h.props.treasures });
  assert.equal(reopened.render().drop.id, first.id, 'A later visit can show a discovery not yet confirmed by the server');
});

test('changing section or opening the collection does not discard a chest already being viewed', () => {
  const first = drop(), h = harness({ treasures: treasures([first]) });
  h.render(); h.commit();
  const presentation = h.render({ enabled: false, collectionOpen: true });
  assert.equal(presentation.drop.id, first.id);
  assert.equal(presentation.blocking, true);
  presentation.dismiss('another-discovery');
  assert.equal(h.render().drop.id, first.id);
});

test('an acknowledged entry erroneously retained in pending data cannot start a chest', () => {
  const first = { ...drop(), acknowledgedAt: '2026-11-18T08:01:00Z' };
  const h = harness({ treasures: treasures([first]) });
  assert.equal(h.render().drop, null);
  assert.equal(h.render().blocking, false);
});
