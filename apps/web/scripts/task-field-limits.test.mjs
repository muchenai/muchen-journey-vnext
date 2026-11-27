import test from 'node:test';
import assert from 'node:assert/strict';
import {validateTaskFieldLimits, taskFieldLength} from '../public/review-native/task-field-limits.js';
import {validateTask} from '../public/review-native/core.js';
import {ApiStore} from '../public/review-native/native-api.js';

const task = (title = '任务标题', summary = '用于验证任务发布长度边界的简述') => ({
  id: '00000000-0000-4000-8000-000000000001', revision: 0, title, summary,
  difficulty: '入门', publishingDepartment: '开发部', reviewMode: 'manual',
  badges: [{id: 'product', weight: 100}], materials: [{id: 'one', name: '学习材料', type: 'link', url: 'https://example.com'}],
});

for (const [field, limit, label] of [['title', 60, '任务标题'], ['summary', 400, '任务简述']]) {
  test(`${field} accepts the limit and rejects one character over for publication`, () => {
    for (const length of [limit - 1, limit, limit + 1]) {
      const input = {...task(), [field]: '字'.repeat(length)};
      const before = structuredClone(input);
      const expected = length <= limit ? [] : [`${label}不能超过 ${limit} 字`];
      assert.deepEqual(validateTaskFieldLimits(input), expected);
      assert.deepEqual(validateTask(input), expected);
      assert.deepEqual(input, before);
    }
  });
  test(`${field} counts whitespace and supplementary characters like native maxlength`, () => {
    assert.equal(taskFieldLength('😀'), 2);
    assert.deepEqual(validateTaskFieldLimits({...task(), [field]: '😀'.repeat(limit / 2)}), []);
    for (const value of ['😀'.repeat(limit / 2) + '字', ' ' + '字'.repeat(limit), '字'.repeat(limit) + ' ', '\n' + '字'.repeat(limit)]) {
      assert.deepEqual(validateTaskFieldLimits({...task(), [field]: value}), [`${label}不能超过 ${limit} 字`]);
    }
  });
}

test('empty drafts remain saveable while publication keeps its minimum requirements', () => {
  assert.deepEqual(validateTaskFieldLimits(task('', '')), []);
  assert.deepEqual(validateTask(task('', '')), ['任务标题至少需要 3 个字', '任务简述至少需要 10 个字，当前 0 个字']);
});

test('real draft adapter rejects oversized content without requests, mutation or truncation', async () => {
  const store = new ApiStore();store.operatorId = 'operator';
  const original = task();store.data = {draft: original, tasks: []};
  const fetchBefore = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => {requests++;throw new Error('Unexpected request');};
  try {
    for (const [title, summary, message] of [
      ['字'.repeat(61), '描述'.repeat(10), '任务标题不能超过 60 字'],
      ['标题', '字'.repeat(401), '任务简述不能超过 400 字'],
      ['字'.repeat(80), '字'.repeat(500), '任务标题不能超过 60 字；任务简述不能超过 400 字'],
    ]) {
      const draft = task(title, summary), before = structuredClone(draft);
      await assert.rejects(store.saveTask(draft), {message});
      assert.deepEqual(draft, before);assert.equal(store.data.draft, original);
    }
    assert.equal(requests, 0);
  } finally {globalThis.fetch = fetchBefore;}
});

test('valid boundary and empty drafts reach persistence intact', async () => {
  const store = new ApiStore();store.operatorId = 'operator';store.data = {tasks: []};
  store.save = () => {};store.refresh = async () => {};
  const fetchBefore = globalThis.fetch, writes = [];
  globalThis.fetch = async (_url, options) => {
    const body = JSON.parse(options.body);writes.push(body);
    return Response.json({ok: true, data: {...body.task, authorId: store.operatorId, revision: 1, status: 'draft'}});
  };
  try {
    for (const draft of [task('字'.repeat(60), '字'.repeat(400)), task('', '')]) {
      const saved = await store.saveTask(draft);
      assert.equal(saved.title, draft.title);assert.equal(saved.summary, draft.summary);
    }
    assert.equal(writes.length, 2);
    assert.ok(writes.every(write => write.command === 'saveTask'));
  } finally {globalThis.fetch = fetchBefore;}
});
