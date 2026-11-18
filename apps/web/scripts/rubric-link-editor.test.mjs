import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRubricLinkEditor, renderRubricAttachments} from '../public/review-native/rubric-link-editor.js';
import {normalizeRubricLink, rubricSourceUrl, normalizeImportedRubricMaterial} from '../public/review-native/rubric-materials.js';

const URL_ONE = 'https://team.feishu.cn/docx/AnswerDocument0001';
const URL_TWO = 'https://team.feishu.cn/docx/AnswerDocument0002';
const WIKI = 'https://team.feishu.cn/wiki/AnswerWikiNode0001';
const material = (overrides = {}) => ({
  id: 'imported-one', name: '标准答案.txt', type: 'file', mime: 'text/plain', size: 11,
  url: 'data:text/plain;base64,' + Buffer.from('1. A\n2. B\n3').toString('base64'),
  sourceUrl: URL_ONE, sourceTitle: '标准答案', sourceRevision: '12', ...overrides,
});
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
};

function harness(files = [], options = {}) {
  const field = {value: '', attrs: {}, listeners: {}, disabled: false,
    setAttribute(key, value) {this.attrs[key] = value;},
    addEventListener(key, callback) {this.listeners[key] = callback;},
    focus() {this.focused = true;},
  };
  const button = {textContent: '读取并添加', disabled: false};
  const form = {elements: {namedItem: () => field}, querySelector: () => button};
  const nodes = {
    '#rubric-link-form': form, '#rubric-link-error': {hidden: true},
    '#rubric-link-status': {textContent: ''}, '[data-cancel-rubric-link]': {},
  };
  const listeners = {};
  const modal = {querySelector: key => nodes[key], addEventListener: (key, callback) => {listeners[key] = callback;}};
  const store = {data: {draft: {
    id: 'task-one', camp: 'exploration', difficulty: '入门', reviewMode: 'ai',
    rubric: [{name: '正确性', description: '按照答案评分', points: 100}], passScore: 60,
    rubricAttachments: [...files],
  }}};
  const state = {saves: 0, closes: 0, refreshes: 0, requests: [], messages: [], fail: false};
  const open = createRubricLinkEditor({
    store, request: async input => {state.requests.push(input); return options.request ? options.request(input) : {material: material()};},
    openModal: (html, ready) => {
      listeners['review-close']?.();
      state.html = html; field.value = files[options.index ?? 0]?.sourceUrl || ''; ready(modal);
    },
    closeModal: () => {state.closes++; listeners['review-close']?.();},
    saveDraft: () => {state.saves++; return !state.fail;},
    refresh: () => {state.refreshes++;},
    toast: (message, type) => {state.messages.push({message, type});},
  });
  return {store, state, nodes, field, button, open,
    submit: () => form.onsubmit({preventDefault() {}}),
    cancel: () => nodes['[data-cancel-rubric-link]'].onclick(),
    close: () => listeners['review-close']?.(),
  };
}

test('answer links require trusted HTTPS document subdomains and strict token paths', () => {
  assert.equal(normalizeRubricLink(`  ${URL_ONE}/?from=copy#title `), URL_ONE);
  assert.equal(normalizeRubricLink(URL_ONE.replace('.cn/', '.cn:443/')), URL_ONE);
  assert.equal(normalizeRubricLink('https://team.larksuite.com/wiki/AnswerWikiNode0001'), 'https://team.larksuite.com/wiki/AnswerWikiNode0001');
  for (const url of ['', '   ', '\t\u3000', 'https://', 'http://team.feishu.cn/docx/AnswerDocument0001',
    'https://feishu.cn/docx/AnswerDocument0001', 'https://team.feishu.cn:444/docx/AnswerDocument0001',
    'https://team.feishu.cn.evil.test/docx/AnswerDocument0001', 'https://notfeishu.cn/docx/AnswerDocument0001',
    'https://user:password@team.feishu.cn/docx/AnswerDocument0001', 'javascript:alert(1)',
    'https://team.feishu.cn/file/AnswerDocument0001', 'https://team.feishu.cn/docx/short',
    'https://team.feishu.cn/docx/AnswerDocument0001/extra', 'https://team.feishu.cn/docx/answer%2Fescaped',
    'https://team.feishu.cn/docx/' + 'a'.repeat(101)]) assert.throws(() => normalizeRubricLink(url), /填写|空格/);
});

test('empty, whitespace and invalid URLs have distinct errors before any API call', async () => {
  for (const [value, expected] of [['', /请填写标准答案/], ['   ', /不能只包含空格/], ['https://example.com/docx/AnswerDocument0001', /有效的 HTTPS/]]) {
    const h = harness(); h.open(); h.field.value = value; await h.submit();
    assert.match(h.nodes['#rubric-link-error'].textContent, expected);
    assert.equal(h.nodes['#rubric-link-error'].hidden, false);
    assert.equal(h.field.attrs['aria-invalid'], 'true');
    assert.equal(h.field.focused, true);
    assert.equal(h.state.requests.length, 0);
    assert.equal(h.state.saves, 0);
    assert.deepEqual(h.store.data.draft.rubricAttachments, []);
    assert.deepEqual(h.state.messages, []);
  }
});

test('successful import saves frozen TXT in rubricAttachments without changing dimensions or pass line', async () => {
  const h = harness(); h.open(); h.field.value = ` ${WIKI}?from=copy `;
  const before = structuredClone(h.store.data.draft);
  await h.submit();
  assert.deepEqual(h.state.requests, [{command: 'importRubricDocument', payload: {url: WIKI, camp: 'exploration', difficulty: '入门'}}]);
  assert.deepEqual(h.store.data.draft.rubricAttachments, [material()]);
  assert.deepEqual(h.store.data.draft.rubric, before.rubric);
  assert.equal(h.store.data.draft.passScore, 60);
  assert.equal(h.state.saves, 1);
  assert.equal(h.state.closes, 1);
  assert.equal(h.state.messages.length, 1);
  assert.match(h.state.messages[0].message, /已读取并添加/);
  assert.match(h.state.html, /不会运行 AI，也不会发送评论/);
  assert.match(h.state.html, /评分使用已导入的版本/);
});

test('a missing, empty or malformed frozen response never reaches a draft or emits success', async () => {
  for (const response of [null, {}, {material: material({url: URL_ONE})},
    {material: material({sourceUrl: 'https://evil.test/docx/AnswerDocument0001'})},
    {material: material({sourceUrl: WIKI})}, {material: material({size: 99})},
    {material: material({url: 'data:text/plain;base64,', size: 0})},
    {material: material({sourceRevision: 'not-a-revision'})}]) {
    const h = harness([], {request: async () => response}); h.open(); h.field.value = URL_ONE; await h.submit();
    assert.deepEqual(h.store.data.draft.rubricAttachments, []);
    assert.equal(h.state.saves, 0); assert.equal(h.state.closes, 0); assert.deepEqual(h.state.messages, []);
    assert.match(h.nodes['#rubric-link-error'].textContent, /未能读取完整/);
    assert.equal(h.button.disabled, false);
  }
  assert.deepEqual(normalizeImportedRubricMaterial(material()), material());
});

test('request errors preserve an existing answer and allow an explicit retry', async () => {
  let fail = true;
  const previous = material({id: 'original', sourceRevision: '1'});
  const h = harness([previous], {request: async () => {if (fail) throw new Error('无权读取该文档'); return {material: material({sourceRevision: '13'})};}});
  h.open(0); h.field.value = URL_ONE; await h.submit();
  assert.deepEqual(h.store.data.draft.rubricAttachments, [previous]);
  assert.equal(h.state.saves, 0); assert.equal(h.state.closes, 0); assert.deepEqual(h.state.messages, []);
  assert.match(h.nodes['#rubric-link-error'].textContent, /无权读取/);
  assert.equal(h.button.disabled, false);
  fail = false; await h.submit();
  assert.equal(h.store.data.draft.rubricAttachments[0].sourceRevision, '13');
  assert.equal(h.state.saves, 1);
});

test('editing replaces only the selected answer and rereading confirms use of the same source', async () => {
  const old = material({id: 'old'});
  const sibling = material({id: 'sibling', sourceUrl: URL_TWO});
  const h = harness([old, sibling], {request: async () => ({material: material({id: 'new', sourceRevision: '14'})})});
  h.open(0, {reread: true});
  assert.match(h.state.html, /重新读取标准答案/); assert.match(h.state.html, /readonly/);
  h.field.value = URL_ONE; await h.submit();
  assert.equal(h.store.data.draft.rubricAttachments.length, 2);
  assert.equal(h.store.data.draft.rubricAttachments[0].id, 'new');
  assert.deepEqual(h.store.data.draft.rubricAttachments[1], sibling);
  assert.match(h.state.messages[0].message, /重新读取并保存/);
});

test('editing a source link imports the new document before replacing the old frozen answer', async () => {
  const work = deferred();
  const old = material();
  const h = harness([old], {request: () => work.promise});
  h.open(0); h.field.value = URL_TWO; const done = h.submit();
  assert.deepEqual(h.store.data.draft.rubricAttachments, [old]);
  assert.equal(h.state.requests[0].payload.url, URL_TWO);
  work.resolve({material: material({sourceUrl: URL_TWO, sourceTitle: '新答案', id: 'new-answer'})});
  await done;
  assert.equal(h.store.data.draft.rubricAttachments.length, 1);
  assert.equal(h.store.data.draft.rubricAttachments[0].sourceUrl, URL_TWO);
  assert.equal(h.store.data.draft.rubricAttachments[0].sourceTitle, '新答案');
});

test('four-document limit blocks new imports while editing an existing answer remains allowed', async () => {
  const files = Array.from({length: 4}, (_, index) => material({id: String(index), sourceUrl: `https://team.feishu.cn/docx/AnswerDocument000${index}`}));
  const h = harness(files); h.open();
  assert.equal(h.state.requests.length, 0); assert.equal(h.state.html, undefined);
  assert.match(h.state.messages[0].message, /最多附加 4 份/);
  const editing = harness(files, {request: async () => ({material: material({sourceUrl: files[0].sourceUrl})})});
  editing.open(0); editing.field.value = files[0].sourceUrl; await editing.submit();
  assert.equal(editing.state.saves, 1); assert.equal(editing.store.data.draft.rubricAttachments.length, 4);
});

test('duplicates with copied query strings fail before reading, and wiki aliases fail after canonical resolution', async () => {
  const previous = material();
  const h = harness([previous]); h.open(); h.field.value = URL_ONE + '?from=copy#text'; await h.submit();
  assert.match(h.nodes['#rubric-link-error'].textContent, /已添加/); assert.equal(h.state.requests.length, 0);
  h.field.value = WIKI; await h.submit();
  assert.equal(h.state.requests.length, 1); assert.match(h.nodes['#rubric-link-error'].textContent, /已添加/);
  assert.deepEqual(h.store.data.draft.rubricAttachments, [previous]); assert.equal(h.state.saves, 0);
});

test('double submit shares a single import and keeps both draft and success untouched until complete', async () => {
  const work = deferred();
  const h = harness([], {request: () => work.promise}); h.open(); h.field.value = URL_ONE;
  const first = h.submit(); await h.submit();
  assert.equal(h.state.requests.length, 1); assert.equal(h.button.disabled, true); assert.equal(h.field.disabled, true);
  assert.equal(h.state.saves, 0); assert.deepEqual(h.store.data.draft.rubricAttachments, []);
  work.resolve({material: material()}); await first;
  assert.equal(h.state.saves, 1); assert.equal(h.state.messages.length, 1);
});

test('cancel, close or opening a new dialog discards late successes without saving', async () => {
  for (const action of ['cancel', 'close', 'reopen']) {
    const work = deferred();
    const h = harness([], {request: () => work.promise}); h.open(); h.field.value = URL_ONE;
    const done = h.submit();
    if (action === 'reopen') h.open(); else h[action]();
    work.resolve({material: material()}); await done;
    assert.deepEqual(h.store.data.draft.rubricAttachments, []); assert.equal(h.state.saves, 0); assert.deepEqual(h.state.messages, []);
  }
});

test('a cancelled import that later fails does not alter the replacement dialog or show an error toast', async () => {
  const work = deferred();
  const h = harness([], {request: () => work.promise});
  h.open(); h.field.value = URL_ONE; const done = h.submit();
  h.cancel(); h.open();
  work.reject(new Error('旧请求权限不足')); await done;
  assert.deepEqual(h.store.data.draft.rubricAttachments, []);
  assert.equal(h.state.saves, 0); assert.deepEqual(h.state.messages, []);
  assert.equal(h.nodes['#rubric-link-error'].hidden, true);
});

test('switching task drafts or changing import context discards the late response', async () => {
  for (const change of ['draft', 'difficulty', 'camp']) {
    const work = deferred();
    const h = harness([], {request: () => work.promise}); h.open(); h.field.value = URL_ONE;
    const old = h.store.data.draft;
    const done = h.submit();
    if (change === 'draft') h.store.data.draft = {...old, id: 'different-task', rubricAttachments: []};
    else old[change] = change === 'camp' ? 'novice' : '挑战';
    work.resolve({material: material()}); await done;
    assert.deepEqual(old.rubricAttachments, []); assert.deepEqual(h.store.data.draft.rubricAttachments, []);
    assert.equal(h.state.saves, 0); assert.deepEqual(h.state.messages, []);
  }
});

test('concurrent list edits cannot overwrite a removed item or exceed the attachment limit', async () => {
  for (const editing of [false, true]) {
    const work = deferred();
    const original = material();
    const h = harness(editing ? [original] : [], {request: () => work.promise});
    h.open(editing ? 0 : null); h.field.value = URL_ONE; const done = h.submit();
    if (editing) h.store.data.draft.rubricAttachments = [];
    else h.store.data.draft.rubricAttachments = Array.from({length: 4}, (_, i) => ({name: `file-${i}.txt`}));
    const current = structuredClone(h.store.data.draft.rubricAttachments);
    work.resolve({material: material()}); await done;
    assert.deepEqual(h.store.data.draft.rubricAttachments, current); assert.equal(h.state.saves, 0);
    assert.match(h.nodes['#rubric-link-error'].textContent, editing ? /列表已更新/ : /最多附加 4 份/);
  }
});

test('failed local draft save rolls back additions and replacements and can retry', async () => {
  for (const editing of [false, true]) {
    const previous = material({sourceRevision: '1'});
    const h = harness(editing ? [previous] : []);
    h.open(editing ? 0 : null); h.field.value = URL_ONE; h.state.fail = true;
    await h.submit();
    assert.deepEqual(h.store.data.draft.rubricAttachments, editing ? [previous] : []);
    assert.equal(h.state.closes, 0); assert.deepEqual(h.state.messages, []);
    assert.match(h.nodes['#rubric-link-error'].textContent, /尚未保存/);
    h.state.fail = false; await h.submit();
    assert.equal(h.state.closes, 1); assert.equal(h.state.messages.length, 1);
  }
});

test('attachment rendering escapes text and unsafe sources, exposes source operations only for imports', () => {
  const imported = material({name: '<script>.txt', sourceTitle: '答案 "来源"<b>'});
  const editor = renderRubricAttachments([imported, {name: '旧文件.txt'}], {editable: true});
  assert.match(editor, /&lt;script&gt;.txt/); assert.match(editor, /答案 &quot;来源&quot;&lt;b&gt;/);
  assert.match(editor, /已读取/); assert.match(editor, /data-edit-rubric-link="0"/);
  assert.match(editor, /data-reread-rubric-link="0"/); assert.doesNotMatch(editor, /data-edit-rubric-link="1"/);
  assert.match(editor, /rel="noopener noreferrer"/);
  const detail = renderRubricAttachments([imported]);
  assert.match(detail, /打开源文档/); assert.match(detail, /下载已导入标准 TXT/);
  assert.match(detail, /data-rubric-download="0"/); assert.doesNotMatch(detail, /data-edit-rubric/);
  const malicious = renderRubricAttachments([material({sourceUrl: 'javascript:alert(1)'})]);
  assert.doesNotMatch(malicious, /javascript:|打开源文档/);
  assert.equal(rubricSourceUrl('https://evil.test/wiki/AnswerWikiNode0001'), '');
});

test('authoring and library wire the answer link module and cache refresh without changing score configuration', () => {
  const source = name => readFileSync(new URL(`../public/review-native/${name}`, import.meta.url), 'utf8');
  const app = source('app.js');
  assert.match(app, /createRubricLinkEditor\(\{store,request,openModal,closeModal,saveDraft,refresh:render,toast\}\)/);
  assert.match(app, /id="add-rubric-link"/); assert.match(app, /纯选择题也需要配置评分维度和通过分数/);
  assert.match(app, /renderRubricAttachments\(d.rubricAttachments/);
  assert.match(source('library.js'), /renderRubricAttachments\(task.rubricAttachments/);
  assert.match(source('index.html'), /app.js\?v=20261118-document-rubric/);
});
