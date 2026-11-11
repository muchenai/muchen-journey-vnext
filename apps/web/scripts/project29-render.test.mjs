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
  const compiledModule ={exports:{}};cache.set(filename,compiledModule);
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
const {VillageTaskCard,VillageTaskRewards}=load(path.join(root,'app/project29/VillageTaskCard.tsx'));
const {FavoriteKnowledge}=load(path.join(root,'app/project29/FavoriteKnowledge.tsx'));
const {PersonalProfileView}=load(path.join(root,'app/project29/PersonalProfile.tsx'));
const {profileGrowthLevel}=load(path.join(root,'app/project29/profileGrowth.ts'));
const {ProfileBadgeWall}=load(path.join(root,'app/project29/ProfileBadgeWall.tsx'));
const {parseProfileCollection}=load(path.join(root,'app/project29/profileBadges.ts'));
const {GrowthHistoryContent}=load(path.join(root,'app/project29/GrowthHistoryDialog.tsx'));
const {AccountSwitchDialog}=load(path.join(root,'app/project29/AccountSwitchDialog.tsx'));

test('personal profile shows actual rewards and growth levels with mall exchange still unavailable',()=>{
  const props={name:'真实学员',wallet:{xp:200,availableXp:200,redeemedXp:0,ownedMedalCount:0,badgeBalances:{product:20,data:5}},badges:[],error:'',onRetry(){},onBack(){},onAcademy(){},onAcademyFavorites(){},onBadgeShop(){},onBadgeCatalog(){},onBadgeOwned(){}};
  const html=renderToStaticMarkup(React.createElement(PersonalProfileView,props));
  assert.match(html,/真实学员/);assert.match(html,/200/);assert.match(html,/20 点/);assert.match(html,/5 点/);
  assert.match(html,/Lv\.1 · 成长探索者/);assert.match(html,/沐晨商城积分/);assert.match(html,/我的徽章墙/);
  assert.match(html,/已拥有徽章/);assert.doesNotMatch(html,/已拥有徽章 · 暂未开放/);
  assert.match(html,/可兑换经验<\/span><strong>200/);assert.match(html,/已用于兑换<\/span><strong>0/);
  assert.match(html,/<strong>0 <small>枚<\/small><\/strong>/);
  assert.match(html,/查看成长明细/);assert.match(html,/经验兑换暂未开放/);assert.match(html,/商城积分 · 暂未开放/);
  assert.doesNotMatch(html,/1,250|Lv\.3|洞察新星|演示成长|预览身份/);
  const failed=renderToStaticMarkup(React.createElement(PersonalProfileView,{...props,wallet:null,badges:null,error:'读取失败'}));
  assert.match(failed,/读取失败/);assert.match(failed,/重新加载/);assert.doesNotMatch(failed,/200|20 点/);
  assert.match(failed,/可兑换经验<\/span><strong>—/);assert.match(failed,/已用于兑换<\/span><strong>—/);
  assert.match(failed,/等级数据读取失败/);assert.doesNotMatch(failed,/<progress|Lv\.1/);
  const loading=renderToStaticMarkup(React.createElement(PersonalProfileView,{...props,wallet:null,badges:null,error:''}));
  assert.match(loading,/正在读取成长等级/);assert.doesNotMatch(loading,/<progress|Lv\.1/);
});

test('profile growth levels follow cumulative XP boundaries and ignore spendable balance',()=>{
  const cases=[
    [0,1,0,500,'成长探索者'],[499,1,499,1,'成长探索者'],
    [500,2,0,500,'成长探索者'],[700,2,200,300,'成长探索者'],
    [1000,3,0,500,'成长实践者'],[1250,3,250,250,'成长实践者'],
  ];
  for(const [xp,level,progress,remaining,title] of cases){
    assert.deepEqual(profileGrowthLevel(xp),{level,nextLevel:level+1,title,progress,step:500,remaining});
    const html=renderToStaticMarkup(React.createElement(PersonalProfileView,{
      name:'真实学员',wallet:{xp,availableXp:0,redeemedXp:xp,ownedMedalCount:0,badgeBalances:{}},badges:[],error:'',
      onRetry(){},onBack(){},onAcademy(){},onAcademyFavorites(){},onBadgeShop(){},onBadgeCatalog(){},onBadgeOwned(){},
    }));
    assert.equal(html.split(`Lv.${level} · ${title}`).length-1,2,'Overview and experience card must agree');
    assert.ok(html.includes(`value="${progress}" max="500"`));
    assert.ok(html.includes(`aria-valuetext="Lv.${level}，${progress} / 500 XP，距离 Lv.${level+1} 还需 ${remaining} 经验"`));
    assert.match(html,/可兑换经验<\/span><strong>0/);
    assert.match(html,/商城积分 · 暂未开放/);assert.match(html,/经验兑换暂未开放/);
    assert.doesNotMatch(html,/<progress[^>]*style=|演示成长|成长等级暂未开放/);
  }
  for(const invalid of [undefined,-1,1.5,NaN,Infinity])assert.equal(profileGrowthLevel(invalid),null);
});

test('profile badge wall uses real ownership, keeps delisted medals and orders newest first',()=>{
  const published=(id)=>({id,name:'徽章 '+id,description:'真实发布',image:'',style:'blue',revision:1,stock:null,costs:[{badgeId:'data',points:5}]});
  const owned=(id,at)=>({id:'r-'+id,medalId:id,medalName:'已获得 '+id,image:'/saved-'+id+'.webp',style:'gold',costs:[{badgeId:'data',points:5}],redeemedAt:at});
  const data={wallet:{xp:100,availableXp:100,redeemedXp:0,ownedMedalCount:2,badgeBalances:{data:8}},medals:[published('unowned'),published('owned')],redemptions:[owned('owned','2026-11-08T00:00:00Z'),owned('delisted','2026-11-09T00:00:00Z')]};
  const result=parseProfileCollection(data);
  assert.deepEqual(result.badges.map(b=>b.id),['delisted','owned']);
  assert.equal(result.badges[0].image,'/saved-delisted.webp');
  assert.equal(result.badges[0].published,false);
  assert.equal(result.badges[0].tone,'gold');
  assert.equal(result.wallet.ownedMedalCount,2);
  assert.throws(()=>parseProfileCollection({...data,redemptions:undefined}),/徽章数据不完整/);
  assert.throws(()=>parseProfileCollection({...data,wallet:{...data.wallet,ownedMedalCount:3}}),/徽章记录正在更新/);
});

test('profile badge wall distinguishes real empty, loading, error and stale data',()=>{
  const props={badges:null,error:'',onRetry(){},onShop(){},onOwned(){}};
  const render=overrides=>renderToStaticMarkup(React.createElement(ProfileBadgeWall,{...props,...overrides}));
  const loading=render({});
  assert.match(loading,/正在读取已拥有徽章/);
  assert.doesNotMatch(loading,/你还没有获得徽章|已获得 0 枚/);
  const failed=render({error:'网络错误'});
  assert.match(failed,/徽章读取失败|重新加载/);
  assert.doesNotMatch(failed,/你还没有获得徽章|已获得 0 枚/);
  const empty=render({badges:[]});
  assert.match(empty,/你还没有获得徽章/);
  assert.match(empty,/完成任务积累徽章点，前往徽章商城兑换你的第一枚徽章。/);
  assert.match(empty,/已获得 0 枚徽章/);
  assert.doesNotMatch(empty,/暂未开放|查看全部/);
  const stale=render({badges:[],error:'网络错误'});
  assert.match(stale,/当前显示上次读取的徽章/);
});

test('profile badge wall previews six owned artworks and offers all owned navigation',()=>{
  const artwork=JSON.parse(readFileSync(path.join(root,'app/project29/badgeCatalogData.json'),'utf8'))[0];
  const badges=Array.from({length:7},(_,i)=>({id:'owned-'+i,name:'已获得 '+i,description:'',category:'数据交付',level:'成长徽章',tone:['cyan','violet','gold'][i%3],artworkId:artwork.id,image:'',icon:'a03b5',requirements:[],revision:1,stock:null,published:true}));
  const props={badges,error:'',onRetry(){},onShop(){},onOwned(){}};
  const html=renderToStaticMarkup(React.createElement(ProfileBadgeWall,props));
  assert.match(html,/已获得 7 枚徽章/);
  assert.equal((html.match(/class="profile-badge-item"/g)||[]).length,6);
  for(const level of [1,2,3])assert.ok(html.includes('/assets/journey-badges/frames/level-'+level+'.svg'));
  assert.ok(html.includes('/assets/journey-badges/centered-icons/'+artwork.path+'.webp'));
  assert.match(html,/一级/);assert.match(html,/二级/);assert.match(html,/三级/);
  assert.doesNotMatch(html,/<h3>已获得 6<\/h3>|暂未开放/);
  assert.match(html,/展示最近获得的 6 枚徽章/);assert.match(html,/查看全部/);
  const one=renderToStaticMarkup(React.createElement(ProfileBadgeWall,{...props,badges:badges.slice(0,1)}));
  assert.doesNotMatch(one,/查看全部/);
});

test('growth details show task origins and signed badge costs without presenting mall exchange as enabled',()=>{
  const page={items:[
    {id:'reward-1',kind:'task_reward',occurredAt:'2026-11-09T08:41:11Z',module:'新手村',title:'学习任务 <script>',taskId:'task-1',xp:100,badgePoints:[{id:'product',points:10}],method:'任务审核通过'},
    {id:'medal-1',kind:'medal_redemption',occurredAt:'2026-11-08T08:41:11Z',module:'新手村',title:'洞察者',xp:0,badgePoints:[{id:'product',points:-5}],medal:{id:'medal-1',name:'洞察者'},method:'徽章点兑换'},
  ],total:3,hasMore:true,nextOffset:2};
  const html=renderToStaticMarkup(React.createElement(GrowthHistoryContent,{page,loading:false,error:'',onRetry(){},onMore(){}}));
  assert.match(html,/学习任务 &lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  assert.match(html,/新手村/);assert.match(html,/任务审核通过/);assert.match(html,/\+100 XP/);assert.match(html,/\+10 点/);
  assert.match(html,/产品开发徽章点/);assert.match(html,/−5 点/);assert.match(html,/已获得「洞察者」/);assert.match(html,/徽章点兑换/);
  assert.match(html,/dateTime="2026-11-09T08:41:11Z"|datetime="2026-11-09T08:41:11Z"/);
  assert.match(html,/16:41/);assert.match(html,/加载更多/);assert.doesNotMatch(html,/\+0 XP|确认兑换|经验兑换商城积分/);
});

test('growth details distinguish empty, failed and still loading states',()=>{
  const props={page:null,loading:true,error:'',onRetry(){},onMore(){}};
  const loading=renderToStaticMarkup(React.createElement(GrowthHistoryContent,props));
  assert.match(loading,/正在读取成长明细/);assert.doesNotMatch(loading,/还没有成长记录/);
  const failed=renderToStaticMarkup(React.createElement(GrowthHistoryContent,{...props,loading:false,error:'登录已失效'}));
  assert.match(failed,/登录已失效/);assert.match(failed,/重新读取/);assert.doesNotMatch(failed,/还没有成长记录|共 0 条/);
  const empty=renderToStaticMarkup(React.createElement(GrowthHistoryContent,{...props,loading:false,page:{items:[],total:0,hasMore:false,nextOffset:null}}));
  assert.match(empty,/还没有成长记录/);assert.doesNotMatch(empty,/读取失败|加载更多/);
});

test('identity selection exposes independent staff login and a learner logout form',()=>{
  const html=renderToStaticMarkup(React.createElement(AccountSwitchDialog,{open:true,onClose(){}}));
  assert.match(html,/以哪种身份继续探索/);assert.match(html,/切换账号/);
  assert.match(html,/href="\/review" target="_blank" rel="noopener noreferrer"/);
  assert.match(html,/<form/);assert.match(html,/type="submit"/);
  assert.doesNotMatch(html,/登录地址尚未配置|111|333/);
});

test('project30 task cards use canonical badge allocations, not task points or fractional weights',()=>{
  const task={id:'card',title:'真实发布任务',category:'产品开发',description:'真实简介',level:'挑战',
    minutes:90,experience:150,points:0,review:'人工审核',mentor:'发布人',publishedAt:'2026-10-29T08:00:00Z',
    badges:[['产品开发',50],['财法合规',50]],rewardAllocations:[{id:'product',points:8},{id:'finance-compliance',points:7}]};
  for(const [status,label] of [['available','可接取'],['active','正在进行中'],['returned','需修改'],['pending','待审核'],['completed','已完成']]){
    const html=renderToStaticMarkup(React.createElement(VillageTaskCard,{task:{...task,status},onOpen(){}}));
    assert.match(html,/真实发布任务/);assert.match(html,/150<!-- --> XP|150 XP/);
    assert.ok(html.includes(label),label);
    assert.match(html,/产品开发徽章点/);assert.match(html,/财法合规徽章点/);
    assert.match(html,/\+8 点/);assert.match(html,/\+7 点/);
    assert.doesNotMatch(html,/7\.5|任务点|示例发布|50%/);
  }
});

test('village detail rewards preserve published values and handle unconfigured badges',()=>{
  const html=renderToStaticMarkup(React.createElement(VillageTaskRewards,{task:{experience:200,points:999,rewardAllocations:[{id:'product',points:20}]}}));
  assert.match(html,/审核通过后的奖励/);assert.match(html,/200 XP/);
  assert.match(html,/产品开发徽章点/);assert.match(html,/\+20 点/);
  assert.doesNotMatch(html,/999|3\.5|1\.5/);
  const empty=renderToStaticMarkup(React.createElement(VillageTaskRewards,{task:{experience:0,rewardAllocations:[]}}));
  assert.match(empty,/暂未配置徽章点/);assert.match(empty,/0 XP/);
});

test('project30 favorites empty state never imports demo collections',()=>{
  const html=renderToStaticMarkup(React.createElement(FavoriteKnowledge,{courses:[],favoriteIds:['prompt','design'],query:'',onToggle(){},onOpen(){},onBrowse(){}}));
  assert.match(html,/暂未开放/);assert.match(html,/共 0 条收藏/);assert.match(html,/data-page-navigation/);
  assert.doesNotMatch(html,/module-tag">L2|示例学习|\+50 XP/);
});

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
    if(['village','academy'].includes(initialScreen))assert.doesNotMatch(html,/许知微 · 通过了|<strong>20<\/strong>|module-tag">L2|<small>L2<|10<small>%|示例内容 · 本次会话体验/);
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

test('Feishu client first render retains the original selected Feishu entry without phone controls',()=>{
  const html=renderToStaticMarkup(React.createElement(JourneyProvider,{
    value:{...value,initialScreen:'login',experience:null,feishuClient:true},
  },React.createElement(Login)));
  const tabs=html.match(/<div[^>]*role="tablist"[^>]*>([\s\S]*?)<\/div>/)?.[1];
  assert.ok(tabs,'The existing login-method row remains present');
  assert.equal((tabs.match(/role="tab"/g)||[]).length,1);
  assert.match(html,/class="login-method-tabs feishu-only"/);
  assert.match(tabs,/aria-selected="true"/);
  assert.match(tabs,/class="active"/);
  assert.match(tabs,/src="\/assets\/project29\/06dc8\.svg"/);
  assert.match(tabs,/飞书登录/);
  assert.doesNotMatch(tabs,/7c344\.svg|3088c\.svg|973c8\.svg/);
  assert.match(html,/class="panel-logo" src="\/assets\/project29\/6f233\.webp"/);
  assert.match(html,/class="panel-title">MUCHEN JOURNEY/);
  assert.match(html,/placeholder="探索营毕业码（选填）"/);
  assert.match(html,/<button[^>]*class="launch-button"[^>]*type="submit"[^>]*>[\s\S]*?79892\.svg[\s\S]*?登录并开始探索[\s\S]*?<\/button>/);
  assert.doesNotMatch(html,/手机号登录|请输入手机号|aria-label="手机号"|password-login-fields|autocomplete="current-password"|type="password"|注册账号|忘记密码|重置密码/);
});

test('phone nickname setup renders the supplied welcome dialog over the exploration dashboard',()=>{
  const html=render({initialScreen:'dashboard',joinPhase:'nickname'});
  assert.match(html,/welcome-name-dialog/);
  assert.match(html,/欢迎加入探索营/);
  assert.match(html,/请输入您的真实姓名/);
  assert.match(html,/确认姓名，进入探索营/);
  assert.match(html,/updated-dashboard/);
  assert.doesNotMatch(html,/当前为前端演示|仅保存在本机浏览器|code-field|autocomplete="current-password"/i);
});



test('released village uses real departments and does not render demo tasks',()=>{
  const {practiceTasks}=load(path.join(root,'app/project29/moduleDemoData.ts'));
  const {taskDepartments}=load(path.join(root,'app/project29/taskDepartments.ts'));
  const html=render({initialScreen:'village'});
  for(const department of taskDepartments) assert.ok(html.includes(department.name),department.name);
  for(const task of practiceTasks) assert.ok(!html.includes(task.title));
  assert.match(html,/正在读取任务/);
  assert.doesNotMatch(html,/示例内容 · 本次会话体验/);
  assert.match(render({initialScreen:'guild'}),/正在读取你的公会认证和徽章凭证/);
  const academy = render({initialScreen:'academy'});
  assert.match(academy,/正在读取学院内容/);
  assert.match(academy,/我的学习进度|学习记录/);
  assert.doesNotMatch(academy,/课程详情暂未开放|首次完成获得探索勋章|认识生成式 AI：从概念到工作场景/);
});
