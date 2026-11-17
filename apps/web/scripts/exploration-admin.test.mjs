import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { validateTask, applyDifficultyPreset, rewardBreakdown } from '../public/review-native/core.js';
import { taskView, taskWrite } from '../public/review-native/native-model.js';
import { copyAsNewTask, editableContent, isTaskUpdate } from '../public/review-native/task-workflow.js';
import { EXPLORATION_MATERIAL_MAX_BYTES, localMaterialUrl, materialImagePreviewUrl, uploadExplorationMaterial } from '../public/review-native/exploration-material-files.js';
import { nextExplorationOrder } from '../public/review-native/exploration-order.js';
import { transferredFiles, normalizeLearningMaterialFile, isMaterialPasteTarget } from '../public/review-native/material-upload-input.js';
import { requiresTaskAssessment, validAssessmentUrl } from '../public/review-native/exploration-completion.js';
import { renderPublishMaterials } from '../public/review-native/publish-materials.js';

const task = mode => ({id: 'draft', camp: 'exploration', title: '测试探索营任务', summary: '这是一个用于验证新探索营任务的完整简述。',
  order: 1, completionMode: mode, assessmentUrl: '', materials: [], badges: [], rubric: [], reviewMode: 'manual'});

test('exploration completion modes drive materials and assessment requirements', () => {
  for (const mode of ['learning', 'checkin']) {
    assert.equal(requiresTaskAssessment(task(mode)), false);
    assert.deepEqual(validateTask(task(mode)), []);
  }
  assert.equal(requiresTaskAssessment(task('assessment')), true);
  assert.deepEqual(validateTask(task('assessment')), ['请至少添加一份学习材料', '请上传任务文件，或填写已有的测试链接']);
  assert.ok(validateTask(task('unknown')).includes('请选择有效的任务完成方式'));
  assert.equal(requiresTaskAssessment({camp: 'novice', completionMode: 'learning'}), true);
});

test('exploration has no department difficulty or badge reward requirements', () => {
  const normalized = applyDifficultyPreset({...task('learning'), difficulty: '挑战', publishingDepartment: '开发部', badges: [{id: 'product', weight: 100}]});
  assert.equal(normalized.difficulty, '');
  assert.equal(normalized.publishingDepartment, undefined);
  assert.deepEqual(normalized.badges, []);
  assert.deepEqual(rewardBreakdown(normalized), {xp: 0, taskPoints: 0, totalPoints: 0, allocations: []});
});

test('exploration publication validates order, links, material count and current shared field limits', () => {
  for (const order of [0, 1.5, 10000, '1']) assert.ok(validateTask({...task('learning'), order}).some(error => error.includes('任务排序')));
  for (const url of ['http://example.com', 'https://user:secret@example.com', 'javascript:alert(1)']) {
    assert.equal(validAssessmentUrl(url), false);
    assert.ok(validateTask({...task('assessment'), assessmentUrl: url}).some(error => error.includes('培训测试链接')));
  }
  assert.equal(validAssessmentUrl(''), true);
  assert.equal(validAssessmentUrl('https://example.com/test'), true);
  assert.ok(validateTask({...task('learning'), title: '字'.repeat(61)}).includes('任务标题不能超过 60 字'));
  assert.ok(validateTask({...task('learning'), summary: '字'.repeat(401)}).includes('任务简述不能超过 400 字'));
  assert.ok(validateTask({...task('learning'), materials: Array.from({length: 21}, (_, id) => ({id, name: '学习材料', type: 'link', url: 'https://example.com'}))}).includes('每个任务最多添加 20 份材料'));
});

test('exploration metadata survives adapters and copying resets published identity', () => {
  const source = {...task('assessment'), order: 3, publishedOrder: 2, assessmentUrl: 'https://example.com/test', version: 4, versionId: 'old-version', publishedAt: '2026-11-17', status: 'published'};
  assert.equal(taskView(taskWrite(source)).completionMode, 'assessment');
  assert.equal(taskWrite(source).assessmentUrl, source.assessmentUrl);
  assert.equal(editableContent(source).order, 3);
  const copy = copyAsNewTask(source, {id: 'new-task', order: 9});
  assert.equal(copy.id, 'new-task');
  assert.equal(copy.order, 9);
  assert.equal(copy.publishedOrder, undefined);
  assert.equal(copy.versionId, undefined);
  assert.equal(isTaskUpdate(copy), false);
  assert.equal(isTaskUpdate({versionId: 'saved-draft-version', status: 'draft'}), false);
  assert.equal(nextExplorationOrder([{camp: 'exploration', order: 1, status: 'published'}, {camp: 'novice', order: 100, status: 'published'}]), 2);
});

test('file uploads use raw bytes and authenticated material references', async () => {
  const previous = globalThis.fetch;
  const id = '00000000-0000-4000-8000-000000000001';
  const file = new File(['image-bytes'], '截图.png', {type: 'image/png'});
  let received;
  globalThis.fetch = async (url, options) => {
    received = {url, options};
    return {ok: true, json: async () => ({ok: true, data: {id, name: file.name, type: 'image', mime: file.type, size: file.size, url: `exploration-material:${id}`}})};
  };
  try {
    const uploaded = await uploadExplorationMaterial(file);
    assert.match(received.url, /^\/api\/review-native\/exploration\/materials\?name=/);
    assert.equal(received.options.body, file);
    assert.equal(received.options.credentials, 'same-origin');
    assert.equal(localMaterialUrl(uploaded.url), `/api/review-native/exploration/materials/${id}`);
    assert.equal(materialImagePreviewUrl(uploaded), `/api/review-native/exploration/materials/${id}?inline=1`);
    assert.equal(localMaterialUrl('javascript:alert(1)'), '');
    await assert.rejects(uploadExplorationMaterial({size: EXPLORATION_MATERIAL_MAX_BYTES + 1, name: 'too-large'}), /100 MB/);
  } finally { globalThis.fetch = previous; }
});

test('paste and drop preserve file order, reject folders and sanitize screenshot names', () => {
  const file = new File(['a'], 'image.png', {type: 'image/png'});
  const other = new File(['b'], 'other.txt', {type: 'text/plain'});
  const result = transferredFiles({types: ['Files'], items: [{kind: 'file', getAsFile: () => file}, {kind: 'file', webkitGetAsEntry: () => ({isDirectory: true, name: 'folder'})}], files: [file, other]});
  assert.deepEqual(result.files, [file, other]);
  assert.match(result.errors[0], /文件夹/);
  assert.match(normalizeLearningMaterialFile(file, {source: 'paste'}).name, /^粘贴图片-/);
  assert.equal(isMaterialPasteTarget({closest: () => ({})}), false);
});

test('publish confirmation names completion mode and keeps authenticated downloads', () => {
  const id = '00000000-0000-4000-8000-000000000001';
  const html = renderPublishMaterials([{type: 'file', name: '材料.pdf', url: `exploration-material:${id}`, size: 100}], task('learning'));
  assert.match(html, /完成方式 · 阅读学习/);
  assert.match(html, new RegExp(`/api/review-native/exploration/materials/${id}`));
});

test('real admin entry preserves material editing and opens exploration without demo adapters', async () => {
  const app = await readFile(new URL('../public/review-native/app.js', import.meta.url), 'utf8');
  assert.match(app, /createMaterialEditor/);
  assert.match(app, /data-edit-material/);
  assert.match(app, /material-dropzone/);
  assert.match(app, /data-field="completionMode"/);
  assert.doesNotMatch(app, /localPreviewEnabled|local-preview-api/);
});
