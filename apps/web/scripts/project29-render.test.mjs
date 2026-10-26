import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import vm from 'node:vm';
import test from 'node:test';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../src');
const nativeRequire=createRequire(import.meta.url), cache=new Map();
function load(filename) {
  if(filename.endsWith('.css'))return {};
  if(filename.endsWith('.json'))return JSON.parse(readFileSync(filename,'utf8'));
  if(cache.has(filename))return cache.get(filename).exports;
  const compiledModule={exports:{}};cache.set(filename,compiledModule);
  const source=ts.transpileModule(readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022,esModuleInterop:true},fileName:filename}).outputText;
  const require=(name)=>{
    if(name==='next/navigation')return {useRouter:()=>({refresh(){}})};
    if(name.endsWith('/actions'))return new Proxy({}, {get:()=>()=>{throw Error('Unexpected render mutation')}});
    if(!name.startsWith('.')&&!name.startsWith('@/'))return nativeRequire(name);
    const base=name.startsWith('@/')?path.join(root,name.slice(2)):path.resolve(path.dirname(filename),name);
    const target=[base,base+'.ts',base+'.tsx'].find(existsSync);
    assert.ok(target,`Missing import ${name}`);return load(target);
  };
  vm.runInThisContext('(function(require,module,exports){'+source+'\n})',{filename})(require,compiledModule,compiledModule.exports);
  return compiledModule.exports;
}
const {default:App,Login}=load(path.join(root,'app/project29/App.tsx'));
const {JourneyProvider}=load(path.join(root,'app/project29/journey-context.tsx'));
const {TaskCards,ExecutionView,executionTasks}=load(path.join(root,'app/project29/ExecutionPages.tsx'));
const {SelfCheckHistory}=load(path.join(root,'app/project29/SelfCheckHistory.tsx'));
const {ReviewNotificationPanel}=load(path.join(root,'app/project29/ReviewNotificationBell.tsx'));

test('review notification panel contains only reminders and independent read actions',()=>{
  const props={panelId:'notifications',unread:1,busy:false,loading:false,loaded:true,error:'',cursor:'next',
    mark:async()=>{},refresh:async()=>{},items:[
      {id:'review1',assignmentId:'task1',taskTitle:'Day 1 测试任务',decision:'REVISION_REQUIRED',reviewedAt:'2026-10-26T06:00:00Z',readAt:null,feedback:'绝不能展示的评语'},
      {id:'review2',assignmentId:'task2',taskTitle:'宝藏一测试任务',decision:'PASS',reviewedAt:'2026-10-26T05:00:00Z',readAt:'2026-10-26T06:00:00Z'},
    ]};
  const html=renderToStaticMarkup(React.createElement(ReviewNotificationPanel,props));
  assert.match(html,/Day 1 测试任务/);assert.doesNotMatch(html,/宝藏一测试任务/);
  assert.match(html,/已退回，请修改/);
  assert.equal((html.match(/标为已读/g)||[]).length,1);
  assert.match(html,/全部已读/);assert.match(html,/查看更多/);
  assert.match(html,/datetime="2026-10-26T06:00:00Z"/i);
  assert.doesNotMatch(html,/绝不能展示的评语/);
  const empty=renderToStaticMarkup(React.createElement(ReviewNotificationPanel,{...props,items:[],unread:0,cursor:null}));
  assert.match(empty,/暂无未读通知/);assert.match(empty,/disabled="">全部已读/);
  const allRead=renderToStaticMarkup(React.createElement(ReviewNotificationPanel,{...props,items:[props.items[1]],unread:0,cursor:null}));
  assert.match(allRead,/暂无未读通知/);assert.doesNotMatch(allRead,/宝藏一测试任务|标为已读/);
});
const data={assignmentId:'a1',status:'IN_PROGRESS',revision:3,taskVersion:2,title:'真实任务',purpose:'学习',shortDescription:'学习',learnerOutcome:'记录',referenceMaterials:[],estimatedMinutes:10,stageKind:'DAY_0',stageKey:'DAY-0',stagePosition:1,currentAssignmentId:'a1',currentStagePosition:1,allowedCommands:['submit'],materials:[],draftBody:'',completedStages:0,totalStages:8,reviewerDisplayName:'真实审核员',latestSubmissionBody:null,latestSubmissionVersion:null,latestSubmissionCreatedAt:null,latestFeedback:null,latestFeedbackAt:null,pendingReviewAssignmentId:null,activityRecords:[],reviewFeedback:[],journeyTasks:Array.from({length:8},(_,i)=>({assignmentId:'a'+(i+1),position:i+1,status:i===0?'CURRENT':'LOCKED',assignmentStatus:i===0?'IN_PROGRESS':'AVAILABLE',title:executionTasks[i].title,shortDescription:''}))};
const value={initialScreen:'dashboard',learnerName:'真实姓名',experience:data,joinPhase:'feishu',joinError:''};
const inside=(component,experience=data)=>renderToStaticMarkup(React.createElement(JourneyProvider,{value:{...value,experience}},component));
const render=(props={})=>renderToStaticMarkup(React.createElement(App,{...value,...props}));

test('new dashboard renders real learner state without browser globals or demo review controls',()=>{
  const html=render();
  assert.match(html,/updated-dashboard/);assert.match(html,/真实姓名/);
  assert.doesNotMatch(html,/模拟导师审核|模拟 AI 评分|邀请码 111|账户 333|12月31日/);
  assert.match(html,/李魔王老师/);assert.match(html,/产品设计导师/);
  assert.match(html,/暂无待审核任务/);
  const pending={...data,activityRecords:[{assignmentId:'a1',position:1,status:'SUBMITTED',body:'真实提交内容',submittedAt:'2026-10-26T00:00:00Z',feedback:null,feedbackAt:null}],journeyTasks:[{...data.journeyTasks[0],assignmentStatus:'SUBMITTED'}]};
  assert.match(render({experience:pending}),/真实提交内容/);
  assert.match(render({experience:pending}),/待审核任务 · 1/);
});
test('all source pages render safely, and unavailable modules never show invented learner progress',()=>{
  for(const initialScreen of ['welcome','tasks','detail','view','village','academy','guild']) {
    const html=render({initialScreen});assert.ok(html.length>1000,initialScreen);
    if(['village','academy','guild'].includes(initialScreen))assert.doesNotMatch(html,/许知微 · 通过了|<strong>20<\/strong>|module-tag">L2|<small>L2<|10<small>%|示例内容 · 本次会话体验/);
  }
});

test('returned work shows revision on both task surfaces until resubmitted and approved',()=>{
  for(const [assignmentStatus,label,journeyStatus] of [
    ['NEEDS_REVISION','待修改','CURRENT'],
    ['SUBMITTED','待审核','CURRENT'],
    ['IN_REVIEW','待审核','CURRENT'],
    ['COMPLETED','已完成','COMPLETED'],
  ]) {
    const experience={...data,status:assignmentStatus,journeyTasks:data.journeyTasks.map((node,index)=>
      index===0?{...node,assignmentStatus,status:journeyStatus,isRevising:assignmentStatus==='NEEDS_REVISION'}:
      {...node,assignmentStatus:'COMPLETED',status:'COMPLETED'})};
    const cards=inside(React.createElement(TaskCards),experience);
    const firstCard=cards.slice(cards.indexOf('<button'),cards.indexOf('</button>'));
    assert.ok(firstCard.includes(`journey-task-status">${label}<`),assignmentStatus);
    const dashboard=render({experience});
    assert.ok(dashboard.includes(`>${label}</span>`),assignmentStatus);
    if(assignmentStatus==='NEEDS_REVISION') {
      assert.match(firstCard,/去修改/);
      assert.doesNotMatch(firstCard,/进行中|提交后进入待审核/);
      assert.doesNotMatch(render({initialScreen:'tasks',experience}),/旅程完成/);
    }
  }
});
test('existing password login, registration and reset are retained',()=>{
  const html=inside(React.createElement(Login));
  assert.match(html,/注册账号/);assert.match(html,/忘记密码/);assert.match(html,/autocomplete="current-password"/i);
  assert.doesNotMatch(html,/本地预览可填写|验证码登录接口尚未接入/);
});
test('graduation card uses actual server code and does not invent completion',()=>{
  const html=inside(React.createElement(TaskCards),{...data,completionCode:{status:'READY',code:'REAL-CODE'}});
  assert.match(html,/探索营毕业码/);assert.match(html,/REAL-CODE/);assert.match(html,/复制毕业码/);
});
test('submitted evidence stays read-only and existing revision actions remain',()=>{
  const html=inside(React.createElement(ExecutionView,{task:executionTasks[0],record:'真实证据',setRecord(){},readOnly:true,canRevise:true,submitDisabled:true,submitLabel:'已提交，等待审核'}));
  assert.match(html,/readOnly=""/i);assert.match(html,/重新修改/);assert.match(html,/已提交，等待审核/);
});
test('new history design receives real records including failures and prior results',()=>{
  const html=inside(React.createElement(SelfCheckHistory,{task:executionTasks[0],onClose(){},error:'本次读取失败',records:[{id:'check1',createdAt:'2026-10-26T00:00:00Z',body:'https://example.com/doc',result:'之前真实自查结果',status:'COMPLETED'}]}));
  assert.match(html,/self-check-dialog/);assert.match(html,/之前真实自查结果/);assert.match(html,/本次读取失败/);
});

export { render, data };

test('phone nickname setup renders the supplied welcome dialog over the exploration dashboard',()=>{
  const html=render({initialScreen:'dashboard',joinPhase:'nickname'});
  assert.match(html,/welcome-name-dialog/);
  assert.match(html,/欢迎加入探索营/);
  assert.match(html,/请输入您的真实姓名/);
  assert.match(html,/确认姓名，进入探索营/);
  assert.match(html,/updated-dashboard/);
  assert.doesNotMatch(html,/当前为前端演示|仅保存在本机浏览器|code-field|autocomplete="current-password"/i);
});
