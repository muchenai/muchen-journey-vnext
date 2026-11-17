import test from 'node:test';
import assert from 'node:assert/strict';
import {createMaterialEditor} from '../public/review-native/material-editor.js';
import {validateMaterialFields, isMaterialLink} from '../public/review-native/material-validation.js';
import {validateTask} from '../public/review-native/core.js';

function harness(materials = []) {
  const input = value => ({value, attrs: {}, setAttribute(k, v) {this.attrs[k] = v;}, addEventListener() {}, focus() {this.focused = true;}});
  const fields = {name: input(''), url: input('')};
  const nodes = Object.fromEntries(['#material-name-error', '#material-url-error', '#material-save-error', '[data-cancel-material]'].map(key => [key, {hidden: true}]));
  const form = {elements: {namedItem: key => fields[key]}};
  nodes['#material-form'] = form;
  const store = {data: {draft: {materials: structuredClone(materials)}}};
  const state = {closes: 0, saves: 0, messages: [], fail: false};
  const open = createMaterialEditor({store,
    openModal(html, ready) {state.html = html;ready({querySelector: key => nodes[key]});},
    closeModal() {state.closes++;},
    saveDraft() {state.saves++;return !state.fail;},
    refresh() {}, toast(message) {state.messages.push(message);},
  });
  return {store, state, fields, nodes, open, submit: () => form.onsubmit({preventDefault() {}})};
}

test('empty and whitespace-only names stay in the dialog without saving or success', () => {
  const original = {id: 'existing', name: '原材料', type: 'link', url: 'https://example.com'};
  for (const editing of [false, true]) {
  for (const name of ['', '   ', '\t\r\n', '\u3000\u00a0']) {
    const h = harness(editing ? [original] : []);h.open(editing ? 0 : null);h.fields.name.value = name;h.fields.url.value = 'https://example.com';h.submit();
    assert.deepEqual(h.store.data.draft.materials, editing ? [original] : []);
    assert.equal(h.state.saves, 0);assert.equal(h.state.closes, 0);assert.deepEqual(h.state.messages, []);
    assert.equal(h.nodes['#material-name-error'].hidden, false);
    assert.equal(h.nodes['#material-name-error'].textContent, name === '' ? '请填写材料名称' : '材料名称不能只包含空格');
    assert.equal(h.fields.name.attrs['aria-invalid'], 'true');assert.equal(h.fields.name.focused, true);
  }
  }
});

test('add trims surrounding spaces and preserves meaningful internal spaces', () => {
  const h = harness();h.open();h.fields.name.value = '  用户  访谈记录  ';h.fields.url.value = ' https://example.com/doc ';h.submit();
  assert.equal(h.store.data.draft.materials.length, 1);
  assert.equal(h.store.data.draft.materials[0].name, '用户  访谈记录');
  assert.equal(h.store.data.draft.materials[0].url, 'https://example.com/doc');
  assert.deepEqual(h.state.messages, ['材料已添加']);assert.equal(h.state.closes, 1);
});

test('invalid and backend-incompatible links are rejected before adding', () => {
  for (const url of ['', 'https://', 'hello', 'http://example.com', 'javascript:alert(1)', 'https://user:secret@example.com', 'https://example.com/' + 'x'.repeat(2000)]) {
    const h = harness();h.open();h.fields.name.value = '资料';h.fields.url.value = url;h.submit();
    assert.equal(h.state.saves, 0);assert.equal(h.nodes['#material-url-error'].hidden, false);
    assert.equal(isMaterialLink(url), false);
    assert.ok(validateTask({materials: [{name: '资料', type: 'link', url}]}).some(error => error.includes('HTTPS')));
  }
  assert.equal(isMaterialLink('https://example.com/doc?a=1#section'), true);
  assert.ok(validateMaterialFields({name: 'x'.repeat(161), url: 'https://example.com'}).errors.name);
});

test('editing pre-fills escaped values and updates the same item in place', () => {
  const original = {id: 'stable-id', name: '原始 "名称"', type: 'link', url: 'https://example.com/old?a=1&b=2'};
  const sibling = {id: 'other', name: '其它资料', type: 'link', url: 'https://example.com'};
  const h = harness([original, sibling]);h.open(0);
  assert.ok(h.state.html.includes('原始 &quot;名称&quot;'));assert.ok(h.state.html.includes('https://example.com/old?a=1&amp;b=2'));
  h.fields.name.value = ' 新名称 ';h.fields.url.value = ' https://example.com/new ';h.submit();
  assert.equal(h.store.data.draft.materials.length, 2);
  assert.deepEqual(h.store.data.draft.materials[0], {...original, name: '新名称', url: 'https://example.com/new'});
  assert.deepEqual(h.store.data.draft.materials[1], sibling);assert.deepEqual(h.state.messages, ['材料已更新']);
});

test('attachment edits preserve uploaded bytes and all metadata', () => {
  for (const type of ['file', 'image', 'text']) {
    const original = {id: type, name: '旧名称', type, url: 'data:text/plain;base64,YQ==', mime: 'text/plain', size: 1, text: '原文'};
    const h = harness([original]);h.open(0);
    assert.ok(!h.state.html.includes('name="url"'));
    h.fields.name.value = '新名称';h.submit();
    assert.deepEqual(h.store.data.draft.materials, [{...original, name: '新名称'}]);
  }
});

test('cancel and invalid edits leave the original material untouched', () => {
  const original = {id: 'one', name: '资料', type: 'link', url: 'https://example.com'};
  const h = harness([original]);h.open(0);h.fields.name.value = ' ';h.fields.url.value = original.url;h.submit();
  assert.deepEqual(h.store.data.draft.materials, [original]);assert.equal(h.state.saves, 0);
  h.nodes['[data-cancel-material]'].onclick();assert.equal(h.state.closes, 1);
  assert.deepEqual(h.store.data.draft.materials, [original]);
});

test('legacy blank names can be repaired one record at a time', () => {
  const originals = [1, 2].map(id => ({id, name: '   ', type: 'link', url: 'https://example.com'}));
  const h = harness(originals);h.open(0);h.fields.name.value = '已修复';h.fields.url.value = originals[0].url;h.submit();
  assert.equal(h.store.data.draft.materials[0].name, '已修复');assert.deepEqual(h.store.data.draft.materials[1], originals[1]);
  assert.ok(validateTask({materials: h.store.data.draft.materials}).includes('请填写材料 2 的名称'));
});

test('failed draft storage rolls back add and edit, preserves dialog, and can retry', () => {
  for (const index of [null, 0]) {
    const original = {id: 'one', name: '原资料', type: 'link', url: 'https://example.com'};
    const h = harness([original]);h.open(index);h.state.fail = true;h.fields.name.value = '新资料';h.fields.url.value = 'https://example.com/new';h.submit();
    assert.deepEqual(h.store.data.draft.materials, [original]);assert.equal(h.state.closes, 0);assert.deepEqual(h.state.messages, []);
    assert.equal(h.nodes['#material-save-error'].hidden, false);
    h.state.fail = false;h.submit();assert.equal(h.state.closes, 1);assert.equal(h.store.data.draft.materials.length, index === null ? 2 : 1);
  }
});
