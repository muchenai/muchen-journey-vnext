import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {
  ANSWER_DOCUMENT_DIMENSION, effectiveRubric, usesAnswerDocumentRubric, hasUsableRubricAttachments,
  rubricScoreTotal, rubricDimensionErrors,
} from '../public/review-native/rubric-policy.js';
import {
  validateTask, getReviewCamp, escapeHtml, DIFFICULTY_PRESETS,
} from '../public/review-native/core.js';
import {
  requiresTaskAssessment, explorationTaskResourceErrors, explorationTaskFiles, EXPLORATION_COMPLETION_MODES,
} from '../public/review-native/exploration-completion.js';
import {validateTaskFieldLimits} from '../public/review-native/task-field-limits.js';
import {isPublishingDepartment} from '../public/review-native/publishing-departments.js';
import {isMaterialLink} from '../public/review-native/material-validation.js';
import {renderRubricAttachments} from '../public/review-native/rubric-link-editor.js';
import {openTask} from '../public/review-native/library.js';
import {createSandboxController} from '../public/review-native/sandbox.js';

const source = name => readFileSync(new URL(`../public/review-native/${name}`, import.meta.url), 'utf8');
function file(body = '1. A\n2. BC', overrides = {}) {
  const bytes = Buffer.from(body);
  return {id: 'answer', name: '标准答案.txt', type: 'file', mime: 'text/plain', size: bytes.length,
    url: `data:text/plain;base64,${bytes.toString('base64')}`, ...overrides};
}
const imported = () => file('1. A\n2. BC', {
  sourceUrl: 'https://team.feishu.cn/docx/AnswerDocument0001', sourceRevision: '12', sourceTitle: '培训标准答案',
});
const task = overrides => ({
  id: 'task-one', camp: 'exploration', title: '标准答案文档评分任务', summary: '阅读学习材料后完成练习，并按照标准答案文档逐题核对。',
  order: 1, completionMode: 'assessment', reviewMode: 'ai', passScore: 60, rubric: [],
  materials: [{name: '学习材料', type: 'link', url: 'https://example.com/read'}],
  taskFiles: [{name: '题目文件', type: 'link', url: 'https://example.com/test'}],
  rubricAttachments: [imported()], ...overrides,
});

function appRender(draft, name) {
  const app = source('app.js');
  const next = name === 'renderScoring' ? 'getReadiness' : 'focusSection';
  const body = app.slice(app.indexOf(`function ${name}()`), app.indexOf(`\nfunction ${next}(`));
  const context = {
    store: {data: {draft}}, requiresTaskAssessment, rubricScoreTotal, usesAnswerDocumentRubric,
    rubricDimensionErrors, ANSWER_DOCUMENT_DIMENSION, getReviewCamp, e: escapeHtml,
    renderRubricAttachments, icon: () => '', cardHeader: (title, suffix = '') => `<h3>${title}${suffix}</h3>`,
    validateTaskFieldLimits, explorationTaskResourceErrors, explorationTaskFiles, EXPLORATION_COMPLETION_MODES,
    DIFFICULTY_PRESETS, isTaskCategory:isPublishingDepartment, isMaterialLink, badgeList: () => [],
  };
  return vm.runInNewContext(`${body}\n${name}();`, context);
}

function sandboxHarness(t, draft) {
  const old = globalThis.localStorage;
  const saved = new Map();
  globalThis.localStorage = {getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value)};
  t.after(() => {if (old === undefined) delete globalThis.localStorage; else globalThis.localStorage = old;});
  const node = () => ({value: '', textContent: '', listeners: {}, addEventListener(key, callback) {this.listeners[key] = callback;}});
  const nodes = Object.fromEntries(['#sandbox-sample-answer', '#sandbox-run', '.sandbox-local-status', '#sandbox-test-result'].map(key => [key, node()]));
  const state = {requests: [], html: '', notices: []};
  const content = {set innerHTML(value) {state.html = value;}};
  const modal = {querySelector: key => key === '.modal-content' ? content : nodes[key]};
  const store = {storageKey: 'test-document-rubric', data: {draft}};
  const controller = createSandboxController({
    store, service: {evaluations: {run: async (sent, answer) => {
      state.requests.push({task: sent, answer});
      return {score: 100, passed: true, dimensions: [{name: '标准答案评分', score: 100, max: 100}], comment: '依据标准答案文档评分。'};
    }}},
    openModal: (html, ready) => {state.html = html; ready(modal);},
    toast: message => state.notices.push(message),
  });
  return {controller, store, state, saved,
    answer(value) {nodes['#sandbox-sample-answer'].value = value; nodes['#sandbox-sample-answer'].listeners.input();},
    run: () => nodes['#sandbox-run'].listeners.click(),
  };
}

test('document-only exploration AI uses the agreed stable 100-point rubric without mutating raw dimensions', () => {
  const draft = task();
  const before = structuredClone(draft);
  Object.freeze(draft.rubric);
  const rubric = effectiveRubric(draft);
  assert.deepEqual(rubric, [{
    id: 'answer-document', name: '标准答案评分', points: 100,
    description: '按已导入标准答案文档逐题核对，遵循文档分值和扣分规则并换算为百分制。选择题文档未注明分值时各题等权；未注明扣分规则时，错选、漏选或多选该题记 0 分。主观题遵循文档评分要点，不自创标准；无法依据文档核对时不评分。',
  }]);
  assert.equal(rubric[0], ANSWER_DOCUMENT_DIMENSION);
  assert.equal(usesAnswerDocumentRubric(draft), true);
  assert.equal(rubricScoreTotal(draft), 100);
  assert.deepEqual(rubricDimensionErrors(draft), []);
  assert.deepEqual(validateTask(draft), []);
  assert.deepEqual(draft, before);
});

test('uploaded plain-text standards also enable document scoring, with server parsing remaining authoritative', () => {
  const draft = task({rubricAttachments: [file()]});
  assert.equal(hasUsableRubricAttachments(draft.rubricAttachments), true);
  assert.equal(usesAnswerDocumentRubric(draft), true);
  assert.deepEqual(validateTask(draft), []);
  assert.equal(hasUsableRubricAttachments([file('答案 A', {name: '答案.md', mime: 'text/markdown',
    url: 'data:text/markdown;base64,' + Buffer.from('答案 A').toString('base64')})]), true);
  assert.equal(hasUsableRubricAttachments([file('答案 A', {name: '答案.md'})]), true);
  for (const bytes of [
    Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from('标准答案 A', 'utf16le')]),
    Buffer.from([0xb1, 0xea, 0xd7, 0xbc, 0xb4, 0xf0, 0xb0, 0xb8, 0x20, 0x41]),
  ]) {
    assert.equal(hasUsableRubricAttachments([file(bytes)]), true);
    assert.deepEqual(validateTask(task({rubricAttachments: [file(bytes)]})), []);
  }
});

test('ordinary uploads retain document scoring after the API returns empty default source fields', () => {
  const savedUpload = file('1. A\n2. BC', {sourceUrl: '', sourceRevision: '', sourceTitle: ''});
  const draft = task({rubricAttachments: [savedUpload]});
  assert.equal(hasUsableRubricAttachments(draft.rubricAttachments), true);
  assert.equal(usesAnswerDocumentRubric(draft), true);
  assert.equal(rubricScoreTotal(draft), 100);
  assert.deepEqual(validateTask(draft), []);
  assert.equal(appRender(draft, 'getReadiness').find(row => row.id === 'task-rubric').ready, true);
  for (const fields of [
    {sourceUrl: ' ', sourceRevision: '', sourceTitle: ''},
    {sourceUrl: '', sourceRevision: '', sourceTitle: ' '},
    {sourceUrl: '', sourceRevision: '12', sourceTitle: ''},
    {sourceUrl: '', sourceRevision: '', sourceTitle: '残缺来源'},
  ]) assert.equal(hasUsableRubricAttachments([file('1. A', fields)]), false);
});

test('missing, blank, corrupt or unsafe documents never create an implicit rubric or bypass publication', () => {
  const invalid = [
    [], [file('')], [file(' \n\t\u3000')], [file('answer', {size: 999})],
    [file('answer', {type: 'link'})], [file('answer', {url: 'https://example.com/answer.txt'})],
    [file('answer', {url: 'data:text/plain;base64,not base64'})],
    [file('answer', {mime: 'application/pdf'})],
    [file('not a DOCX', {name: '答案.docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'})],
    [file('answer', {sourceUrl: 'https://evil.test/docx/AnswerDocument0001', sourceRevision: '1', sourceTitle: '答案'})],
    [file('answer', {sourceUrl: '', sourceRevision: '1', sourceTitle: '答案'})],
    [file('answer', {sourceUrl: imported().sourceUrl, sourceRevision: 'bad', sourceTitle: '答案'})],
    Array.from({length: 5}, () => imported()),
  ];
  for (const rubricAttachments of invalid) {
    const draft = task({rubricAttachments});
    assert.equal(hasUsableRubricAttachments(rubricAttachments), false);
    assert.deepEqual(effectiveRubric(draft), []);
    assert.match(validateTask(draft).join('；'), /标准答案文档|评分维度/);
  }
});

test('an explicit row always takes precedence and must be complete with exactly 100 points', () => {
  for (const rubric of [
    [{id: 'one', name: '', points: 0, description: ''}],
    [{id: 'one', name: '答案正确性', points: 60, description: '按文档核对'}],
    [{id: 'one', name: '答案正确性', points: 100, description: ''}],
    [{id: 'one', name: '答案正确性', points: 101, description: '按文档核对'}],
    [{id: 'one', name: '答案正确性', points: 33.333, description: '按文档核对'},
      {id: 'two', name: '说明', points: 66.667, description: '说明完整'}],
  ]) {
    const draft = task({rubric});
    assert.equal(usesAnswerDocumentRubric(draft), false);
    assert.equal(effectiveRubric(draft), rubric);
    assert.ok(rubricDimensionErrors(draft).length > 0);
    assert.ok(validateTask(draft).length > 0);
  }
  const rubric = [{id: 'explicit', name: '答案正确性', points: 100, description: '以标准答案为准'}];
  assert.equal(effectiveRubric(task({rubric})), rubric);
  assert.deepEqual(validateTask(task({rubric})), []);
});

test('novice, other camps, manual review and missing raw arrays keep their existing rules', () => {
  for (const camp of ['novice', 'academy', undefined]) {
    const draft = task({camp});
    assert.equal(usesAnswerDocumentRubric(draft), false);
    assert.deepEqual(effectiveRubric(draft), []);
    assert.ok(validateTask(draft).includes('请至少配置一个评分维度'));
  }
  const manual = task({reviewMode: 'manual'});
  assert.equal(usesAnswerDocumentRubric(manual), false);
  assert.deepEqual(validateTask(manual), []);
  assert.equal(usesAnswerDocumentRubric(task({rubric: undefined})), false);
  assert.equal(usesAnswerDocumentRubric(task({rubric: null})), false);
});

test('removing the final document immediately resets effective total and authoring readiness', () => {
  const draft = task();
  assert.equal(appRender(draft, 'getReadiness').find(row => row.id === 'task-rubric').ready, true);
  draft.rubricAttachments.splice(0, 1);
  assert.equal(rubricScoreTotal(draft), 0);
  assert.equal(appRender(draft, 'getReadiness').find(row => row.id === 'task-rubric').ready, false);
  assert.ok(validateTask(draft).length > 0);
  assert.deepEqual(draft.rubric, []);
});

test('authoring total, readiness and source-document instructions use the same effective policy', () => {
  const draft = task();
  const html = appRender(draft, 'renderScoring');
  assert.match(html, /合计 100\/100/);
  assert.match(html, /已按标准答案文档评分，满分 100 分/);
  assert.match(html, /各题等权/); assert.match(html, /错选、漏选或多选该题记 0 分/);
  assert.match(html, /无法依据文档核对时不评分/);
  assert.match(html, /如需自定义评分规则，仍可添加维度/);
  assert.doesNotMatch(html, /data-rubric="0"/);
  const incomplete = task({rubric: [{id: 'one', name: '', points: 0, description: ''}]});
  assert.match(appRender(incomplete, 'renderScoring'), /合计 0\/100/);
  assert.equal(appRender(incomplete, 'getReadiness').find(row => row.id === 'task-rubric').ready, false);
});

test('library details display the effective 100-point standard and retain the frozen file and source', () => {
  const draft = task();
  let html;
  openTask(draft, {data: {tasks: [draft], submissions: []}}, {
    isSuperAdmin: true, openModal: value => {html = value;}, toast() {},
  });
  assert.match(html, /共 100 分/); assert.match(html, /标准答案评分/);
  assert.match(html, /已按标准答案文档评分/); assert.match(html, /各题等权/);
  assert.match(html, /打开源文档/); assert.match(html, /下载已导入标准 TXT/);
  assert.doesNotMatch(html, /尚未配置评分标准/);
  assert.deepEqual(draft.rubric, []);
});

test('document-only sandbox runs the real service path using the raw author payload', async t => {
  const draft = task();
  const h = sandboxHarness(t, draft);
  h.controller.open(); h.answer('1. A\n2. BC'); await h.run();
  assert.equal(h.state.requests.length, 1);
  assert.deepEqual(h.state.requests[0].task.rubric, []);
  assert.deepEqual(h.state.requests[0].task.rubricAttachments, draft.rubricAttachments);
  assert.match(h.state.html, /标准答案评分/); assert.match(h.state.html, /100/);
  assert.deepEqual(h.state.notices, []);
  assert.deepEqual(draft.rubric, []);
});

test('sandbox rejects incomplete explicit dimensions and corrupt document-only standards before any API call', async t => {
  for (const draft of [
    task({rubric: [{id: 'one', name: '', points: 100, description: '按文档核对'}]}),
    task({rubricAttachments: [file('   ')]}),
  ]) {
    const h = sandboxHarness(t, draft);
    h.controller.open(); h.answer('1. A'); await h.run();
    assert.equal(h.state.requests.length, 0);
    assert.match(h.state.html, /评分维度|标准答案文档/);
  }
});

test('sandbox marks previous results stale after document replacement, removal or explicit-dimension changes', async t => {
  const h = sandboxHarness(t, task());
  h.controller.open(); h.answer('1. A'); await h.run();
  assert.doesNotMatch(h.state.html, /配置已更新/);
  h.store.data.draft.rubricAttachments = [file('1. B')];
  h.controller.open(); assert.match(h.state.html, /配置已更新/);
  h.store.data.draft.rubricAttachments = [];
  h.controller.open(); assert.match(h.state.html, /配置已更新/);
  h.store.data.draft.rubric = [{id: 'explicit', name: '正确性', points: 100, description: '按答案评分'}];
  h.controller.open(); assert.match(h.state.html, /配置已更新/);
});

test('entry scripts fetch the updated shared policy rather than old cached validation', () => {
  const appVersion = source('index.html').match(/src="\.\/app\.js\?v=(\d{8})-/)?.[1];
  assert.ok(Number(appVersion) >= 20261126);
  assert.match(source('app.js'), /core.js\?v=20261118-document-rubric/);
  assert.match(source('app.js'), /sandbox.js\?v=20261118-document-rubric/);
  assert.match(source('app.js'), /library.js\?v=20261127-task-management/);
  assert.match(source('core.js'), /rubric-policy.js\?v=20261118-document-rubric/);
  assert.match(source('sandbox.js'), /rubric-policy.js\?v=20261118-document-rubric/);
});
