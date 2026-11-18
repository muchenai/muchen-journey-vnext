import test from 'node:test';
import assert from 'node:assert/strict';
import {File} from 'node:buffer';
import {normalizeRubricFile, rubricAttachmentErrors, RUBRIC_MAX_BYTES} from '../public/review-native/rubric-materials.js';
import {validateTask} from '../public/review-native/core.js';

globalThis.File ||= File;

test('scoring uploads normalize actual browser MIME by supported extension', () => {
  for (const [name, type] of [['答案.txt', 'text/plain'], ['答案.md', 'text/markdown'],
    ['答案.PDF', 'application/pdf'], ['答案.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']]) {
    const normalized = normalizeRubricFile(new File(['answer B'], name));
    assert.equal(normalized.name, name);
    assert.equal(normalized.type, type);
    assert.equal(normalized.size, 8);
  }
});

test('legacy DOC, empty files, more than four and oversize fail at selection', () => {
  assert.throws(() => normalizeRubricFile(new File(['doc'], '答案.doc')), /转换为 DOCX/);
  assert.throws(() => normalizeRubricFile(new File([], 'empty.txt')), /不能为空/);
  assert.throws(() => normalizeRubricFile(new File(['a'], '答案.txt'), 4), /4 份/);
  assert.throws(() => normalizeRubricFile(new File([new Uint8Array(RUBRIC_MAX_BYTES + 1)], '答案.txt')), /2 MB/);
  assert.throws(() => normalizeRubricFile(new File(['data'], 'unknown.exe')), /仅支持/);
});

test('restored scoring attachment metadata is checked before publishing', () => {
  assert.deepEqual(rubricAttachmentErrors([{name: '答案.txt', type: 'file', size: 1}]), []);
  assert.match(rubricAttachmentErrors([{name: '答案.doc', type: 'file', size: 1}]).join(), /转换为 DOCX/);
  assert.match(rubricAttachmentErrors(Array(5).fill({name: '答案.txt', type: 'file', size: 1})).join(), /4 份/);
});

test('AI publishing rejects invalid scoring dimensions and attachment metadata', () => {
  const task = {camp: 'exploration', title: '评分测试任务', summary: '请阅读材料并完成本次测试任务。',
    order: 1, completionMode: 'assessment', materials: [{name: '材料', type: 'link', url: 'https://example.com/read'}],
    taskFiles: [{name: '题目', type: 'link', url: 'https://example.com/task'}], reviewMode: 'ai', passScore: 60,
    rubric: [{id: 'a', name: '正确性', points: 100, description: '标准答案为 B。'}], rubricAttachments: []};
  assert.deepEqual(validateTask(task), []);
  assert.match(validateTask({...task, rubric: [{...task.rubric[0], points: 0}]}).join(), /大于 0/);
  assert.match(validateTask({...task, rubric: [{...task.rubric[0], points: 101}]}).join(), /不超过 100/);
  assert.match(validateTask({...task, rubric: [{...task.rubric[0], points: 33.333},
    {...task.rubric[0], id: 'b', points: 66.667}]}).join(), /两位小数/);
  assert.match(validateTask({...task, passScore: 60.001}).join(), /两位小数/);
  assert.match(validateTask({...task, rubric: Array(13).fill(task.rubric[0])}).join(), /12 个/);
  assert.match(validateTask({...task, rubricAttachments: Array(5).fill({name: '答案.txt', type: 'file', size: 1})}).join(), /4 份/);
});
