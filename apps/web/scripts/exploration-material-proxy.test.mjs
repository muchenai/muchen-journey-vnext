import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const materialId = '00000710-0000-4000-8000-000000000003';
class ApiRequestError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}
function loadProxy(response) {
  const calls = [];
  const source = readFileSync(new URL('../src/lib/server/exploration-material-proxy.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;
  const mod = {exports: {}};
  vm.runInNewContext(code, {
    module: mod, exports: mod.exports, Response, Request, Headers, URL, URLSearchParams,
    require: name => name === 'server-only' ? {} : {
      ApiRequestError, apiResponse: async (...args) => {
        calls.push(args);
        if (response instanceof Error) throw response;
        return response;
      },
    },
  });
  return {...mod.exports, calls};
}
test('material downloads use staff and learner routes with their existing scoped sessions', async () => {
  for (const role of ['LEARNER', 'REVIEWER', 'OPERATOR', 'CONTENT_EDITOR']) {
    const proxy = loadProxy(new Response('questions'));
    const result = await proxy.explorationMaterialResponse(
      new Request('http://localhost:3000/api/file?inline=1'), materialId, role,
    );
    assert.equal(await result.text(), 'questions');
    const [path, actualRole, init] = proxy.calls[0];
    assert.equal(path, `/api/v1/${role === 'LEARNER' ? 'me' : 'review-admin'}/exploration/materials/${materialId}?inline=1`);
    assert.equal(actualRole, role);
    assert.equal(init.redirect, 'error');
    assert.equal(init.method, 'GET');
  }
});
test('material proxy preserves ranges, private headers and HEAD without buffering a body', async () => {
  const backendHeaders = {
    'Content-Type': 'application/octet-stream', 'Content-Length': '4',
    'Content-Range': 'bytes 2-5/9', 'Accept-Ranges': 'bytes',
    'Content-Disposition': 'attachment; filename=questions.pdf', ETag: '"verified-file"',
    'Set-Cookie': 'must-not-propagate=1',
  };
  const proxy = loadProxy(new Response('esti', {status: 206, headers: backendHeaders}));
  const result = await proxy.explorationMaterialResponse(
    new Request('http://localhost:3000/api/file', {headers: {Range: 'bytes=2-5'}}), materialId, 'REVIEWER',
  );
  assert.equal(result.status, 206);
  assert.equal(await result.text(), 'esti');
  assert.equal(proxy.calls[0][2].headers.get('Range'), 'bytes=2-5');
  for (const [name, value] of Object.entries(backendHeaders)) {
    assert.equal(result.headers.get(name), name === 'Set-Cookie' ? null : value);
  }
  assert.equal(result.headers.get('Cache-Control'), 'private, no-store');
  assert.equal(result.headers.get('X-Content-Type-Options'), 'nosniff');
  const headProxy = loadProxy(new Response(null, {headers: {'Content-Length': '9'}}));
  const head = await headProxy.explorationMaterialResponse(
    new Request('http://localhost:3000/api/file', {method: 'HEAD'}), materialId, 'REVIEWER',
  );
  assert.equal(headProxy.calls[0][2].method, 'HEAD');
  assert.equal(head.headers.get('Content-Length'), '9');
  assert.equal(await head.text(), '');
});
test('invalid material requests and backend denials cannot stream attachments', async () => {
  const proxy = loadProxy(new Response('unreachable'));
  assert.equal((await proxy.explorationMaterialResponse(new Request('http://localhost:3000/api/file'), 'bad-id', 'REVIEWER')).status, 400);
  assert.equal((await proxy.explorationMaterialResponse(
    new Request('http://localhost:3000/api/file', {headers: {Range: 'bytes=0-5,8-9'}}), materialId, 'LEARNER',
  )).status, 416);
  assert.equal(proxy.calls.length, 0);
  const denied = loadProxy(new ApiRequestError('没有找到可访问的任务文件。', 404));
  const result = await denied.explorationMaterialResponse(new Request('http://localhost:3000/api/file'), materialId, 'LEARNER');
  assert.equal(result.status, 404);
  assert.equal(result.headers.get('Cache-Control'), 'private, no-store');
  assert.deepEqual(await result.json(), {error: '没有找到可访问的任务文件。'});
});
