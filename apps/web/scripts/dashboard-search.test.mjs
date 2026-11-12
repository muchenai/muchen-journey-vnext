import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src');
const nativeRequire = createRequire(import.meta.url);
const cache = new Map();
function load(filename) {
  if (filename.endsWith('.css')) return {};
  if (cache.has(filename)) return cache.get(filename).exports;
  const compiledModule = { exports: {} };
  cache.set(filename, compiledModule);
  const source = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
    fileName: filename,
  }).outputText;
  const require = name => {
    if (!name.startsWith('.') && !name.startsWith('@/')) return nativeRequire(name);
    const base = name.startsWith('@/') ? path.join(root, name.slice(2)) : path.resolve(path.dirname(filename), name);
    const target = [base, base + '.ts', base + '.tsx'].find(existsSync);
    assert.ok(target, `Missing import ${name}`);
    return load(target);
  };
  vm.runInThisContext('(function(require,module,exports){' + source + '\n})', { filename })(require, compiledModule, compiledModule.exports);
  return compiledModule.exports;
}

const { executionTasks } = load(path.join(root, 'app/project29/ExecutionPages.tsx'));
const { JourneyProvider } = load(path.join(root, 'app/project29/journey-context.tsx'));
const { UpdatedDashboard } = load(path.join(root, 'app/project29/UpdatedDashboard.tsx'));
const { prioritizeDashboardTasks } = load(path.join(root, 'app/project29/DashboardTaskGrid.tsx'));
const { DashboardSearchProvider, filterDashboardTasks } = load(path.join(root, 'app/project29/dashboardSearch.tsx'));

test('task search independently matches title, name and description with trimmed case-insensitive text', () => {
  const entries = [
    { task: { ...executionTasks[0], title: '标题命中', name: '第一项', description: '介绍一' }, index: 4, status: 'active' },
    { task: { ...executionTasks[1], title: '第二项', name: '名称命中', description: '介绍二' }, index: 1, status: 'pending' },
    { task: { ...executionTasks[2], title: '第三项', name: '第三项', description: 'Only the Muchener description matches' }, index: 7, status: 'locked' },
  ];
  for (const [query, index] of [['标题命中', 0], ['名称命中', 1], ['  mUcHeNeR\t', 2]]) {
    const matches = filterDashboardTasks(entries, query);
    assert.equal(matches.length, 1, query);
    assert.equal(matches[0], entries[index], 'Search must return the original task entry');
  }
  assert.deepEqual(filterDashboardTasks(entries, '不存在的关键词'), []);
  assert.equal(filterDashboardTasks(entries, ''), entries);
  assert.equal(filterDashboardTasks(entries, ' \t\n '), entries);
});

const statuses = ['completed', 'locked', 'pending', 'active', 'revision', 'completed', 'revision', 'active'];
test('filtering preserves task priority, stable ties, original indices and entry identity', () => {
  const entries = Object.freeze(executionTasks.map((task, index) => Object.freeze({
    task: Object.freeze({ ...task, description: '共同搜索词' }), index, status: statuses[index],
  })));
  const ordered = prioritizeDashboardTasks(entries);
  const matches = filterDashboardTasks(ordered, '共同搜索词');
  assert.deepEqual(matches.map(entry => entry.index), [4, 6, 3, 7, 2, 1, 0, 5]);
  for (const entry of matches) assert.equal(entry, entries[entry.index]);
  assert.deepEqual(entries.map(entry => entry.index), [0, 1, 2, 3, 4, 5, 6, 7], 'Search must not reorder its source');
});

function createExperience(completedStages = 2) {
  const assignmentStatuses = { completed: 'COMPLETED', locked: 'AVAILABLE', pending: 'SUBMITTED', active: 'IN_PROGRESS', revision: 'NEEDS_REVISION' };
  return {
    assignmentId: 'assignment-5', stagePosition: 5, estimatedMinutes: 27, completedStages,
    journeyTasks: executionTasks.map((task, index) => ({
      assignmentId: `assignment-${index + 1}`, position: index + 1, title: task.title,
      status: statuses[index] === 'completed' ? 'COMPLETED' : statuses[index] === 'locked' ? 'LOCKED' : 'CURRENT',
      assignmentStatus: assignmentStatuses[statuses[index]],
    })),
    activityRecords: [{ position: 3, body: '真实待审核提交', status: 'SUBMITTED', submittedAt: '2026-11-10T08:00:00Z' }],
    reviewFeedback: [{ assignmentId: 'assignment-5', position: 5, records: [{
      id: 'feedback-1', reviewedAt: '2026-11-10T09:00:00Z', decision: 'REVISION_REQUIRED', comment: '请补充真实任务证据',
    }] }],
  };
}

function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (Array.isArray(node)) return node.map(child => find(child, predicate)).find(Boolean) ?? null;
  return predicate(node) ? node : find(node.props?.children, predicate);
}

function createDashboard(experience = createExperience()) {
  let query = '';
  let tree;
  let clearCount = 0;
  function DashboardProbe() {
    tree = UpdatedDashboard({ identity: '真实学员', decoration: null, activeNavigationDecoration: null, idleNavigationDecoration: null });
    return tree;
  }
  return {
    setQuery(value) { query = value; },
    get query() { return query; },
    get clearCount() { return clearCount; },
    render({ withProvider = true } = {}) {
      const dashboard = React.createElement(DashboardProbe);
      return renderToStaticMarkup(React.createElement(JourneyProvider, { value: {
        learnerName: '真实学员', experience, initialScreen: 'dashboard', joinPhase: 'feishu', joinError: '',
      } }, withProvider ? React.createElement(DashboardSearchProvider, {
        query, onClearSearch() { query = ''; clearCount++; },
      }, dashboard) : dashboard));
    },
    clear() {
      const button = find(tree, node => node.type === 'button' && node.props.className === 'dashboard-search-clear');
      assert.ok(button, 'The rendered search results must expose a clear action');
      button.props.onClick();
    },
  };
}

function tiles(html) {
  return (html.match(/<button\b[^>]*class="dashboard-task-tile\b[^>]*>[\s\S]*?<\/button>/g) ?? []).map(markup => ({
    index: Number(markup.match(/data-task-index="(\d+)"/)[1]),
    status: markup.match(/data-status="([^"]+)"/)[1], markup,
  }));
}

test('real task title, description and English queries reach the search result cards', () => {
  const dashboard = createDashboard();
  for (const [query, expected] of [['模型判断', [6]], ['经营理念', [0]], ['  mUcHeNeR  ', [1]], ['  DAY 1\t', [0]]]) {
    dashboard.setQuery(query);
    const html = dashboard.render();
    assert.deepEqual(tiles(html).map(tile => tile.index), expected, query);
    assert.match(html, /aria-label="探索营任务搜索结果"/);
    assert.match(html, /role="status" aria-live="polite">找到 1 个任务/);
    for (const tile of tiles(html)) {
      assert.equal(tile.status, statuses[tile.index]);
      assert.match(tile.markup, /data-action="open-task"/);
      const description = renderToStaticMarkup(React.createElement(React.Fragment, null, executionTasks[tile.index].description.trim()));
      assert.ok(tile.markup.includes(description), 'Search cards expose the matching task description');
    }
  }
});

test('search includes the current task and preserves priority and original navigation indices', () => {
  const dashboard = createDashboard();
  const original = dashboard.render();
  assert.match(original, /data-task-index="4" data-node-id="4043:227"/);
  assert.deepEqual(tiles(original).map(tile => tile.index), [6, 3, 7, 2, 1, 0, 5]);
  dashboard.setQuery('宝藏');
  const searched = dashboard.render();
  const matches = tiles(searched);
  assert.deepEqual(matches.map(tile => tile.index), [4, 3, 2, 1]);
  assert.deepEqual(matches.map(tile => tile.status), ['revision', 'active', 'pending', 'locked']);
  assert.match(matches.at(-1).markup, /aria-disabled="true"/);
  assert.match(searched, /找到 4 个任务/);
  assert.doesNotMatch(searched, /data-node-id="4043:200"|aria-label="任务操作日志"/);
  assert.equal((searched.match(/class="dashboard-task-board"/g) ?? []).length, 1, 'The original seven-card board is replaced');
});

test('every one of the eight exploration tasks remains searchable with its original status and route index', () => {
  const dashboard = createDashboard();
  assert.equal(executionTasks.length, 8);
  for (const [index, task] of executionTasks.entries()) {
    dashboard.setQuery(task.title);
    const matches = tiles(dashboard.render());
    assert.deepEqual(matches.map(tile => tile.index), [index], task.title);
    assert.equal(matches[0].status, statuses[index]);
    assert.match(matches[0].markup, /data-action="open-task"/);
  }
});

test('no matches provide feedback and an operable clear action that restores the original dashboard state', () => {
  const experience = createExperience();
  const snapshot = JSON.stringify(experience);
  const dashboard = createDashboard(experience);
  const original = dashboard.render();
  dashboard.setQuery('不存在的探索营任务');
  const empty = dashboard.render();
  assert.match(empty, /找到 0 个任务/);
  assert.match(empty, /暂无相关任务/);
  assert.match(empty, /请尝试其他关键词/);
  assert.deepEqual(tiles(empty), []);
  assert.doesNotMatch(empty, /data-node-id="4043:200"|aria-label="任务操作日志"/);
  dashboard.clear();
  assert.equal(dashboard.query, '');
  assert.equal(dashboard.clearCount, 1);
  const restored = dashboard.render();
  assert.equal(restored, original, 'Clearing must restore the current task, logs, card order and existing statuses');
  assert.match(restored, /data-node-id="4043:200"/);
  assert.match(restored, /aria-label="任务操作日志"/);
  assert.match(restored, /真实待审核提交/);
  assert.match(restored, /请补充真实任务证据/);
  assert.equal(JSON.stringify(experience), snapshot, 'Search and clearing must not mutate learner progress or task state');
});

test('clearing matching results and whitespace-only queries restore the original seven-card layout', () => {
  const dashboard = createDashboard();
  const original = dashboard.render();
  dashboard.setQuery('规则');
  assert.ok(tiles(dashboard.render()).length > 0);
  dashboard.clear();
  assert.equal(dashboard.render(), original);
  dashboard.setQuery(' \t\n ');
  assert.equal(dashboard.render(), original);
  assert.equal(dashboard.render({ withProvider: false }), original, 'Standalone dashboard rendering retains the default layout');
});

test('task filtering never changes the completed total, progress maximum or supporting task records', () => {
  for (const completedStages of [0, 2, 8]) {
    const dashboard = createDashboard(createExperience(completedStages));
    const originalProgress = dashboard.render().match(/<progress\b[^>]*>/)[0];
    for (const query of ['宝藏', '经营理念', '无结果关键词']) {
      dashboard.setQuery(query);
      const html = dashboard.render();
      assert.equal(html.match(/<progress\b[^>]*>/)[0], originalProgress);
      assert.ok(originalProgress.includes(`value="${completedStages}" max="8"`));
      assert.ok(html.includes(`aria-valuetext="${completedStages}/8 项已完成"`));
      assert.ok(html.includes(`data-node-id="4062:590">${completedStages}/8<`));
      assert.match(html, /待审核任务 · 1/);
      assert.match(html, /真实待审核提交/);
      assert.match(html, /请补充真实任务证据/);
    }
  }
});
