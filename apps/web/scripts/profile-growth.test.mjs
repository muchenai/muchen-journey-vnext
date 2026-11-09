import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

class ApiRequestError extends Error { constructor(status,message){super(message);this.status=status;} }
function load(relative,globals={}){
  const filename=new URL(relative,import.meta.url);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const compiledModule ={exports:{}};
  vm.runInNewContext(code,{module: compiledModule,exports:compiledModule.exports,URL,Response,AbortController,...globals});
  return compiledModule.exports;
}
const helper=()=>load('../src/app/project29/profileGrowth.ts');
const route=apiRequest=>load('../src/app/api/learner/profile/history/route.ts',{require:name=>name==='next/server'?{NextResponse:Response}:{apiRequest,ApiRequestError}});
const request=(query='')=>({nextUrl:new URL(`http://localhost:3000/api/learner/profile/history${query}`)});
const wallet={xp:100,availableXp:100,redeemedXp:0,ownedMedalCount:0,badgeBalances:{product:10}};
const entry={id:'reward-1',kind:'task_reward',occurredAt:'2026-11-09T08:00:00Z',module:'新手村',title:'真实任务',xp:100,badgePoints:[{id:'product',points:10}],method:'任务审核通过'};

test('growth history proxy uses the current learner session and drops caller identity parameters',async()=>{
  const calls=[];
  const result=await route(async(...args)=>{calls.push(args);return {items:[],total:0,hasMore:false,nextOffset:null};}).GET(request('?offset=40&limit=20&learnerId=someone-else&organizationId=another-org'));
  assert.equal(result.status,200);assert.equal(result.headers.get('Cache-Control'),'no-store');
  assert.deepEqual(calls,[['/api/v1/me/novice/growth?offset=40&limit=20','LEARNER']]);
});

test('growth history proxy rejects invalid pagination without accessing the API',async()=>{
  let called=0;const target=route(async()=>{called++;return {};});
  for(const query of ['?offset=-1','?offset=1.5','?offset=2147483648','?offset=9007199254740992','?limit=0','?limit=101','?limit=1.5','?offset=../../admin']){
    const response=await target.GET(request(query));assert.equal(response.status,400);assert.equal(response.headers.get('Cache-Control'),'no-store');
  }
  assert.equal(called,0);
});

test('growth history proxy preserves authentication failures without an empty success response',async()=>{
  for(const status of [401,403,500]){
    const response=await route(async()=>{throw new ApiRequestError(status,'无法读取真实数据');}).GET(request());
    assert.equal(response.status,status);assert.equal(response.headers.get('Cache-Control'),'no-store');
    assert.deepEqual(await response.json(),{error:'无法读取真实数据'});
  }
});

test('wallet requires authoritative XP and badge counts rather than filling missing values with zero',()=>{
  const {parseProfileWallet}=helper();
  assert.equal(parseProfileWallet(wallet).availableXp,100);
  assert.equal(parseProfileWallet(wallet).ownedMedalCount,0);
  for(const field of ['xp','availableXp','redeemedXp','ownedMedalCount']){
    const missing={...wallet};delete missing[field];
    assert.throws(()=>parseProfileWallet(missing));
    for(const invalid of [-1,1.5,'0',null,Infinity])assert.throws(()=>parseProfileWallet({...wallet,[field]:invalid}));
  }
  assert.throws(()=>parseProfileWallet({...wallet,badgeBalances:{product:'10'}}));
});

test('growth history fetch stays in authenticated context and honors cancellation',async()=>{
  const calls=[];const signal=new AbortController().signal;
  const {readGrowthPage}=load('../src/app/project29/profileGrowth.ts',{fetch:async(...args)=>{calls.push(args);return Response.json({items:[entry],total:1,hasMore:false,nextOffset:null});}});
  const page=await readGrowthPage(0,signal);
  assert.equal(page.items[0].xp,100);assert.equal(calls.length,1);
  assert.equal(calls[0][0],'/api/learner/profile/history?offset=0&limit=20');
  assert.equal(calls[0][1].credentials,'same-origin');assert.equal(calls[0][1].cache,'no-store');assert.equal(calls[0][1].signal,signal);
  await assert.rejects(()=>readGrowthPage(-1,signal));assert.equal(calls.length,1);
});

test('growth history rejects failed HTTP responses and malformed or non-advancing pages',async()=>{
  const signal=new AbortController().signal;
  const failed=load('../src/app/project29/profileGrowth.ts',{fetch:async()=>Response.json({error:'登录已失效'},{status:401})});
  await assert.rejects(()=>failed.readGrowthPage(0,signal),/登录已失效/);
  const {parseGrowthPage}=helper();
  assert.throws(()=>parseGrowthPage({items:[{...entry,occurredAt:'invalid-date'}],total:1,hasMore:false,nextOffset:null}));
  assert.throws(()=>parseGrowthPage({items:[{...entry,xp:'100'}],total:1,hasMore:false,nextOffset:null}));
  const repeated=load('../src/app/project29/profileGrowth.ts',{fetch:async()=>Response.json({items:[entry],total:50,hasMore:true,nextOffset:20})});
  await assert.rejects(()=>repeated.readGrowthPage(20,signal),/分页异常/);
});
