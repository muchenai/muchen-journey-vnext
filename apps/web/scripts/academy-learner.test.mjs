import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const id = '11111111-1111-4111-8111-111111111111';
const root = new URL('../src/', import.meta.url);
const next = { NextResponse: { json: (data, init) => Response.json(data, init) } };
class ApiRequestError extends Error { constructor(message, status) { super(message); this.status = status; } }
function load(path, dependencies, extras = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, root), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(code, { module: compiledModule, exports: compiledModule.exports, require: name => dependencies[name], Request, Response, Headers, URL, Buffer, ...extras });
  return compiledModule.exports;
}
function learnerRoute() {
  const calls = [];
  const route = load('app/api/learner/academy/route.ts', { 'next/server': next, '@/lib/server/api': { ApiRequestError, apiRequest: async (...args) => { calls.push(args); return { ok: true }; } } });
  const post = (body, headers = {}) => route.POST(new Request('http://localhost:3000/api/learner/academy', { method: 'POST', headers: { 'Origin': 'http://localhost:3000', 'Host': 'localhost:3000', 'Content-Type': 'application/json', ...headers }, body: typeof body === 'string' ? body : JSON.stringify(body) }));
  return { route, calls, post };
}

test('learner snapshot and favorites use only learner-scoped academy endpoints', async () => {
  const h = learnerRoute();
  assert.equal((await h.route.GET()).status, 200);
  assert.equal((await h.post({ command: 'favorite', id, saved: true })).status, 200);
  assert.equal(h.calls[0][0], '/api/v1/me/academy');
  assert.equal(h.calls[1][0], `/api/v1/me/academy/courses/${id}/favorite`);
  assert.ok(h.calls.every(call => call[1] === 'LEARNER'));
  assert.deepEqual(JSON.parse(h.calls[1][2].body), { saved: true });
});

test('cross-origin, malformed, oversized and invalid ID requests never reach backend', async () => {
  const h = learnerRoute();
  assert.equal((await h.post({ command: 'favorite', id, saved: true }, { Origin: 'https://unrelated.example' })).status, 403);
  assert.equal((await h.post({ command: 'favorite', id, saved: true }, { 'Sec-Fetch-Site': 'cross-site' })).status, 403);
  assert.equal((await h.post('{')).status, 400);
  assert.equal((await h.post('x'.repeat(20001))).status, 413);
  assert.equal((await h.post({ command: 'favorite', id: '../../staff', saved: true })).status, 400);
  assert.equal((await h.post({ command: 'progress', id, seconds: -5, duration: 1 })).status, 400);
  assert.equal(h.calls.length, 0);
});

test('share resubmission preserves expected revision and does not allow arbitrary backend fields', async () => {
  const h = learnerRoute();
  const payload = { command: 'resubmit', id, revision: 4, title: '学习实践', summary: '可复用的方法', url: 'https://example.com/lesson', minutes: 15, tags: ['AI 入门'], authorId: 'another-user', status: 'approved' };
  assert.equal((await h.post(payload)).status, 200);
  const [path, role, init] = h.calls[0];
  assert.equal(path, `/api/v1/me/academy/shares/${id}`);
  assert.equal(role, 'LEARNER'); assert.equal(init.method, 'PATCH');
  const body = JSON.parse(init.body);
  assert.equal(body.expected_revision, 4);
  assert.equal(body.authorId, undefined); assert.equal(body.status, undefined);
});

test('share creation retries retain the same draft ID and video checkpoints carry course revision', async () => {
  const h = learnerRoute();
  const body = { command: 'share', id, title: '学习实践', summary: '可复用的方法', url: 'https://example.com/', minutes: 15, tags: [] };
  await h.post(body); await h.post(body);
  assert.equal(JSON.parse(h.calls[0][2].body).id, id);
  assert.equal(JSON.parse(h.calls[1][2].body).id, id);
  await h.post({ command: 'progress', id, seconds: 30, duration: 120, revision: 8 });
  assert.equal(JSON.parse(h.calls[2][2].body).expected_revision, 8);
});

function mediaHarness(values = {}, env = {}, upstream) {
  const calls = [];
  const media = load('lib/server/academy-media.ts', {
    'server-only': {}, 'next/server': next,
    'next/headers': { cookies: async () => ({ get: name => values[name] ? { value: values[name] } : undefined }) },
    '@/lib/auth/cookies': { SESSION_COOKIE: 'learner-session', STAFF_SESSION_COOKIE: 'staff-session' },
  }, { process: { env }, fetch: async (url, init) => { calls.push({ url: String(url), init }); return upstream ? upstream(init) : new Response(init.method === 'HEAD' ? null : new Uint8Array([1, 2]), { status: 206, headers: { 'Content-Type': 'video/mp4', 'Content-Range': 'bytes 0-1/10', 'Accept-Ranges': 'bytes', 'Content-Length': '2' } }); } });
  return { ...media, calls };
}

test('video streams range response with learner cookie only and ignores backend URLs supplied by clients', async () => {
  const h = mediaHarness({ 'learner-session': 'learner-token', 'staff-session': 'staff-token' });
  const response = await h.proxyAcademyVideo(new Request('http://localhost:3000/api/learner/academy', { headers: { Range: 'bytes=0-1' } }), id, 'LEARNER');
  assert.equal(response.status, 206);
  assert.equal(response.headers.get('Content-Range'), 'bytes 0-1/10');
  assert.equal(response.headers.get('Cache-Control'), 'private, no-store');
  assert.deepEqual([...new Uint8Array(await response.arrayBuffer())], [1, 2]);
  const call = h.calls[0];
  assert.equal(call.url, `http://localhost:8000/api/v1/me/academy/courses/${id}/video`);
  assert.equal(call.init.headers.get('Cookie'), 'learner-session=learner-token');
  assert.equal(call.init.headers.get('X-Journey-Session-Scope'), 'learner');
  assert.equal(call.init.headers.get('Range'), 'bytes=0-1');
});

test('staff media uses staff session and HEAD, never the learner cookie', async () => {
  const h = mediaHarness({ 'learner-session': 'learner-token', 'staff-session': 'staff-token' });
  const response = await h.proxyAcademyVideo(new Request('http://localhost:3000/api/review-native/academy', { method: 'HEAD' }), id, 'REVIEWER');
  assert.equal(await response.text(), '');
  assert.equal(h.calls[0].init.headers.get('Cookie'), 'staff-session=staff-token');
  assert.equal(h.calls[0].init.headers.get('X-Journey-Session-Scope'), 'staff');
  assert.equal(h.calls[0].init.method, 'HEAD');
  assert.ok(h.calls[0].url.includes('/api/v1/ops/academy/'));
});

test('video version validators survive the proxy and stale If-Range returns the complete new resource', async () => {
  const etag = '"new-video-sha256"';
  const h = mediaHarness({ 'learner-session': 'learner-token' }, {}, init => {
    const matches = init.headers.get('If-Range') === etag;
    return new Response(matches ? new Uint8Array([3, 4]) : new Uint8Array([1, 2, 3, 4]), {
      status: matches ? 206 : 200,
      headers: { 'Content-Type': 'video/mp4', 'Content-Length': matches ? '2' : '4', ETag: etag, ...(matches ? { 'Content-Range': 'bytes 2-3/4' } : {}) },
    });
  });
  const stale = await h.proxyAcademyVideo(new Request('http://localhost:3000/', { headers: { Range: 'bytes=2-3', 'If-Range': '"old-video-sha256"' } }), id, 'LEARNER');
  assert.equal(h.calls[0].init.headers.get('If-Range'), '"old-video-sha256"');
  assert.equal(stale.status, 200);
  assert.equal(stale.headers.get('ETag'), etag);
  assert.equal(stale.headers.get('Content-Range'), null);
  assert.equal(stale.headers.get('Content-Length'), '4');
  assert.equal(stale.headers.get('Cache-Control'), 'private, no-store');
  assert.deepEqual([...new Uint8Array(await stale.arrayBuffer())], [1, 2, 3, 4]);
  const matching = await h.proxyAcademyVideo(new Request('http://localhost:3000/', { headers: { Range: 'bytes=2-3', 'If-Range': etag } }), id, 'LEARNER');
  assert.equal(matching.status, 206);
  assert.equal(matching.headers.get('ETag'), etag);
  assert.equal(matching.headers.get('Content-Range'), 'bytes 2-3/4');
});

test('invalid or oversized If-Range never reaches the video backend', async () => {
  const h = mediaHarness({ 'learner-session': 'learner-token' });
  for (const value of ['unquoted-value', '"' + 'x'.repeat(256) + '"']) {
    const response = await h.proxyAcademyVideo(new Request('http://localhost:3000/', { headers: { 'If-Range': value } }), id, 'LEARNER');
    assert.equal(response.status, 400);
  }
  assert.equal(h.calls.length, 0);
});

test('unauthenticated media and invalid multi-range requests are rejected before fetch', async () => {
  const h = mediaHarness();
  assert.equal((await h.proxyAcademyVideo(new Request('http://localhost:3000/'), id, 'LEARNER')).status, 401);
  assert.equal((await h.proxyAcademyVideo(new Request('http://localhost:3000/', { headers: { Range: 'bytes=0-1,5-6' } }), id, 'LEARNER')).status, 416);
  assert.equal((await h.proxyAcademyVideo(new Request('http://localhost:3000/'), '../secrets', 'LEARNER')).status, 400);
  assert.equal(h.calls.length, 0);
});

test('fixture media access remains limited to local and test environments', async () => {
  const prod = mediaHarness({}, { ALLOW_FIXTURE_IDENTITY: 'true', APP_ENV: 'production' });
  assert.equal((await prod.proxyAcademyVideo(new Request('http://localhost:3000/'), id, 'LEARNER')).status, 401);
  const local = mediaHarness({}, { ALLOW_FIXTURE_IDENTITY: 'true', APP_ENV: 'local' });
  assert.equal((await local.proxyAcademyVideo(new Request('http://localhost:3000/'), id, 'LEARNER')).status, 206);
  assert.equal(local.calls[0].init.headers.get('X-Fixture-Role'), 'LEARNER');
});
