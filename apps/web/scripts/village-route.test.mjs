import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const task='00000000-0000-4000-8000-000000000001';
const assignment='00000000-0000-4000-8000-000000000002';
function load(apiRequest,route='village'){
  const source=readFileSync(new URL(`../src/app/api/learner/${route}/route.ts`,import.meta.url),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const mod={exports:{}};
  vm.runInNewContext(code,{module:mod,exports:mod.exports,URL,Buffer,require:name=>name==='next/server'
    ?{NextResponse:Response}:{apiRequest,ApiRequestError:class extends Error{}}});
  return mod.exports;
}
test('profile wallet uses only the current learner session and never substitutes demo balances',async()=>{
  const calls=[];
  const route=load(async(...args)=>{calls.push(args);return {xp:200,badgeBalances:{product:20}}},'profile');
  const response=await route.GET();
  assert.equal(response.status,200);assert.equal(response.headers.get('Cache-Control'),'no-store');
  assert.deepEqual(calls,[['/api/v1/me/novice/wallet','LEARNER']]);
  assert.deepEqual(await response.json(),{xp:200,badgeBalances:{product:20}});
  const failed=await load(async()=>{throw Error('offline')},'profile').GET();
  assert.equal(failed.status,500);assert.equal(failed.headers.get('Cache-Control'),'no-store');
  assert.deepEqual(await failed.json(),{error:'成长数据读取失败，请重试。'});
});
function request(body,origin='http://localhost:3000'){
  return {headers:new Headers({origin,host:'localhost:3000','content-type':'application/json'}),text:async()=>JSON.stringify(body)};
}
test('village mutations enforce origin and resolve only a learner-owned assignment',async()=>{
  const calls=[];const route=load(async(...args)=>{calls.push(args);return {assignmentId:assignment};});
  const body={command:'submit',taskId:task,key:task,revision:2,answer:'answer',assignmentId:'malicious-assignment'};
  assert.equal((await route.POST(request(body,'https://untrusted.example'))).status,403);assert.equal(calls.length,0);
  assert.equal((await route.POST(request(body))).status,200);
  assert.equal(calls[0][0],`/api/v1/me/novice/tasks/${task}`);
  assert.equal(calls[1][0],`/api/v1/me/assignments/${assignment}/submissions`);
  for(const call of calls) assert.equal(call[1],'LEARNER');
  assert.deepEqual(JSON.parse(calls[1][2].body),{expected_revision:2,body:'answer',attachment_ids:[]});
});
test('learning files are authenticated downloads, never inline executable data',async()=>{
  const calls=[];const route=load(async(...args)=>{calls.push(args);return {name:'学习资料.txt',mime:'text/plain',data:Buffer.from('materials').toString('base64')};});
  const response=await route.GET({nextUrl:new URL(`http://localhost:3000/api/learner/village?task=${task}&material=0`)});
  assert.equal(response.status,200);assert.equal(await response.text(),'materials');
  assert.match(response.headers.get('Content-Disposition'),/^attachment;/);
  assert.equal(response.headers.get('Cache-Control'),'no-store');assert.equal(calls[0][1],'LEARNER');
});
test('invalid tasks and unclaimed submissions never reach mutation endpoints',async()=>{
  const calls=[];const route=load(async(...args)=>{calls.push(args);return {assignmentId:null};});
  assert.equal((await route.GET({nextUrl:new URL('http://localhost:3000/api/learner/village?task=../../admin')})).status,400);
  assert.equal(calls.length,0);
  assert.equal((await route.POST(request({command:'submit',taskId:task,key:task,revision:1,answer:'test'}))).status,400);
  assert.equal(calls.length,1);
});
