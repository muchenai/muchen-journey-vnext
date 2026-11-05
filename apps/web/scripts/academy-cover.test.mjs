import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const id = '11111111-1111-4111-8111-111111111111';
const source = 'a'.repeat(64);
const jpeg = new Uint8Array([255, 216, 255, 224, 0, 0, 255, 217]);
const root = new URL('../src/', import.meta.url);
const next = { NextResponse: { json: (data, init) => Response.json(data, init) } };
function load(path, dependencies, extras = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, root), 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(code, { module: compiledModule, exports: compiledModule.exports, require: name => dependencies[name],
    Request, Response, Headers, URL, Uint8Array, AbortSignal, setTimeout: fn => { fn(); return 0; }, ...extras });
  return compiledModule.exports;
}
function proxy({ values = { 'learner-session': 'learner-token', 'staff-session': 'staff-token' }, env = {}, upstream } = {}) {
  const calls = [];
  const exports = load('lib/server/academy-cover.ts', {
    'server-only': {}, 'next/server': next,
    'next/headers': { cookies: async () => ({ get: name => values[name] ? { value: values[name] } : undefined }) },
    '@/lib/auth/cookies': { SESSION_COOKIE: 'learner-session', STAFF_SESSION_COOKIE: 'staff-session' },
  }, { process: { env }, fetch: async (url, init) => {
    calls.push({ url: String(url), init });
    return upstream ? upstream(init, calls.length) : new Response(init.method === 'HEAD' ? null : jpeg, {
      headers: { 'Content-Type': 'image/jpeg', 'Content-Length': String(jpeg.length), ETag: '"cover-hash"' },
    });
  } });
  const request = (options = {}, path = `http://localhost:3000/api/learner/academy/courses/${id}/cover?source=${source}`) => new Request(path, options);
  return { ...exports, calls, request };
}

test('course cover proxies only its fixed endpoint and isolated learner session', async () => {
  const h = proxy();
  const r = await h.proxyAcademyCover(h.request({}, `http://localhost:3000/cover?source=${source}&url=https://untrusted.invalid/`), id, 'LEARNER');
  assert.equal(r.status, 200);
  assert.deepEqual(new Uint8Array(await r.arrayBuffer()), jpeg);
  assert.equal(r.headers.get('Content-Type'), 'image/jpeg');
  assert.equal(r.headers.get('Cache-Control'), 'private, no-cache');
  assert.equal(r.headers.get('Vary'), 'Cookie');
  assert.equal(h.calls[0].url, `http://localhost:8000/api/v1/me/academy/courses/${id}/cover?source=${source}`);
  assert.equal(h.calls[0].init.headers.get('Cookie'), 'learner-session=learner-token');
  assert.equal(h.calls[0].init.headers.get('X-Journey-Session-Scope'), 'learner');
  assert.equal(h.calls[0].init.redirect, 'error');
});

test('staff HEAD uses staff cookie and successful conditional requests have no body', async () => {
  const h = proxy();
  const r = await h.proxyAcademyCover(h.request({ method: 'HEAD' }), id, 'REVIEWER');
  assert.equal(r.status, 200);
  assert.equal(await r.text(), '');
  assert.equal(r.headers.get('Content-Length'), String(jpeg.length));
  assert.equal(h.calls[0].init.headers.get('Cookie'), 'staff-session=staff-token');
  assert.ok(h.calls[0].url.includes('/ops/academy/'));
  const conditional = proxy({ upstream: () => new Response(null, { status: 304, headers: { ETag: '"cover-hash"' } }) });
  const unchanged = await conditional.proxyAcademyCover(conditional.request({ headers: { 'If-None-Match': '"cover-hash"' } }), id, 'LEARNER');
  assert.equal(unchanged.status, 304);
  assert.equal(await unchanged.text(), '');
  assert.equal(unchanged.headers.get('Cache-Control'), 'private, no-cache');
  assert.equal(conditional.calls[0].init.headers.get('If-None-Match'), '"cover-hash"');
});

test('unauthenticated or invalid cover requests never reach the API', async () => {
  const h = proxy();
  assert.equal((await h.proxyAcademyCover(h.request(), '../other', 'LEARNER')).status, 400);
  assert.equal((await h.proxyAcademyCover(h.request({}, 'http://localhost/?source=../private'), id, 'LEARNER')).status, 400);
  assert.equal((await h.proxyAcademyCover(h.request({ headers: { 'If-None-Match': 'x'.repeat(1000) } }), id, 'LEARNER')).status, 400);
  assert.equal(h.calls.length, 0);
  const unauthenticated = proxy({ values: { 'staff-session': 'staff-token' }, env: { APP_ENV: 'production', ALLOW_FIXTURE_IDENTITY: 'true' } });
  assert.equal((await unauthenticated.proxyAcademyCover(unauthenticated.request(), id, 'LEARNER')).status, 401);
  assert.equal(unauthenticated.calls.length, 0);
});

test('unavailable covers and invalid image content are not cached as successful images', async () => {
  for (const upstream of [
    () => new Response('missing', { status: 404 }),
    () => new Response('<svg/>', { headers: { 'Content-Type': 'image/svg+xml' } }),
    () => new Response('broken jpeg', { headers: { 'Content-Type': 'image/jpeg' } }),
    () => new Response(new Uint8Array(1024 * 1024 + 1), { headers: { 'Content-Type': 'image/jpeg' } }),
  ]) {
    const h = proxy({ upstream });
    const r = await h.proxyAcademyCover(h.request(), id, 'LEARNER');
    assert.ok([404, 502].includes(r.status));
    assert.equal(r.headers.get('Cache-Control'), 'private, no-store');
    assert.equal(h.calls.length, 1);
  }
});

test('pending generation retries are bounded and stop on success or definite failure', async () => {
  const ready = proxy({ upstream: (init, count) => count === 1 ? new Response(null, { status: 425 }) : new Response(jpeg, { headers: { 'Content-Type': 'image/jpeg' } }) });
  assert.equal((await ready.proxyAcademyCover(ready.request(), id, 'LEARNER')).status, 200);
  assert.equal(ready.calls.length, 2);
  const pending = proxy({ upstream: () => new Response(null, { status: 425 }) });
  const response = await pending.proxyAcademyCover(pending.request(), id, 'LEARNER');
  assert.equal(response.status, 425);
  assert.equal(response.headers.get('Retry-After'), '2');
  assert.equal(pending.calls.length, 11);
});

function coverHarness() {
  const state = []; let cursor = 0;
  const element = (type, props, key) => ({ type, props, key });
  const coverModule = load('app/project29/AcademyCourseCover.tsx', {
    react: { useState: initial => { const slot = cursor++; if (!(slot in state)) state[slot] = initial; return [state[slot], value => { state[slot] = value; }]; } },
    'react/jsx-runtime': { jsx: element, jsxs: element, Fragment: 'fragment' },
    './ModuleCourseArtwork': { ModuleCourseArtwork: 'default-artwork' },
  });
  const render = props => { cursor = 0; const wrapper = coverModule.AcademyCourseCover(props); return wrapper.type(wrapper.props); };
  const flatten = value => Array.isArray(value) ? value.flatMap(flatten) : value && typeof value === 'object' ? [value, ...flatten(value.props?.children)] : [];
  return { ...coverModule, render, flatten };
}

test('card cover accepts no remote image URLs and changes component identity when its source changes', () => {
  const h = coverHarness();
  const course = { id, type: 'link', coverUrl: `/api/v1/me/academy/courses/${id}/cover?source=${source}` };
  assert.equal(h.academyCoverSource(course), `/api/learner/academy/courses/${id}/cover?source=${source}`);
  for (const coverUrl of [undefined, 'https://example.com/cover.jpg', '//example.com/image', `/api/v1/me/academy/courses/22222222-2222-4222-8222-222222222222/cover?source=${source}`]) {
    assert.equal(h.academyCoverSource({ ...course, coverUrl }), undefined);
  }
  const old = h.AcademyCourseCover({ course, index: 0 });
  const changed = h.AcademyCourseCover({ course: { ...course, coverUrl: course.coverUrl.replace(source, 'b'.repeat(64)) }, index: 0 });
  assert.notEqual(old.key, changed.key);
});

test('card retains the original illustration until loaded and restores it without a broken image on failure', () => {
  const h = coverHarness(), props = { course: { id, type: 'video', coverUrl: `/api/v1/me/academy/courses/${id}/cover?source=${source}` }, index: 2 };
  let tree = h.flatten(h.render(props));
  assert.ok(tree.some(el => el.type === 'default-artwork'));
  let img = tree.find(el => el.type === 'img');
  assert.equal(img.props.loading, 'lazy'); assert.equal(img.props.decoding, 'async');
  assert.equal(img.props.className, 'academy-cover-image');
  img.props.onLoad();
  tree = h.flatten(h.render(props));
  assert.ok(!tree.some(el => el.type === 'default-artwork'));
  img = tree.find(el => el.type === 'img');
  assert.equal(img.props.className, 'academy-cover-image is-loaded');
  img.props.onError();
  tree = h.flatten(h.render(props));
  assert.ok(tree.some(el => el.type === 'default-artwork'));
  assert.ok(!tree.some(el => el.type === 'img'));
});
