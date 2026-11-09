import assert from 'node:assert/strict';
import test from 'node:test';
import { createGuildRequestApi } from '../public/review-native/guild-store.js';
import { createGuildController } from '../public/review-native/guild.js';

const request = (extra={}) => ({id:'request-1',studentId:'learner-1',studentName:'学员甲',level:1,status:'pending',evidence:[{id:'medal-1',name:'蓝色徽章',grade:1}],submittedAt:'2026-11-09T01:00:00Z',reviewedAt:null,reviewerName:'',reason:'',...extra});
const response=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
function harness(handler){
 const user={id:'admin-1',accessRole:'super_admin'},calls=[];
 const api=createGuildRequestApi({getCurrentUser:()=>user,fetcher:async(url,options)=>{const call={url,...options,body:options.body?JSON.parse(options.body):undefined};calls.push(call);return handler(call);}});
 return {api,user,calls};
}

test('guild review list loads actual server requests and clones cached evidence',async()=>{
 const h=harness(()=>response({requests:[request()]}));
 assert.equal(h.api.loaded,false);assert.deepEqual(h.api.snapshot(),{requests:[]});
 await h.api.refresh();
 assert.equal(h.calls[0].url,'/api/review-native/guild-requests');
 assert.equal(h.calls[0].credentials,'same-origin');assert.equal(h.calls[0].cache,'no-store');
 const copy=h.api.snapshot();copy.requests[0].evidence[0].name='changed';
 assert.equal(h.api.snapshot().requests[0].evidence[0].name,'蓝色徽章');
});

test('approval uses server acknowledgment and a pending refresh cannot overwrite it',async()=>{
 let finish;
 const h=harness(call=>call.method==='GET'?response({requests:[request()]}):new Promise(resolve=>{finish=()=>resolve(response({requests:[request({status:'approved',reviewerName:'管理员'})]}));}));
 await h.api.refresh();
 const operation=h.api.review('request-1','approved',' 符合条件 ');
 assert.equal(h.api.snapshot().requests[0].status,'pending');
 await assert.rejects(h.api.review('request-1','approved',''),/正在提交/);
 await h.api.refresh();assert.equal(h.calls.length,2);
 finish();await operation;
 assert.equal(h.api.snapshot().requests[0].status,'approved');
 assert.deepEqual(h.calls[1].body,{id:'request-1',decision:'approved',reason:'符合条件'});
 await assert.rejects(h.api.review('request-1','returned','改变结论'),/已处理/);
});

test('returning requires a visible reason and preserves server review history',async()=>{
 const h=harness(call=>response({requests:[request(call.method==='POST'?{status:'returned',reason:call.body.reason,reviewedAt:'2026-11-09T02:00:00Z'}:{})]}));
 await h.api.refresh();
 await assert.rejects(h.api.review('request-1','returned',' '),/退回原因/);
 assert.equal(h.calls.length,1);
 await h.api.review('request-1','returned','请补充凭证');
 assert.equal(h.api.snapshot().requests[0].reason,'请补充凭证');
 assert.equal(h.api.snapshot().requests[0].status,'returned');
});

test('self-review, changed identity, and learner role cannot send review commands',async()=>{
 const h=harness(()=>response({requests:[request({studentId:'admin-1'})]}));
 await h.api.refresh();await assert.rejects(h.api.review('request-1','approved'),/自己的/);
 h.user.id='admin-2';await assert.rejects(h.api.review('request-1','approved'),/身份或审核列表/);
 assert.deepEqual(h.api.snapshot().requests,[]);
 h.user.accessRole='learner';await assert.rejects(h.api.refresh(),/仅管理员/);
 assert.equal(h.calls.length,1);
});

test('server conflict updates stale state without pretending a review succeeded',async()=>{
 let changed=false;
 const h=harness(call=>{if(call.method==='POST'){changed=true;return response({error:'该申请已被其他管理员处理'},409);}return response({requests:[request(changed?{status:'returned',reason:'材料不足'}:{})]});});
 await h.api.refresh();await assert.rejects(h.api.review('request-1','approved'),/其他管理员/);
 assert.equal(h.api.snapshot().requests[0].status,'returned');
 assert.equal(h.api.snapshot().requests[0].reason,'材料不足');
});

test('network errors remain retryable and identity changes during request discard response',async()=>{
 let fail=true;
 const h=harness(()=>{if(fail)return response({error:'服务暂时不可用'},503);return response({requests:[request()]});});
 await assert.rejects(h.api.refresh(),/服务暂时不可用/);assert.equal(h.api.loaded,false);assert.equal(h.api.error,'服务暂时不可用');
 fail=false;await h.api.refresh();assert.equal(h.api.error,'');
 let resolve;
 const pending=harness(()=>new Promise(done=>{resolve=done;}));
 const loading=pending.api.refresh();pending.user.id='another-admin';resolve(response({requests:[request()]}));
 await assert.rejects(loading,/身份已改变/);assert.deepEqual(pending.api.snapshot().requests,[]);
});

function controllerHarness(items,extra={}){
 const store={isAdmin:()=>true,currentUserId:()=> 'admin-1',snapshot:()=>({certifications:[],labs:[],rules:[],contributions:[],stats:{certifiedLearners:0,publishedLabs:0,totalPoints:0}}),requestSnapshot:()=>({requests:items}),requestsLoaded:true,requestsLoading:false,requestsError:'',...extra};
 const controller=createGuildController({guild:store,ui:{icon:()=>'',refresh(){},toast(){}}});
 return controller;
}

test('admin guild retains existing tabs and shows pending applications with escaped evidence',()=>{
 const controller=controllerHarness([request({studentName:'<img src=x onerror=alert(1)>',evidence:[{id:'id',name:'<script>徽章</script>',grade:1}]})]);
 const html=controller.render();
 for(const label of ['晋级审核','能力认证','模拟实验室','工会贡献','待审核','已通过','已退回','查看并审核','刷新申请'])assert.ok(html.includes(label));
 assert.ok(html.includes('&lt;script&gt;徽章&lt;/script&gt;'));assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<script>'));
 assert.ok(html.includes('审核通过只更新该工会的阶段'));
 assert.ok(html.includes('旧版全局认证'));
});

test('request errors expose retry and self application offers detail without audit action',()=>{
 assert.ok(controllerHarness([],{requestsError:'读取失败'}).render().includes('重新加载'));
 const html=controllerHarness([request({studentId:'admin-1'})]).render();
 assert.ok(html.includes('需由其他管理员审核'));assert.ok(html.includes('查看详情'));assert.ok(!html.includes('查看并审核'));
});

test('review detail requires a separate decision form and explains learner-visible return reason',()=>{
 const buttons=new Map();let click,modalHtml='',writes=0;
 const form={};
 const node={classList:{add(){}},querySelectorAll:()=>[],querySelector:selector=>selector==='form'?form:selector.startsWith('[data-gd-')?{addEventListener:(_type,handler)=>buttons.set(selector,handler)}:null};
 const store={isAdmin:()=>true,currentUserId:()=> 'admin-1',snapshot:()=>({certifications:[],labs:[],rules:[],contributions:[],stats:{}}),requestSnapshot:()=>({requests:[request()]}),requestsLoaded:true,requestsLoading:false,refreshRequests:async()=>{},reviewRequest:()=>{writes++;}};
 const controller=createGuildController({guild:store,ui:{icon:()=>'',refresh(){},toast(){},openModal:(html,ready)=>{modalHtml=html;ready(node);},closeModal(){}}});
 const root={querySelector:()=>null,contains:()=>true,addEventListener:(_type,handler)=>{click=handler;}};
 controller.bind(root);
 try{
  const button={dataset:{gdRequestDetail:'request-1'},disabled:false,hasAttribute:()=>false};
  click({target:{closest:()=>button}});
  assert.ok(modalHtml.includes('公会晋级申请详情'));assert.ok(modalHtml.includes('medal-1'));assert.equal(writes,0);
  buttons.get('[data-gd-return-request]')();
  assert.ok(modalHtml.includes('退回公会晋级申请'));assert.ok(modalHtml.includes('name="reason" required'));assert.ok(modalHtml.includes('学员可见'));assert.equal(writes,0);assert.equal(typeof form.onsubmit,'function');
 }finally{controller.deactivate();}
});


const taskSnapshot=(extra={})=>({id:'guild-l1-brief',version:1,source:'project39-template',title:'需求澄清与验收边界',level:1,brief:'先确认客户需求，再承诺交期。',deliverable:'需求确认单与待澄清问题。',checks:['明确有效条数与范围边界','列出待澄清问题及责任人','写明质量、格式与验收方法'],artifact:'第一行成果\n第二行完整内容',submittedAt:'2026-11-09T00:30:00Z',revision:1,...extra});
const scopedRequest=(extra={})=>request({guildId:'multilingual',guildTitle:'多语种数据交付线',task:taskSnapshot(),...extra});

test('new guild request preserves immutable guild and complete task evidence in cache',async()=>{
 const h=harness(()=>response({requests:[scopedRequest()]}));
 await h.api.refresh();
 const copy=h.api.snapshot();copy.requests[0].guildTitle='changed';copy.requests[0].task.checks.push('altered');copy.requests[0].task.artifact='changed';
 const stored=h.api.snapshot().requests[0];
 assert.equal(stored.guildTitle,'多语种数据交付线');assert.equal(stored.task.checks.length,3);assert.equal(stored.task.artifact,'第一行成果\n第二行完整内容');
 await h.api.review('request-1','approved','任务成果满足要求');
 assert.deepEqual(h.calls[1].body,{id:'request-1',decision:'approved',reason:'任务成果满足要求'});
});

test('request list shows scoped guild, named stage and task while keeping legacy records separate',()=>{
 const html=controllerHarness([scopedRequest({guildTitle:'<工会 & 测试>'}),request({id:'legacy-1',studentName:'旧学员'})]).render();
 for(const text of ['所属工会','申请阶段 / 任务','规范实践','需求澄清与验收边界','旧版全局认证','独立保留，不计入具体工会阶段'])assert.ok(html.includes(text),text);
 assert.ok(html.includes('&lt;工会 &amp; 测试&gt;'));assert.ok(!html.includes('<工会 & 测试>'));
});

test('request search matches guild, certification stage and task title independently',()=>{
 const controller=controllerHarness([scopedRequest({studentName:'语言学员'}),scopedRequest({id:'request-2',studentName:'模型学员',guildId:'model-evaluation',guildTitle:'通用模型测评交付线',level:2,task:taskSnapshot({title:'质检返修与进度调整'})})]);
 let search;const results={innerHTML:''};
 const root={querySelector:selector=>selector==='[data-gd-search]'?{addEventListener:(_type,handler)=>{search=handler;}}:selector==='[data-gd-results]'?results:null,addEventListener(){}};
 controller.bind(root);
 try{
  for(const query of ['通用模型测评','model-evaluation','协同攻坚','质检返修']){
   search({target:{value:query}});assert.ok(results.innerHTML.includes('模型学员'),query);assert.ok(!results.innerHTML.includes('语言学员'),query);
  }
  search({target:{value:'旧版全局认证'}});assert.ok(results.innerHTML.includes('暂无符合条件'));
 }finally{controller.deactivate();}
});

function detailHarness(item){
 const buttons=new Map();let click,modalHtml='';const classes=[];const form={};
 const node={classList:{add:name=>classes.push(name)},querySelectorAll:()=>[],querySelector:selector=>selector==='form'?form:selector.startsWith('[data-gd-')?{addEventListener:(_type,handler)=>buttons.set(selector,handler)}:null};
 const store={isAdmin:()=>true,currentUserId:()=> 'admin-1',snapshot:()=>({certifications:[],labs:[],rules:[],contributions:[],stats:{}}),requestSnapshot:()=>({requests:[item]}),requestsLoaded:true,requestsLoading:false,refreshRequests:async()=>{}};
 const controller=createGuildController({guild:store,ui:{icon:()=>'',refresh(){},toast(){},openModal:(html,ready)=>{modalHtml=html;ready(node);},closeModal(){}}});
 controller.bind({querySelector:()=>null,contains:()=>true,addEventListener:(_type,handler)=>{click=handler;}});
 click({target:{closest:()=>({dataset:{gdRequestDetail:item.id},disabled:false,hasAttribute:()=>false})}});
 return {controller,buttons,classes,html:()=>modalHtml};
}

test('review detail includes untruncated escaped task artifact, self-checks and distinct timestamps',()=>{
 const artifact='第一行 <script>alert(1)</script>\n'+'完整成果'.repeat(1400)+'\n最后一行成果';
 const h=detailHarness(scopedRequest({task:taskSnapshot({artifact,brief:'<任务场景>',deliverable:'核对 & 验收'})}));
 try{
  const html=h.html();
  for(const text of ['多语种数据交付线','规范实践','任务描述','交付要求','学员提交的完整成果','自查记录','成果提交时间','最后一行成果'])assert.ok(html.includes(text),text);
  for(const value of [taskSnapshot().submittedAt,request().submittedAt])assert.ok(html.includes(new Date(value).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})));
  assert.ok(html.includes('&lt;任务场景&gt;'));assert.ok(html.includes('核对 &amp; 验收'));assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('完整成果'.repeat(1400)));assert.ok(h.classes.includes('gd-request-modal'));
  for(const check of taskSnapshot().checks)assert.ok(html.includes(check));
  h.buttons.get('[data-gd-approve-request]')();
  assert.ok(h.html().includes('其他工会的进度不变'));assert.ok(h.html().includes('多语种数据交付线'));
 }finally{h.controller.deactivate();}
});

test('legacy request detail and decision explain no concrete guild credit is granted',()=>{
 const h=detailHarness(request());
 try{
  assert.ok(h.html().includes('旧版全局认证'));assert.ok(h.html().includes('提交时未要求认证任务成果'));
  h.buttons.get('[data-gd-approve-request]')();assert.ok(h.html().includes('不计入具体工会阶段'));
 }finally{h.controller.deactivate();}
});
