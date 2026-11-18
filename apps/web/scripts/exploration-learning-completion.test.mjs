import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import React from 'react';
import * as jsxRuntime from 'react/jsx-runtime';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

function load(file, dependencies = {}) {
  const compiled = ts.transpileModule(readFileSync(new URL(`../src/app/project29/${file}`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const loadedModule = { exports: {} };
  vm.runInNewContext(compiled, { module: loadedModule, exports: loadedModule.exports, URL,
    require: name => name === './explorationTaskState' ? load('explorationTaskState.ts') : ({ react: React, 'react/jsx-runtime': jsxRuntime, ...dependencies })[name] ?? {},
  });
  return loadedModule.exports;
}

function find(node, predicate) {
  if (Array.isArray(node)) return node.map(child => find(child, predicate)).find(Boolean);
  if (!node || typeof node !== 'object') return undefined;
  return predicate(node) ? node : find(node.props?.children, predicate);
}

const Form = () => null;
const { ExplorationLearningActions, ExplorationAssessmentActions } = load('ExplorationLearningActions.tsx', {
  './VillageTaskForm': { VillageTaskForm: Form },
});
const { ExplorationGraduationTaskCard } = load('ExplorationGraduationTaskCard.tsx');
const task = { id: 'task-learning', versionId: 'version-one', status: 'active', completionMode: 'learning',
  materials: [{ name: '文档', type: 'link', url: 'https://example.com/learning' }], openedMaterials: [] };
const renderLearning = patch => renderToStaticMarkup(React.createElement(ExplorationLearningActions, {
  task: { ...task, ...patch }, busy: false, hasNext: true, onComplete: async () => true, onContinue() {},
}));

test('learning completion waits for every material and exposes the opened material count', () => {
  const initial = renderLearning();
  assert.match(initial, /还有 1 份材料尚未打开/);
  assert.match(initial, /disabled="">完成学习，进入下一板块/);
  const ready = renderLearning({ openedMaterials: [0] });
  assert.match(ready, /本板块材料均已打开/);
  assert.doesNotMatch(ready, /disabled="">完成学习，进入下一板块/);
  const completed = renderLearning({ status: 'completed', openedMaterials: [0] });
  assert.match(completed, /本板块学习已完成/);
  assert.match(completed, /完成记录已保存/);
});

test('signout requires a separate acknowledgement and completed signout stays readable', () => {
  const initial = renderLearning({ completionMode: 'checkin' });
  assert.match(initial, /type="checkbox"/);
  assert.match(initial, /我已完成签退，并成功进入项目培训群/);
  assert.match(initial, /disabled="">确认完成签退及入群/);
  assert.match(renderLearning({ completionMode: 'checkin', status: 'completed' }), /签退及入群已确认/);
});

test('assessment results use the configured minimum and preserve the real draft and submit form', () => {
  const tree = ExplorationAssessmentActions({ task: { ...task, completionMode: 'assessment', minimumAnswerLength: 1 },
    answer: 'https://example.com/result', busy: false, savedMessage: '草稿保存成功', beforeActions: 'AI反馈区',
    hasNext: true, onAnswer() {}, onAction: async () => true, onContinue() {},
  });
  const form = find(tree, node => node.type === Form);
  assert.equal(form.props.minLength, 1);
  assert.equal(form.props.inputLabel, '测试结果或飞书文档链接');
  assert.equal(form.props.savedMessage, '草稿保存成功');
  assert.equal(form.props.beforeActions, 'AI反馈区');
  assert.doesNotMatch(form.props.placeholder, /AI 自测|AI 评测/);
});

test('an unlocked unclaimed assessment keeps the claim step while its visible status is active', () => {
  const commands = [];
  const tree = ExplorationAssessmentActions({ task: { ...task, completionMode: 'assessment', claimed: false, assignmentId: null },
    answer: '', busy: false, savedMessage: '', beforeActions: 'AI反馈区', hasNext: true,
    onAnswer() {}, onAction: async command => { commands.push(command); return true; }, onContinue() {},
  });
  assert.equal(find(tree, node => node.type === Form), undefined);
  const start = find(tree, node => node.type === 'button');
  assert.match(renderToStaticMarkup(tree), /填写测试结果/);
  start.props.onClick();
  assert.deepEqual(commands, ['claim']);
});

const renderGraduation = graduation => renderToStaticMarkup(React.createElement(ExplorationGraduationTaskCard, {
  order: 9, onOpen() {}, treasures: { total: 4, count: 0, items: [], pendingDrops: [], graduation },
}));

test('existing ready and migrated graduation codes retain their real account states', () => {
  const ready = renderGraduation({ status: 'READY', code: 'REAL-GRADUATION', unlockedAt: '2026-11-17T00:00:00Z' });
  assert.match(ready, /data-graduation-status="READY"/);
  assert.match(ready, /REAL-GRADUATION/);
  assert.match(ready, /查看毕业码/);
  const migrated = renderGraduation({ status: 'MIGRATED', code: null, unlockedAt: null });
  assert.match(migrated, /data-graduation-status="MIGRATED"/);
  assert.match(migrated, /历史数据已迁移至公司飞书账号/);
  const formal = renderGraduation({ status: 'NOT_REQUIRED', code: null, unlockedAt: null });
  assert.match(formal, /正式账号/);
  assert.match(formal, /当前为公司飞书账号，无需使用毕业码/);
});

test('locked graduation explains its server reason and does not invent a code', () => {
  const html = renderGraduation({ status: 'LOCKED', code: null, unlockedAt: null, blockReason: '还有测试等待审核通过。' });
  assert.match(html, /还有测试等待审核通过/);
  assert.match(html, /data-graduation-status="LOCKED"/);
  assert.doesNotMatch(html, /exploration-graduation-task-code/);
});

const materialHooks = { useState: value => [value, () => {}], useRef: value => ({ current: value }) };
const { ExplorationLearningMaterial } = load('ExplorationLearningMaterial.tsx', { react: materialHooks });
const renderMaterial = material => ExplorationLearningMaterial({ taskId: task.id, index: 2, material });

test('real uploaded images and videos use the authenticated inline stream and keep the download route', () => {
  const image = renderMaterial({ name: '签退二维码.png', type: 'image', mime: 'image/png', url: '' });
  assert.equal(find(image, node => node.type === 'img').props.src, '/api/learner/exploration?task=task-learning&material=2&inline=1');
  assert.equal(find(image, node => node.type === 'a').props.href, '/api/learner/exploration?task=task-learning&material=2');
  const video = renderMaterial({ name: '培训视频.mp4', type: 'file', mime: 'video/mp4', size: 100 * 1024 * 1024, url: '' });
  const player = find(video, node => node.type === 'video');
  assert.equal(player.props.controls, true);
  assert.equal(player.props.playsInline, true);
  assert.equal(player.props.preload, 'metadata');
  assert.match(player.props.src, /material=2&inline=1$/);
});

test('HTML and SVG attachments keep download-only rendering and unsafe link schemes remain inactive', () => {
  for (const [name, mime] of [['unsafe.svg', 'image/svg+xml'], ['unsafe.html', 'text/html']]) {
    const tree = renderMaterial({ name, mime, type: 'file', url: '' });
    assert.equal(find(tree, node => node.type === 'img' || node.type === 'iframe'), undefined);
    assert.equal(find(tree, node => node.type === 'a').props.download, true);
  }
  const tree = renderMaterial({ name: '无效链接', type: 'link', url: 'javascript:alert(1)' });
  assert.equal(find(tree, node => node.type === 'a'), undefined);
});

test('an image that finishes loading records one material-open action across repeated events', async () => {
  let reads = 0;
  const tree = ExplorationLearningMaterial({ taskId: task.id, index: 0,
    material: { name: '签退二维码.png', type: 'image', mime: 'image/png', url: '' },
    onOpened: async () => { reads++; return task; },
  });
  const image = find(tree, node => node.type === 'img');
  image.props.onLoad();
  image.props.onLoad();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(reads, 1);
});

test('question documents use a separate authenticated file group without learning-read controls', () => {
  const tree = ExplorationLearningMaterial({ taskId: 'task/question', index: 0, group: 'task',
    material: { name: '入营选择与解答题.pdf', type: 'file', mime: 'application/pdf', url: '' },
  });
  const link = find(tree, node => node.type === 'a');
  assert.equal(link.props.href, '/api/learner/exploration?task=task%2Fquestion&material=0&group=task');
  assert.equal(link.props.download, true);
  assert.doesNotMatch(renderToStaticMarkup(tree), /尚未打开|打开记录|已确认阅读/);
  const image = ExplorationLearningMaterial({ taskId: task.id, index: 1, group: 'task',
    material: { name: '题目.png', type: 'image', mime: 'image/png', url: '' },
  });
  assert.equal(find(image, node => node.type === 'img').props.src,
    '/api/learner/exploration?task=task-learning&material=1&group=task&inline=1');
  const legacy = renderMaterial({ name: '学习材料.pdf', type: 'file', mime: 'application/pdf', url: '' });
  assert.equal(find(legacy, node => node.type === 'a').props.href, '/api/learner/exploration?task=task-learning&material=2');
});

test('question document results retain the configured answer limit and real submission form', () => {
  const tree = ExplorationAssessmentActions({ task: { ...task, completionMode: 'assessment',
    taskFiles: [{ name: '题目.docx', type: 'file' }], minimumAnswerLength: 1, claimed: true },
    answer: 'https://example.com/my-answers', busy: false, savedMessage: '', beforeActions: '自测反馈',
    hasNext: true, onAnswer() {}, onAction: async () => true, onContinue() {},
  });
  const form = find(tree, node => node.type === Form);
  assert.equal(form.props.minLength, 1);
  assert.equal(form.props.inputLabel, '任务成果或飞书文档链接');
  assert.equal(form.props.beforeActions, '自测反馈');
  assert.match(form.props.placeholder, /任务成果/);
});
