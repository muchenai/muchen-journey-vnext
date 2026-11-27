import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const taskId = '00000720-0000-4000-8000-000000000001';
const reviewerId = '00000720-0000-4000-8000-000000000002';
const key = '00000720-0000-4000-8000-000000000003';
function compile(path, imports) {
  const source = readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(code, {
    module: mod, exports: mod.exports, Request, Response, Headers, URL, Buffer,
    require: name => imports[name] || {},
  });
  return mod.exports;
}
function loadRoute(result = { ok: true, data: { id: taskId } }) {
  const calls = [];
  const route = compile('app/api/review-native/route.ts', {
    'next/server': { NextResponse: { json: (body, init) => Response.json(body, init) } },
    '@/lib/server/api': { apiRequest: async (...args) => { calls.push(args); return result.data; } },
    '@/app/review/admin-actions': { publishAdminTask: async (...args) => { calls.push(args); return result; } },
  });
  return { ...route, calls };
}
function publish(camp, payload = { verified: [] }, origin = 'http://localhost:3000') {
  return new Request('http://localhost:3000/api/review-native', {
    method: 'POST', headers: { origin, host: 'localhost:3000', 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: 'publishTask', task: { id: taskId, revision: 1, camp }, key, payload }),
  });
}
test('exploration publication reaches backend without choosing another reviewer and preserves authorization failures', async () => {
  const route = loadRoute();
  assert.equal((await route.POST(publish('exploration'))).status, 200);
  assert.equal(route.calls.length, 1);
  assert.deepEqual(Array.from(route.calls[0][1]), []);
  assert.equal(route.calls[0][2], key);
  const denied = loadRoute({ ok: false, status: 403, error: '仅超级管理员可以执行此操作。' });
  const response = await denied.POST(publish('exploration'));
  assert.equal(response.status, 403);
  assert.match((await response.json()).error, /超级管理员/);
});
test('novice publication needs no named reviewer and cross-origin requests are rejected', async () => {
  const route = loadRoute();
  assert.equal((await route.POST(publish('novice'))).status, 200);
  assert.equal((await route.POST(publish('exploration', { verified: [], reviewerId: 'invalid' }))).status, 400);
  assert.equal((await route.POST(publish('exploration', { verified: [] }, 'https://other.example'))).status, 403);
  assert.equal(route.calls.length, 1);
  assert.equal((await route.POST(publish('novice', { verified: [], reviewerId }))).status, 200);
  assert.deepEqual(Array.from(route.calls[1][1]), []);
});
test('the delete gateway forwards revision zero for legacy exploration tasks', async () => {
  const route = loadRoute();
  const remove = revision => new Request('http://localhost:3000/api/review-native', {
    method: 'POST', headers: {origin: 'http://localhost:3000', host: 'localhost:3000', 'Content-Type': 'application/json'},
    body: JSON.stringify({command: 'deleteTask', task: {id: taskId, revision}, key}),
  });
  assert.equal((await route.POST(remove(0))).status, 200);
  assert.equal((await route.POST(remove(-1))).status, 400);
  assert.equal((await route.POST(remove('0'))).status, 400);
  assert.equal(route.calls.length, 1);
  const [path, role, options] = route.calls[0];
  assert.equal(path, `/api/v1/review-admin/tasks/${taskId}/delete`);
  assert.equal(role, 'REVIEWER');
  assert.deepEqual(JSON.parse(options.body), {expected_revision: 0});
  assert.equal(options.headers['Idempotency-Key'], key);
});

test('server publication adapter leaves reviewer attribution to the server for both camps', async () => {
  const calls = [];
  const actions = compile('app/review/admin-actions.ts', {
    '@/lib/server/api': { apiRequest: async (...args) => { calls.push(args); return { id: taskId }; } },
  });
  const task = { id: taskId, revision: 4, camp: 'exploration' };
  assert.equal((await actions.publishAdminTask(task, ['https://example.com'], key)).ok, true);
  await actions.publishAdminTask({ ...task, camp: 'novice' }, [], key);
  for (const call of calls) {
    assert.equal(call[0], `/api/v1/review-admin/tasks/${taskId}/publish`);
    assert.equal(call[2].headers['Idempotency-Key'], key);
  }
  assert.deepEqual(JSON.parse(calls[0][2].body), { expected_revision: 4, verified_material_urls: ['https://example.com'] });
  assert.equal('reviewed_by' in JSON.parse(calls[1][2].body), false);
});
