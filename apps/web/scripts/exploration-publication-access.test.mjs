import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {ApiStore, createJourneyService} from '../public/review-native/native-api.js';
import {canConfigureTask, EXPLORATION_CONFIGURATION_NOTICE} from '../public/review-native/task-publication-access.js';
import {renderLibrary, openTask} from '../public/review-native/library.js';
import {createTaskWorkflow} from '../public/review-native/task-workflow.js';
import {createPublicationReviewController} from '../public/review-native/publication-review.js';
import {taskIssue} from '../public/review-native/task-field-limits.js';
import {confirmPublicationFields} from '../public/review-native/publish-materials.js';

const exploration = {id:'exploration',camp:'exploration',title:'培训任务',summary:'学习培训材料',completionMode:'learning',order:1,materials:[],badges:[],rubric:[],status:'published'};
const novice = {...exploration,id:'novice',camp:'novice',title:'新手村任务'};
const source = await readFile(new URL('../public/review-native/app.js',import.meta.url),'utf8');

test('ordinary administrators cannot persist, change camp, archive, delete or publish exploration tasks', async()=>{
  const store=new ApiStore(); store.capabilities={isSuperAdmin:false}; store.operatorId='operator';
  store.data={tasks:[exploration],draft:structuredClone(exploration)};
  const previous=globalThis.fetch;let writes=0;
  globalThis.fetch=async()=>{writes++;throw Error('unexpected network request');};
  try {
    assert.throws(()=>store.save(),/仅限超级管理员/);
    for(const task of [exploration,{...exploration,camp:'novice'}]) {
      await assert.rejects(store.saveTask(task),/仅限超级管理员/);
      await assert.rejects(store.archiveTask(task),/仅限超级管理员/);
      await assert.rejects(store.deleteTask(task),/仅限超级管理员/);
      const service=createJourneyService({store});
      await assert.rejects(service.tasks.publish(task,'reviewer',[],'key'),/仅限超级管理员/);
      await assert.rejects(service.tasks.submitPublication(task,[]),/仅限超级管理员/);
    }
    assert.equal(writes,0);
  } finally {globalThis.fetch=previous;}
});

test('super administrators publish exploration without reviewer membership; novice retains reviewer validation',async()=>{
  const store=new ApiStore(); store.capabilities={isSuperAdmin:true}; store.members=[];
  store.data={tasks:[]};store.save=()=>{};store.refresh=async()=>{};
  const requests=[],previous=globalThis.fetch;
  globalThis.fetch=async(_url,options)=>{
    const command=JSON.parse(options.body);requests.push(command);
    return {ok:true,status:200,json:async()=>({ok:true,data:command.task})};
  };
  try {
    const service=createJourneyService({store});
    await service.tasks.publish(exploration,undefined,[],'key');
    assert.equal(requests[0].command,'publishTask');
    assert.equal('reviewerId' in requests[0].payload,false);
    await assert.rejects(service.tasks.publish(novice,undefined,[],'key'),/请选择内容复核人/);
    await assert.rejects(service.tasks.submitPublication(exploration,[]),/无需提交发布审核/);
    assert.equal(requests.length,1);
  } finally {globalThis.fetch=previous;}
});

test('ordinary administrators keep novice publication submission',async()=>{
  const writes=[],previous=globalThis.fetch;
  const store={capabilities:{isSuperAdmin:false},data:{},save(){},refresh:async()=>{}};
  globalThis.fetch=async(_url,options)=>{const body=JSON.parse(options.body);writes.push(body);return {ok:true,status:200,json:async()=>({ok:true,data:novice})};};
  try {
    await createJourneyService({store}).tasks.submitPublication(novice,[]);
    assert.equal(writes[0].command,'submitPublication');
  } finally {globalThis.fetch=previous;}
});

test('task library preserves reading and review navigation while hiding exploration mutations from ordinary staff',()=>{
  const store={data:{tasks:[exploration,novice],submissions:[{taskId:'exploration'}],learners:[]},getTask:id=>[exploration,novice].find(t=>t.id===id)};
  const ordinary={isSuperAdmin:false};
  const html=renderLibrary(store,ordinary);
  assert.match(html,/data-task-view="exploration"/);
  for(const operation of ['edit','copy','archive','delete']) assert.doesNotMatch(html,new RegExp(`data-task-${operation}="exploration"`));
  assert.match(html,/data-task-edit="novice"/);
  const superHtml=renderLibrary(store,{isSuperAdmin:true});
  assert.match(superHtml,/data-task-edit="exploration"/);
  assert.match(superHtml,/data-task-delete="exploration"/);
  let detail;
  openTask(exploration,store,{...ordinary,openModal(value){detail=value;}});
  assert.doesNotMatch(detail,/data-detail-edit/);
  assert.match(detail,/data-task-review/);
});

test('copying exploration is blocked while stale exploration drafts can be left for a novice form',async()=>{
  const events=[];
  const store={capabilities:{isSuperAdmin:false},data:{tasks:[],draft:structuredClone(exploration)},getTask:()=>exploration,save(){}};
  const workflow=createTaskWorkflow({store,newDraft:()=>({...novice,id:'new',status:'draft'}),openModal(){throw Error('must not offer to save forbidden draft');},closeModal(){},showEditor(){events.push('editor');},toast(message){events.push(message);}});
  await workflow.start(exploration);
  assert.deepEqual(events,[EXPLORATION_CONFIGURATION_NOTICE]);
  await workflow.start();
  assert.equal(store.data.draft.camp,'novice');
  assert.equal(store.data.draft.id,'new');
  assert.ok(events.includes('editor'));
});

test('exploration URL cannot create an ordinary draft, while super administrator URL still opens exploration',async()=>{
  const previous={fetch:globalThis.fetch,location:globalThis.location,localStorage:globalThis.localStorage};
  globalThis.location={search:'?camp=exploration'};
  globalThis.localStorage={getItem:()=>null};
  try {
    for(const isSuperAdmin of [false,true]) {
      globalThis.fetch=async()=>({ok:true,status:200,json:async()=>({ok:true,data:{actor:{id:'actor',name:'测试管理员'},operatorId:'actor',members:[],tasks:[],reviews:[],capabilities:{isSuperAdmin}}})});
      const store=await ApiStore.create();
      assert.equal(store.data.draft.camp,isSuperAdmin?'exploration':'novice');
    }
  } finally {Object.assign(globalThis,previous);}
});

test('legacy pending exploration publication permits return but has no approval or ordinary edit action',()=>{
  const request={id:'old',taskId:exploration.id,status:'pending',submittedBy:{id:'ordinary'},task:exploration};
  const store={data:{publicationRequests:[request]},getTask:()=>exploration};
  let html;
  const ui={isSuperAdmin:true,currentUser:{id:'super'},icon:()=>'',openModal(value){html=value;}};
  const controller=createPublicationReviewController({store,service:{},ui});
  const page={contains:()=>true,querySelector:()=>({})};
  controller.bind({querySelector:()=>page});
  page.onclick({target:{closest:()=>({dataset:{pubOpen:'old'}})}});
  assert.doesNotMatch(html,/data-pub-decision="approved"|审核通过并发布/);
  assert.match(html,/data-pub-decision="rejected"/);
  assert.match(html,/退回此历史申请/);
  assert.match(html,/确认退回/);
});

test('restored ordinary exploration editor contains no editable controls',()=>{
  const fn=source.slice(source.indexOf('function renderEditor()'),source.indexOf('function cardHeader('));
  const context=vm.createContext({canConfigureTask,EXPLORATION_CONFIGURATION_NOTICE,store:{data:{draft:exploration}},ui:{isSuperAdmin:false}});
  vm.runInContext(fn,context);
  const html=vm.runInContext('renderEditor()',context);
  assert.match(html,/仅限超级管理员/);
  assert.match(html,/新建新手村任务/);
  assert.doesNotMatch(html,/<input|<textarea|<select|id="save-draft"|id="publish-task"/);
});

function publishHarness(task,isSuperAdmin=true) {
  const state={forms:[],publishCalls:[],submitted:0,saves:0};
  const controls={'#publish-task':{disabled:false},'#confirm-publish':{disabled:true},'#cancel-publish':{},'#publish-error':{hidden:true}};
  const modal={dataset:{},querySelector:()=>null,querySelectorAll:()=>[]};
  const context=vm.createContext({canConfigureTask,EXPLORATION_CONFIGURATION_NOTICE,store:{data:{draft:task},members:[],async saveTask(value){state.saves++;return value;}},ui:{isSuperAdmin},materialUploadsPending:false,
    draftPublication:()=>null,validateTask:()=>[],taskIssue,bindFieldFeedback(){},confirmPublicationFields,normalizeBadgeWeights:value=>value,isTaskUpdate:()=>false,taskResourceLinks:()=>[],crypto:globalThis.crypto,e:value=>value,icon:()=>'',renderPublishMaterials:()=>'',
    $:key=>controls[key],openModal(html,ready){state.forms.push(html);if(html.includes('native-publish-confirm'))ready(modal);},closeModal(){},openSubmitPublication(){state.submitted++;},toast(){},render(){},
    service:{tasks:{async publish(...args){state.publishCalls.push(args);return task;}}},sandbox:{retainForPublishedTask(){}},taskWorkflow:{async resetAfterPublish(){}}});
  vm.runInContext(source.slice(source.indexOf('async function publish()'),source.indexOf('onInviteSessionChange(render)')),context);
  return {state,controls,run:()=>vm.runInContext('publish()',context)};
}

test('actual exploration publish dialog is ready without a reviewer and publishes directly',async()=>{
  const h=publishHarness(exploration);
  await h.run();
  assert.match(h.state.forms[0],/直接发布/);
  assert.doesNotMatch(h.state.forms[0],/内容复核人|publish-reviewer/);
  assert.equal(h.controls['#confirm-publish'].disabled,false);
  await h.controls['#confirm-publish'].onclick();
  assert.equal(h.state.publishCalls.length,1);
  assert.equal(h.state.publishCalls[0][1],undefined);
  assert.equal(h.state.submitted,0);
});

test('actual ordinary exploration publish is rejected before saving; novice still submits for approval',async()=>{
  const denied=publishHarness(exploration,false);await denied.run();
  assert.equal(denied.state.saves,0);assert.equal(denied.state.forms.length,0);
  const allowed=publishHarness(novice,false);await allowed.run();
  assert.equal(allowed.state.saves,1);assert.equal(allowed.state.submitted,1);
});
