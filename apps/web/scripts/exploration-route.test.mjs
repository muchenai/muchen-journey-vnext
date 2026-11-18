import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const taskId = '00000710-0000-4000-8000-000000000001';
const key = '00000710-0000-4000-8000-000000000002';
class ApiRequestError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}
function loadRoute(path, overrides = {}) {
  const calls = [];
  const source = readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(code, {
    module: mod, exports: mod.exports, Response, Request, Headers, URL, URLSearchParams, Buffer, TransformStream,
    require: name => name === '@/lib/server/api' ? {
      ApiRequestError, apiRequest: async (...args) => { calls.push(args); return overrides.result || { items: [] }; },
    } : { explorationMaterialResponse: async (...args) => { calls.push(['material', ...args]); return new Response('file'); } },
  });
  return { ...mod.exports, calls };
}
function post(body, origin = 'http://localhost:3000') {
  return new Request('http://localhost:3000/api/learner/exploration', {
    method: 'POST', headers: { origin, host: 'localhost:3000', 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
}
test('exploration reads real learner catalog, task and self-check history', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts');
  for (const query of ['', `?task=${taskId}`, `?task=${taskId}&selfChecks=1`, '?treasures=1']) {
    assert.equal((await route.GET(new Request(`http://localhost:3000/api/learner/exploration${query}`))).status, 200);
  }
  assert.deepEqual(route.calls.map(call => new URL(call[0], 'http://api').searchParams.get('command')), ['learnerSnapshot', 'learnerTask', 'selfCheckHistory', 'treasures']);
  assert.ok(route.calls.every(call => call[1] === 'LEARNER'));
});
test('exploration writes retain reference commands and forward scoped idempotency', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts');
  const result = await route.POST(post({ command: 'completeLearning', taskId, revision: 3, idempotencyKey: key, checkinConfirmed: true }));
  assert.equal(result.status, 200);
  const [path, role, init] = route.calls[0];
  assert.equal(path, '/api/v1/me/exploration');
  assert.equal(role, 'LEARNER');
  assert.equal(init.headers['Idempotency-Key'], key);
  assert.deepEqual(JSON.parse(init.body), { command: 'completeLearning', key, taskId, revision: 3, checkinConfirmed: true });
});
test('the full 8000-character Chinese answer fits, including legacy duplicate body', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts');
  const answer = '学'.repeat(8000);
  const result = await route.POST(post({ command: 'draft', taskId, revision: 3, key, answer, body: answer }));
  assert.equal(result.status, 200);
  assert.equal(JSON.parse(route.calls[0][2].body).answer, answer);
  assert.equal('body' in JSON.parse(route.calls[0][2].body), false);
});
test('exploration rejects invalid origins, commands and identifiers before backend writes', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts');
  assert.equal((await route.POST(post({ command: 'claim', taskId, key }, 'https://other.example'))).status, 403);
  assert.equal((await route.POST(post({ command: 'publishTask', taskId, key }))).status, 400);
  assert.equal((await route.POST(post({ command: 'claim', taskId, key: 'bad' }))).status, 400);
  assert.equal((await route.GET(new Request('http://localhost:3000/api/learner/exploration?task=bad'))).status, 400);
  assert.equal(route.calls.length, 0);
});
test('exploration cancellation is rejected locally without forwarding a backend write', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts');
  const response = await route.POST(post({ command: 'cancel', taskId, key, revision: 3 }));
  assert.equal(response.status, 409);
  assert.equal((await response.json()).error, '探索营任务接取后不能取消。');
  assert.equal(route.calls.length, 0);
  assert.equal(response.headers.get('Cache-Control'), 'private, no-store');
});
test('private material download resolves learner task scope before streaming', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts', { result: { id: key, name: '培训视频.mp4', mime: 'video/mp4' } });
  const result = await route.GET(new Request(`http://localhost:3000/api/learner/exploration?task=${taskId}&material=0&inline=1`));
  assert.equal(await result.text(), 'file');
  assert.equal(new URL(route.calls[0][0], 'http://api').searchParams.get('command'), 'material');
  assert.equal(new URL(route.calls[0][0], 'http://api').searchParams.has('group'), false);
  assert.equal(route.calls[1][0], 'material');
  assert.equal(route.calls[1][2], key);
  assert.equal(route.calls[1][3], 'LEARNER');
});
test('task document downloads preserve their independent group and learner authorization', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts', { result: { id: key, name: '练习题.docx', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' } });
  const result = await route.GET(new Request(`http://localhost:3000/api/learner/exploration?task=${taskId}&material=0&group=task`));
  assert.equal(result.status, 200);
  assert.equal(await result.text(), 'file');
  const params = new URL(route.calls[0][0], 'http://api').searchParams;
  assert.equal(params.get('command'), 'material');
  assert.equal(params.get('taskId'), taskId);
  assert.equal(params.get('index'), '0');
  assert.equal(params.get('group'), 'task');
  assert.equal(route.calls[0][1], 'LEARNER');
  assert.equal(route.calls[1][2], key);
  assert.equal(route.calls[1][3], 'LEARNER');
});
test('invalid task document groups and mixed commands never request or stream files', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts', { result: { id: key } });
  for (const query of [
    `?task=${taskId}&material=0&group=unknown`,
    `?task=${taskId}&material=0&group=`,
    `?task=${taskId}&group=task`,
    '?material=0&group=task',
    `?task=${taskId}&material=0&group=task&selfChecks=1`,
    `?task=${taskId}&material=0&group=task&treasures=1`,
  ]) {
    assert.equal((await route.GET(new Request(`http://localhost:3000/api/learner/exploration${query}`))).status, 400, query);
  }
  assert.equal(route.calls.length, 0);
});
test('legacy data URL documents are served as attachments through learner authorization', async () => {
  const route = loadRoute('app/api/learner/exploration/route.ts', { result: { name: '说明.html', mime: 'text/html', data: Buffer.from('<script>bad()</script>').toString('base64') } });
  const result = await route.GET(new Request(`http://localhost:3000/api/learner/exploration?task=${taskId}&material=0&inline=1`));
  assert.match(result.headers.get('Content-Disposition'), /^attachment;/);
  assert.equal(result.headers.get('X-Content-Type-Options'), 'nosniff');
});
test('material upload streams files and rejects oversized files and foreign origins', async () => {
  const route = loadRoute('app/api/review-native/exploration/materials/route.ts');
  const upload = (extra = {}) => new Request('http://localhost:3000/api/review-native/exploration/materials?name=notes.txt&type=file', {
    method: 'POST', headers: { origin: 'http://localhost:3000', host: 'localhost:3000', 'Content-Type': 'text/plain', ...extra }, body: 'notes',
  });
  assert.equal((await route.POST(upload({ 'content-length': String(100 * 1024 * 1024 + 1) }))).status, 413);
  assert.equal((await route.POST(upload({ origin: 'https://other.example' }))).status, 403);
  assert.equal(route.calls.length, 0);
  assert.equal((await route.POST(upload())).status, 200);
  assert.equal(route.calls[0][1], 'REVIEWER');
  assert.equal(route.calls[0][2].duplex, 'half');
  assert.equal(await new Response(route.calls[0][2].body).text(), 'notes');
});
