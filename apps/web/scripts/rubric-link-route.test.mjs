import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const url = 'https://team.feishu.cn/wiki/AnswerReference1234';
const payload = { url, camp: 'exploration', difficulty: '' };
class ApiRequestError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}
function compile(path, dependencies) {
  const source = ts.transpileModule(readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const loaded = { exports: {} };
  vm.runInNewContext(source, { module: loaded, exports: loaded.exports, Buffer, URL,
    require: name => dependencies[name] || {} });
  return loaded.exports;
}
function loadRoute(error) {
  const calls = [];
  const material = { id: 'imported-answer', type: 'file', name: '标准答案.txt',
    mime: 'text/plain', size: 6, url: 'data:text/plain;base64,MS4gQQ==',
    sourceUrl: 'https://team.feishu.cn/docx/ResolvedAnswer1234', sourceRevision: '7', sourceTitle: '标准答案' };
  const route = compile('app/api/review-native/route.ts', {
    'next/server': { NextResponse: { json: (body, init) => Response.json(body, init) } },
    '@/lib/server/api': { ApiRequestError, apiRequest: async (...args) => {
      calls.push(args); if (error) throw error; return { material };
    } },
  });
  return { ...route, calls, material };
}
function request(body = { command: 'importRubricDocument', payload }, extraHeaders = {}) {
  return new Request('http://localhost:3000/api/review-native', { method: 'POST',
    headers: { origin: 'http://localhost:3000', host: 'localhost:3000',
      'content-type': 'application/json', ...extraHeaders }, body: JSON.stringify(body) });
}

test('private answer-link import reaches the authorized staff endpoint and preserves frozen attachment metadata', async () => {
  const route = loadRoute();
  const response = await route.POST(request());
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).data.material, route.material);
  assert.equal(route.calls.length, 1);
  assert.equal(route.calls[0][0], '/api/v1/review-admin/rubric-documents/import');
  assert.equal(route.calls[0][1], 'REVIEWER');
  assert.equal(route.calls[0][2].method, 'POST');
  assert.deepEqual(JSON.parse(route.calls[0][2].body), payload);
});

test('answer-link import rejects malformed requests and foreign origins before document access', async () => {
  const route = loadRoute();
  for (const data of [
    { ...payload, url: null }, { ...payload, url: 'x'.repeat(2001) },
    { ...payload, camp: 'other' }, { ...payload, difficulty: 'unlimited' },
  ]) assert.equal((await route.POST(request({ command: 'importRubricDocument', payload: data }))).status, 400);
  assert.equal((await route.POST(request(undefined, { origin: 'https://other.example' }))).status, 403);
  assert.equal((await route.POST(request(undefined, { 'sec-fetch-site': 'cross-site' }))).status, 403);
  assert.equal((await route.POST(request(undefined, { 'content-type': 'text/plain' }))).status, 415);
  assert.equal(route.calls.length, 0);
});

test('answer-link import keeps authentication, publisher and document-read failures explicit', async () => {
  for (const [status, message] of [
    [401, '请先登录。'], [403, '仅超级管理员可以执行此操作。'],
    [422, '请输入有效的标准答案飞书文档链接。'], [502, '标准答案文档没有读取权限。'],
  ]) {
    const route = loadRoute(new ApiRequestError(message, status));
    const response = await route.POST(request());
    assert.equal(response.status, status);
    assert.equal((await response.json()).error, message);
    assert.equal(route.calls.length, 1);
  }
});

test('saved tasks and publisher sandbox retain imported private answer bytes and source revision', async () => {
  const calls = [], material = loadRoute().material;
  const actions = compile('app/review/admin-actions.ts', { '@/lib/server/api': {
    apiRequest: async (...args) => { calls.push(args); return { id: 'saved' }; },
  } });
  const task = { id: '00000731-0000-4000-8000-000000000001', revision: 2,
    camp: 'exploration', rubricAttachments: [material] };
  assert.equal((await actions.saveAdminTask(task)).ok, true);
  assert.equal((await actions.testAdminTask(task, '1. A；2. B')).ok, true);
  assert.deepEqual(JSON.parse(calls[0][2].body).content.rubricAttachments, [material]);
  assert.deepEqual(JSON.parse(calls[1][2].body).task.rubricAttachments, [material]);
});
