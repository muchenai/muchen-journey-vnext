import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import * as jsxRuntime from 'react/jsx-runtime';
import ts from 'typescript';

const taskStateModule = { exports: {} };
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/app/project29/explorationTaskState.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { module: taskStateModule, exports: taskStateModule.exports });

const graduationModule = { exports: {} };
const graduationCode = ts.transpileModule(readFileSync(new URL('../src/app/project29/ExplorationGraduationTaskCard.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
vm.runInNewContext(graduationCode, { module: graduationModule, exports: graduationModule.exports,
  require: name => name === 'react/jsx-runtime' ? jsxRuntime : {},
});
const compiled = ts.transpileModule(readFileSync(new URL('../src/app/project29/ExplorationTaskList.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const compiledModule = { exports: {} };
vm.runInNewContext(compiled, { module: compiledModule, exports: compiledModule.exports,
  require: name => name === 'react/jsx-runtime' ? jsxRuntime : name === './ExplorationGraduationTaskCard' ? graduationModule.exports : name === './explorationTaskState' ? taskStateModule.exports : {},
});
const List = compiledModule.exports.ExplorationTaskList;
const task = (id, order, status = 'active') => ({ id, order, status, title: `可配置学习任务${id}`, description: `管理员编写的学习介绍${id}`,
  publishingDepartment: 'RETIRED_DEPARTMENT', level: 'RETIRED_DIFFICULTY', experience: 9999, points: 9999 });
const props = { tasks: [], identity: '体验学员', onBack() {}, onOpenTask() {} };
const render = overrides => renderToStaticMarkup(React.createElement(List, { ...props, ...overrides }));

test('restored exploration list uses administrator order and an arbitrary published task count', () => {
  const tasks = [task('later', 12), task('first', 2), task('middle', 7), task('other', 5)];
  const html = render({ tasks });
  assert.ok(html.indexOf('data-task-id="first"') < html.indexOf('data-task-id="other"'));
  assert.ok(html.indexOf('data-task-id="other"') < html.indexOf('data-task-id="middle"'));
  assert.ok(html.indexOf('data-task-id="middle"') < html.indexOf('data-task-id="later"'));
  assert.match(html, /data-task-order="12"/);
  assert.match(html, /aria-valuemax="4"/);
  assert.match(html, /任务 02/);
  assert.match(html, /\/assets\/project29\/90975.webp/);
  assert.match(html, /探索营毕业码/);
  assert.doesNotMatch(html, /上一任务|待解锁|RETIRED_DEPARTMENT|RETIRED_DIFFICULTY|9999/);
  const many = render({ tasks: Array.from({ length: 14 }, (_, index) => task(`task-${index}`, index + 1)) });
  assert.equal((many.match(/data-task-id=/g) || []).length, 14);
  assert.match(many, /aria-valuemax="14"/);
});

test('graduation remains the final card for any catalog size and never inflates task progress', () => {
  for (const count of [0, 1, 6, 14, 30]) {
    const tasks = Array.from({ length: count }, (_, index) => task(`row-${index}`, index + 1));
    const html = render({ tasks });
    assert.equal((html.match(/data-graduation-order=/g) || []).length, 1);
    assert.match(html, new RegExp(`data-graduation-order="${count + 1}"`));
    assert.equal((html.match(/data-task-id=/g) || []).length, count);
    assert.match(html, new RegExp(`aria-valuemax="${count || 1}"`));
    if (count) assert.ok(html.indexOf('data-graduation-order=') > html.indexOf(`data-task-id="row-${count - 1}"`));
  }
  let opened = 0;
  const root = List({ ...props, onOpenGraduation: () => { opened++; } });
  function find(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.map(find).find(Boolean);
    if (node.type === graduationModule.exports.ExplorationGraduationTaskCard) return node;
    return find(node.props?.children);
  }
  find(root).props.onOpen();
  assert.equal(opened, 1);
});

test('published tasks retain independent statuses and route clicks to the selected task', () => {
  const tasks = [task('done', 1, 'completed'), task('review', 2, 'pending'), task('edit', 3, 'returned'), task('work', 4, 'active'), task('new', 5), task('later', 6, 'locked')];
  const html = render({ tasks });
  for (const label of ['已完成', '待审核', '待修改', '进行中', '待解锁']) assert.match(html, new RegExp(label));
  assert.match(html, /aria-valuenow="1"/);
  assert.match(html, /任务 03/);
  assert.match(html, /journey-task-locked/);
  assert.doesNotMatch(html, /可接取/);
  const selected = [];
  const root = List({ ...props, tasks, onOpenTask: id => selected.push(id) });
  const buttons = [];
  function visit(value) {
    if (!value || typeof value !== 'object') return;
    if (Array.isArray(value)) { value.forEach(visit); return; }
    if (value.type === 'button') buttons.push(value);
    visit(value.props?.children);
  }
  visit(root);
  let stopped = false;
  buttons.find(button => button.props['data-task-id'] === 'new').props.onClick({ stopPropagation() { stopped = true; } });
  assert.deepEqual(selected, ['new']);
  assert.equal(stopped, true);
  const locked = buttons.find(button => button.props['data-task-id'] === 'later');
  assert.equal(locked.props.disabled, true);
  locked.props.onClick({ stopPropagation() {} });
  assert.deepEqual(selected, ['new']);
  assert.match(html, /上一任务提交后解锁/);
  assert.match(html, /等待上一任务提交/);
});

test('loading, empty and unavailable task states render without a fixed route or missing-current crash', () => {
  assert.match(render({ loading: true }), /正在读取探索任务/);
  assert.match(render({}), /暂时没有已发布的探索任务/);
  const html = render({ tasks: [task('unavailable', 1, 'unavailable')], error: '任务读取失败', onRefresh() {} });
  assert.match(html, /任务读取失败/);
  assert.match(html, /刷新任务/);
  assert.match(html, /等待启程/);
  assert.match(html, /暂不可用/);
});

test('catalog reordering preserves server-backed history access while an untouched locked task stays disabled', () => {
  const tasks = [task('new-first', 1, 'locked'), task('reviewing', 2, 'pending'), task('returned', 3, 'returned'),
    task('already-claimed', 4, 'active'), task('finished', 5, 'completed')];
  const selected = [];
  const tree = List({ ...props, tasks, onOpenTask: id => selected.push(id) });
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(visit); return; }
    if (node.type === 'button' && node.props['data-task-id']) {
      assert.equal(node.props.disabled, node.props['data-task-id'] === 'new-first');
      node.props.onClick({ stopPropagation() {} });
    }
    visit(node.props?.children);
  }
  visit(tree);
  assert.deepEqual(selected, ['reviewing', 'returned', 'already-claimed', 'finished']);
});
