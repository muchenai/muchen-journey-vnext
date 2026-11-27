import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import * as jsxRuntime from 'react/jsx-runtime';

class ApiRequestError extends Error { constructor(status,message){super(message);this.status=status;} }
function load(relative,globals={}){
  const filename=new URL(relative,import.meta.url);
  const code=ts.transpileModule(readFileSync(filename,'utf8'),{fileName:filename.pathname,compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
  const compiledModule={exports:{}};
  vm.runInNewContext(code,{module:compiledModule,exports:compiledModule.exports,URL,Response,AbortController,...globals});
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
  assert.equal(parseProfileWallet(wallet).mallPoints,undefined);
  assert.equal(parseProfileWallet({...wallet,mallPoints:0}).mallPoints,0);
  for(const mallPoints of ['1',null,-1,1.5,Number.MAX_SAFE_INTEGER+1])
    assert.throws(()=>parseProfileWallet({...wallet,mallPoints}));
});

test('growth history preserves prior reward types and verifies the debited XP against the credited mall points',()=>{
  const {parseGrowthPage}=helper();
  const page=item=>parseGrowthPage({items:[item],total:1,hasMore:false,nextOffset:null});
  for(const kind of ['task_reward','course_reward','offline_grant','medal_redemption']){
    assert.equal(page({...entry,kind}).items[0].kind,kind);
  }
  const exchange={...entry,kind:'mall_exchange',module:'沐晨商城',xp:-20,mallPoints:2,badgePoints:[]};
  assert.equal(page(exchange).items[0].xp,-20);
  for(const override of [{mallPoints:undefined},{mallPoints:0},{mallPoints:-2},{mallPoints:'2'},{xp:-10},{xp:20}]){
    assert.throws(()=>page({...exchange,...override}));
  }
});

test('exchange proxy forwards the learner request and retry key, rejecting malformed input before any write',async()=>{
  const calls=[];
  const apiRequest=async(...args)=>{calls.push(args);return {wallet:{...wallet,mallPoints:1}};};
  const target=load('../src/app/api/learner/experience/route.ts',{require:name=>name==='next/server'?{NextResponse:Response}:{apiRequest,ApiRequestError}});
  const key=randomUUID();
  const send=(body,headers={})=>target.POST(new Request('http://localhost:3000/api/learner/experience',{
    method:'POST',body:JSON.stringify(body),headers:{host:'localhost:3000',origin:'http://localhost:3000','Content-Type':'application/json','Idempotency-Key':key,...headers},
  }));
  for(const points of [null,0,-1,1.1,'1',Number.MAX_SAFE_INTEGER+1])assert.equal((await send({points})).status,400);
  assert.equal((await send({points:1,learnerId:'another-learner'})).status,400);
  assert.equal((await send({points:1},{'Idempotency-Key':'bad'})).status,400);
  assert.equal((await send({points:1},{origin:'http://different.example'})).status,403);
  assert.equal(calls.length,0);
  for(let attempt=0;attempt<2;attempt++){
    const result=await send({points:1});
    assert.equal(result.status,200);assert.equal((await result.json()).wallet.mallPoints,1);
    const [path,role,init]=calls[attempt];
    assert.equal(path,'/api/v1/me/profile/exchange');assert.equal(role,'LEARNER');
    assert.equal(init.method,'POST');assert.equal(init.headers['Idempotency-Key'],key);
    assert.deepEqual(JSON.parse(init.body),{points:1});
  }
});

// Render the form's event handlers with the same hook slots across a retry.
function exchangeForm(fetch, mallExchangeAvailable = true) {
  const slots=[];
  let cursor=0;
  const react={
    useRef(initial){const i=cursor++;return slots[i]??={current:initial};},
    useState(initial){const i=cursor++;if(!(i in slots))slots[i]=initial;return [slots[i],value=>{slots[i]=value;}];},
  };
  const modules={react,'react/jsx-runtime':jsxRuntime,'./profileGrowth':helper(),'./ModuleShell':{ModuleIcon:'icon',ModulePanel:'section'}};
  const {ProfileExchange}=load('../src/app/project29/ProfileExchange.tsx',{require:name=>modules[name],fetch,crypto});
  const receipts=[];
  function find(tree,type){
    if(!tree || typeof tree!=='object')return;
    if(tree.type===type)return tree;
    for(const child of [tree.props?.children].flat(Infinity)){const result=find(child,type);if(result)return result;}
  }
  return {receipts,render(){
    cursor=0;
    const tree=ProfileExchange({wallet:{...wallet,mallPoints:0,mallExchangeAvailable},refresh(){},onExchanged:updated=>receipts.push(updated),showHistory(){}});
    const form=find(tree,'form');
    if (!form) return {form,entry:find(tree,'button').props,status:find(tree,'p')?.props?.children};
    return {input:find(form,'input').props,button:find(form,'button').props,submit:()=>form.props.onSubmit({preventDefault(){}})};
  }};
}

test('closed exchange keeps the entry clickable and reports 暂未开放 without posting',()=>{
  let posts=0;
  const view=exchangeForm(()=>{posts++;},false);
  const panel=view.render();
  assert.equal(panel.form,undefined);
  assert.equal(panel.entry.children,'经验兑换商城积分');
  panel.entry.onClick();
  assert.equal(view.render().status,'暂未开放');
  assert.equal(posts,0);
});

test('exchange form blocks invalid and in-flight submissions, reuses the uncertain request key and applies the confirmed wallet',async()=>{
  const calls=[];
  let finish;
  const receipt={wallet:{...wallet,availableXp:80,redeemedXp:20,mallPoints:2}};
  const view=exchangeForm((url,init)=>{
    calls.push({url,init});
    return new Promise(resolve=>{finish=resolve;});
  });
  for(const value of ['', '0', '-1', '1.5', '11']){
    view.render().input.onChange({target:{value}});
    const invalid=view.render();assert.equal(invalid.button.disabled,true);
    await invalid.submit();
  }
  assert.equal(calls.length,0);
  view.render().input.onChange({target:{value:'2'}});
  const first=view.render().submit();
  assert.equal(view.render().button.disabled,true);
  await view.render().submit();
  assert.equal(calls.length,1);
  finish(Response.json({error:'暂时无法确认这笔兑换'},{status:503}));await first;
  assert.equal(view.receipts.length,0);assert.equal(view.render().button.disabled,false);
  const second=view.render().submit();
  assert.equal(calls.length,2);
  const retryKey=calls[0].init.headers['Idempotency-Key'];
  assert.match(retryKey,/^[\da-f-]{36}$/);
  for(const {url,init} of calls){
    assert.equal(url,'/api/learner/experience');assert.equal(init.method,'POST');
    assert.equal(init.credentials,'same-origin');assert.equal(init.headers['Idempotency-Key'],retryKey);
    assert.deepEqual(JSON.parse(init.body),{points:2});
  }
  finish(Response.json(receipt));await second;
  assert.deepEqual(view.receipts,[receipt.wallet]);assert.equal(view.render().button.disabled,true);
  view.render().input.onChange({target:{value:'1'}});
  const next=view.render().submit();
  assert.notEqual(calls[2].init.headers['Idempotency-Key'],retryKey);
  finish(Response.json({wallet:{...receipt.wallet,availableXp:70,redeemedXp:30,mallPoints:3}}));await next;
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
