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
      : name === '@/lib/auth/cookies' ? { SESSION_COOKIE:'session',CSRF_COOKIE:'csrf',STAFF_SESSION_COOKIE:'staff_session',STAFF_CSRF_COOKIE:'staff_csrf' } : {},
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
  const api=loadApi({staff_session:'signed-session',staff_csrf:'signed-csrf',session:'phone-session',csrf:'phone-csrf'},async(url,init)=>{calls.push(init);return {ok:true,json:async()=>({data:{ok:true}})};});
  await api.apiRequest('/api/v1/review-admin/reviews','REVIEWER');
  await api.apiRequest('/api/v1/review-admin/tasks/example','OPERATOR',{method:'PUT',body:'{}'});
  for(const init of calls) { assert.equal(init.headers.has('X-Fixture-Role'),false);assert.equal(init.headers.get('Cookie'),'staff_session=signed-session; staff_csrf=signed-csrf'); }
  assert.equal(calls[1].headers.get('X-CSRF-Token'),'signed-csrf');
});


test('each workspace uses only its own cookie pair and authoritative scope', async () => {
  const calls=[];
  const api=loadApi({staff_session:'admin',staff_csrf:'admin-csrf',session:'phone',csrf:'phone-csrf'},async(url,init)=>{calls.push(init);return {ok:true,json:async()=>({data:{}})};});
  await api.apiRequest('/api/v1/session','LEARNER');
  await api.apiRequest('/api/v1/session/logout','REVIEWER',{method:'POST',headers:{'X-Journey-Session-Scope':'learner'}});
  assert.equal(calls[0].headers.get('Cookie'),'session=phone; csrf=phone-csrf');
  assert.equal(calls[0].headers.get('X-Journey-Session-Scope'),'learner');
  assert.equal(calls[1].headers.get('Cookie'),'staff_session=admin; staff_csrf=admin-csrf');
  assert.equal(calls[1].headers.get('X-Journey-Session-Scope'),'staff');
  assert.equal(calls[1].headers.get('X-CSRF-Token'),'admin-csrf');
});

test('a workspace never falls back to the other workspace login', async () => {
  let calls=0;
  const fetch=async()=>{calls++;};
  await assert.rejects(()=>loadApi({session:'phone'},fetch).apiRequest('/api/v1/session','REVIEWER'),e=>e.status===401);
  await assert.rejects(()=>loadApi({staff_session:'admin'},fetch).apiRequest('/api/v1/session','LEARNER'),e=>e.status===401);
  assert.equal(calls,0);
});

test('native administrator logout clears only staff cookies after revocation', async () => {
  const source=readFileSync(new URL('../src/app/api/review-native/route.ts',import.meta.url),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  for (const fail of [false,true]) {
    const values={session:'phone',csrf:'phone-csrf',staff_session:'admin',staff_csrf:'admin-csrf'};
    const calls=[];const mod={exports:{}};
    vm.runInNewContext(code,{module:mod,exports:mod.exports,Headers,URL,Buffer,
      require:name=>name==='next/server'?{NextResponse:{json:(body,options)=>({body,...options})}}:
      name==='next/headers'?{cookies:async()=>({delete:key=>{delete values[key];}})}:
      name==='@/lib/auth/cookies'?{STAFF_SESSION_COOKIE:'staff_session',STAFF_CSRF_COOKIE:'staff_csrf'}:
      name==='@/lib/server/api'?{ApiRequestError:class extends Error {},apiRequest:async(...args)=>{calls.push(args);if(fail)throw Error('unavailable');}}:{} });
    const response=await mod.exports.POST({headers:new Headers({origin:'http://localhost:3000',host:'localhost:3000','content-type':'application/json'}),text:async()=>JSON.stringify({command:'logout'})});
    assert.equal(calls[0][1],'REVIEWER');
    assert.equal(values.session,'phone');assert.equal(values.csrf,'phone-csrf');
    assert.equal(response.status,fail?500:200);
    assert.equal(values.staff_session,fail?'admin':undefined);
    assert.equal(values.staff_csrf,fail?'admin-csrf':undefined);
  }
});
