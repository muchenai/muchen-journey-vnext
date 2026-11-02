import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
function load(file, deps={}) {
  const source=readFileSync(new URL('../src/app/'+file,import.meta.url),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const mod={exports:{}};
  vm.runInNewContext(code,{module:mod,exports:mod.exports,URL,require:name=>deps[name]});
  return mod.exports;
}
const economy=load('project29/badgeEconomy.ts');
const filters=load('project29/taskDepartments.ts',{'./badgeEconomy':economy});
const task=(department,extra={})=>({publishingDepartment:department,title:'真实任务',description:'说明',category:'产品开发',level:'入门',review:'人工审核',rewardAllocations:[{id:'product',points:5}],...extra});
test('delivery aggregate includes exactly the seven publishing departments, never badge/category inference',()=>{
  const delivery=filters.taskDepartments.filter(d=>d.delivery);
  assert.equal(delivery.length,7);
  const tasks=filters.taskDepartments.map(d=>task(d.name));
  tasks.push(task('',{category:'数据交付',rewardAllocations:[{id:'data',points:10}]}));
  assert.equal(filters.filterDepartmentTasks(tasks,'delivery').length,7);
  assert.equal(filters.filterDepartmentTasks(tasks,'all').length,20);
  for(const d of delivery) assert.equal(filters.filterDepartmentTasks(tasks,d.id).length,1);
  assert.equal(filters.belongsToDepartment(task('总经办',{category:'数据交付'}),'delivery'),false);
});
test('department, level, review, keyword and reward filters compose and reset restores all',()=>{
  const tasks=[task('IT部'),task('开发部'),task('IT部',{level:'挑战'}),task('IT部',{review:'AI 自测'})];
  assert.equal(filters.filterDepartmentTasks(tasks,'it','入门','人工审核','IT部','产品开发').length,1);
  assert.equal(filters.filterDepartmentTasks(tasks,'it','入门','人工审核','','数据交付').length,0);
  assert.equal(filters.filterDepartmentTasks(tasks,'all').length,4);
});
test('medals adapt only actual balances and historical ownership; no demo balance or duplicate owned medal',()=>{
  const result=economy.adaptMedals({medals:[],wallet:{badgeBalances:{product:12}},redemptions:[{id:'receipt',medalId:'old',medalName:'历史徽章',image:'',style:'gold',costs:[{badgeId:'product',points:3}],redeemedAt:'2026-10-30T00:00:00Z'}]});
  assert.equal(result.badges.length,1);assert.equal(result.badges[0].published,false);
  assert.equal(result.wallet.owned[0],'old');assert.equal(result.wallet.balances['产品开发'],12);
  assert.equal(result.wallet.balances['数据交付'],0);assert.equal(result.wallet.history[0].at,'2026-10-30T00:00:00Z');
  assert.equal(economy.badgeCostStatus(result.wallet,{requirements:[{type:'产品开发',amount:13}]}).affordable,false);
});
test('medal proxy rejects cross-origin/invalid requests and uses only learner identity',async()=>{
  const calls=[];const route=load('api/learner/medals/route.ts',{'next/server':{NextResponse:Response},'@/lib/server/api':{apiRequest:async(...args)=>{calls.push(args);return {};},ApiRequestError:class extends Error{}}});
  const id='00000000-0000-4000-8000-000000000001';
  const request=(origin,body)=>({headers:new Headers({origin,host:'localhost:3000','content-type':'application/json'}),text:async()=>JSON.stringify(body)});
  assert.equal((await route.POST(request('https://elsewhere.test',{medalId:id,revision:1}))).status,403);
  assert.equal((await route.POST(request('http://localhost:3000',{medalId:'../admin',revision:1}))).status,400);
  assert.equal(calls.length,0);
  assert.equal((await route.GET()).headers.get('Cache-Control'),'no-store');
  assert.equal((await route.POST(request('http://localhost:3000',{medalId:id,revision:3,learnerId:'other'}))).status,200);
  assert.ok(calls.every(call=>call[1]==='LEARNER'));
  assert.deepEqual(JSON.parse(calls[1][2].body),{expected_revision:3});
});
