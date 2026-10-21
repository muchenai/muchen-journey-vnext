import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

function loadApi(values, fetch) {
  const source = readFileSync(new URL('../src/lib/server/api.ts', import.meta.url), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022 } }).outputText;
  const mod = { exports:{} };
  vm.runInNewContext(code, { module:mod, exports:mod.exports, Headers, URL, fetch,
    process:{env:{APP_ENV:'local',ALLOW_FIXTURE_IDENTITY:'false',API_INTERNAL_URL:'http://api:8000'}},
    require: name => name === 'next/headers' ? { cookies:async()=>({get:key=>values[key] ? {value:values[key]} : undefined}) }
      : name === '@/lib/auth/cookies' ? { SESSION_COOKIE:'session',CSRF_COOKIE:'csrf' } : {},
  });
  return mod.exports;
}

test('anonymous real Review requests fail as authentication errors, never as fixture or network failures', async () => {
  let calls = 0;
  const api = loadApi({}, async()=>{ calls++; });
  await assert.rejects(()=>api.apiRequest('/api/v1/review-admin/reviews','REVIEWER'), e=>e.status===401 && e.code==='UNAUTHENTICATED');
  assert.equal(calls,0);
});

test('real reviewer and operator requests forward only the signed session and CSRF', async () => {
  const calls=[];
  const api=loadApi({session:'signed-session',csrf:'signed-csrf'},async(url,init)=>{calls.push(init);return {ok:true,json:async()=>({data:{ok:true}})};});
  await api.apiRequest('/api/v1/review-admin/reviews','REVIEWER');
  await api.apiRequest('/api/v1/review-admin/tasks/example','OPERATOR',{method:'PUT',body:'{}'});
  for(const init of calls) { assert.equal(init.headers.has('X-Fixture-Role'),false);assert.equal(init.headers.get('Cookie'),'session=signed-session; csrf=signed-csrf'); }
  assert.equal(calls[1].headers.get('X-CSRF-Token'),'signed-csrf');
});
