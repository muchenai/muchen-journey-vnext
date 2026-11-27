import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {ApiStore, createJourneyService} from '../public/review-native/native-api.js';
import {renderLibrary, openTask} from '../public/review-native/library.js';
import {createTaskWorkflow} from '../public/review-native/task-workflow.js';
import {createPublicationReviewController} from '../public/review-native/publication-review.js';
import {canEditTask} from '../public/review-native/task-publication-access.js';
import {normalizeBadgeWeights} from '../public/review-native/core.js';
import {taskIssue} from '../public/review-native/task-field-limits.js';
import {confirmPublicationFields} from '../public/review-native/publish-materials.js';

const exploration = {id:'exploration',authorId:'ordinary',camp:'exploration',title:'培训任务',summary:'学习培训材料',completionMode:'learning',order:1,materials:[],badges:[],rubric:[],status:'published'};
const novice = {...exploration,id:'novice',camp:'novice',title:'新手村任务'};
const source = await readFile(new URL('../public/review-native/app.js',import.meta.url),'utf8');

test('ordinary administrators cannot directly publish, archive or delete exploration tasks', async()=>{
  const store=new ApiStore(); store.capabilities={isSuperAdmin:false}; store.operatorId='operator';
  store.data={tasks:[exploration],draft:structuredClone(exploration)};
  const previous=globalThis.fetch; let writes=0;
  globalThis.fetch=async()=>{writes++;throw Error('unexpected network request');};
  try {
    for(const task of [exploration,{...exploration,camp:'novice'}]) {
      await assert.rejects(store.archiveTask(task),/仅限超级管理员/);
      await assert.rejects(store.deleteTask(task),/仅限超级管理员/);
      await assert.rejects(createJourneyService({store}).tasks.publish(task,[],'key'),/仅限超级管理员/);
    }
    assert.equal(writes,0);
  } finally {globalThis.fetch=previous;}
});

test('super administrators directly publish both camps without reviewer selection',async()=>{
  const store=new ApiStore(); store.capabilities={isSuperAdmin:true}; store.members=[];
  store.data={tasks:[]};store.save=()=>{};store.refresh=async()=>{};
  const requests=[],previous=globalThis.fetch;
  globalThis.fetch=async(_url,options)=>{
    const command=JSON.parse(options.body);requests.push(command);
    return {ok:true,status:200,json:async()=>({ok:true,data:command.task})};
  };
  try {
    const service=createJourneyService({store});
    await service.tasks.publish(exploration,[],'key');
    assert.equal(requests[0].command,'publishTask');
    assert.equal('reviewerId' in requests[0].payload,false);
    await service.tasks.publish(novice,[],'key');
    assert.equal('reviewerId' in requests[1].payload,false);
    await assert.rejects(service.tasks.submitPublication(exploration,[]),/无需提交发布审核/);
    assert.equal(requests.length,2);
  } finally {globalThis.fetch=previous;}
});

test('ordinary administrators submit both camps for approval',async()=>{
  const writes=[],previous=globalThis.fetch;
  const store={capabilities:{isSuperAdmin:false},data:{},save(){},refresh:async()=>{}};
  globalThis.fetch=async(_url,options)=>{const body=JSON.parse(options.body);writes.push(body);return {ok:true,status:200,json:async()=>({ok:true,data:novice})};};
  try {
    for (const task of [novice, exploration]) await createJourneyService({store}).tasks.submitPublication(task,[]);
    assert.deepEqual(writes.map(w=>[w.command,w.id]),[['submitPublication','novice'],['submitPublication','exploration']]);
  } finally {globalThis.fetch=previous;}
});

test('task library preserves reading and review navigation and permits editing own exploration tasks without granting delete or archive',()=>{
  const store={operatorId:'ordinary',capabilities:{isSuperAdmin:false},data:{tasks:[exploration,novice],submissions:[{taskId:'exploration'}],learners:[]},getTask:id=>[exploration,novice].find(t=>t.id===id)};
  const ordinary={isSuperAdmin:false};
  const html=renderLibrary(store,ordinary);
  assert.match(html,/data-task-view="exploration"/);
  for(const operation of ['edit','copy']) assert.match(html,new RegExp(`data-task-${operation}="exploration"`));
  for(const operation of ['archive','delete']) assert.doesNotMatch(html,new RegExp(`data-task-${operation}="exploration"`));
  assert.match(html,/data-task-edit="novice"/);
  store.capabilities.isSuperAdmin=true;
  const superHtml=renderLibrary(store,{isSuperAdmin:true});
  assert.match(superHtml,/data-task-edit="exploration"/);
  assert.match(superHtml,/data-task-delete="exploration"/);
  store.capabilities.isSuperAdmin=false;
  let detail;
  openTask(exploration,store,{...ordinary,openModal(value){detail=value;}});
  assert.match(detail,/data-detail-edit/);
  assert.match(detail,/data-task-review/);
});

test('cross-publisher editing preserves task identity and is only available to super administrators',()=>{
  for (const isSuperAdmin of [false,true]) {
    const store={operatorId:'another',capabilities:{isSuperAdmin},data:{tasks:[exploration,novice],submissions:[],learners:[]},save(){}};
    const render=renderLibrary(store,{isSuperAdmin});
    const notifications=[],routes=[];
    const context=vm.createContext({store,canEditTask,normalizeBadgeWeights,toast:message=>notifications.push(message),navigate:(...args)=>routes.push(args)});
    vm.runInContext(source.slice(source.indexOf('function editTask(task)'),source.indexOf('function saveDraft()')),context);
    for(const task of [exploration,novice]){
      for (const option of ['edit','archive',...(task.camp==='exploration'?['delete']:[])]) {
        assert.equal(render.includes(`data-task-${option}="${task.id}"`),isSuperAdmin);
      }
      context.original={...task,revision:7};
      vm.runInContext('editTask(original)',context);
      if(isSuperAdmin){
        assert.equal(store.data.draft.id,task.id);
        assert.equal(store.data.draft.authorId,task.authorId);
        assert.equal(store.data.draft.revision,7);
        assert.deepEqual(routes.pop(),['publish','saved-task']);
      }else{
        assert.equal(store.data.draft,undefined);
        assert.match(notifications.pop(),/没有编辑/);
      }
    }
  }
});

test('ordinary administrators can copy exploration into a new draft',async()=>{
  const events=[];
  const store={capabilities:{isSuperAdmin:false},data:{tasks:[],draft:structuredClone(exploration)},getTask:()=>exploration,save(){}};
  const workflow=createTaskWorkflow({store,newDraft:()=>({...novice,id:'new',status:'draft'}),openModal(){throw Error('must not offer to save forbidden draft');},closeModal(){},showEditor(){events.push('editor');},toast(message){events.push(message);}});
  await workflow.start(exploration);
  assert.equal(store.data.draft.camp,'exploration');
  assert.equal(store.data.draft.id,'new');
  assert.ok(events.includes('editor'));
});

test('exploration URL opens the exploration editor for both administrator identities',async()=>{
  const previous={fetch:globalThis.fetch,location:globalThis.location,localStorage:globalThis.localStorage};
  globalThis.location={search:'?camp=exploration'};
  globalThis.localStorage={getItem:()=>null};
  try {
    for(const isSuperAdmin of [false,true]) {
      globalThis.fetch=async()=>({ok:true,status:200,json:async()=>({ok:true,data:{actor:{id:'actor',name:'测试管理员'},operatorId:'actor',members:[],tasks:[],reviews:[],capabilities:{isSuperAdmin}}})});
      const store=await ApiStore.create();
      assert.equal(store.data.draft.camp,'exploration');
    }
  } finally {Object.assign(globalThis,previous);}
});

test('pending exploration publication permits approval or return by a super administrator',()=>{
  const request={id:'old',taskId:exploration.id,status:'pending',submittedBy:{id:'ordinary'},task:exploration};
  const store={data:{publicationRequests:[request]},getTask:()=>exploration};
  let html;
  const ui={isSuperAdmin:true,currentUser:{id:'ordinary'},icon:()=>'',openModal(value){html=value;}};
  const controller=createPublicationReviewController({store,service:{},ui});
  const page={contains:()=>true,querySelector:()=>({})};
  controller.bind({querySelector:()=>page});
  page.onclick({target:{closest:()=>({dataset:{pubOpen:'old'}})}});
  assert.match(html,/data-pub-decision="approved"/);
  assert.match(html,/data-pub-decision="rejected"/);
  assert.doesNotMatch(html,/退回此历史申请/);
  assert.match(html,/审核通过并发布/);
});

test('promotion allows the submitting administrator to approve or return a pending publication',async()=>{
  const store={actor:{id:'applicant'},capabilities:{isSuperAdmin:false},data:{publicationRequests:[{id:'request',submittedBy:{id:'applicant'},status:'pending',revision:4}]},async refresh(){}};
  const service=createJourneyService({store}),previous=globalThis.fetch,writes=[];
  globalThis.fetch=async(_url,options)=>{writes.push(JSON.parse(options.body));return Response.json({ok:true,data:{}});};
  try{
    await assert.rejects(service.tasks.reviewPublication('request',{decision:'approved'}),/仅超级管理员/);
    assert.deepEqual(writes,[]);
    store.capabilities.isSuperAdmin=true;
    for(const decision of ['approved','rejected']){
      await service.tasks.reviewPublication('request',{decision,comment:'发布人需补充材料'});
      assert.deepEqual(writes.at(-1),{command:'reviewPublication',id:'request',payload:{expected_revision:4,decision,comment:'发布人需补充材料'}});
    }
  }finally{globalThis.fetch=previous;}
});

function publishHarness(task,isSuperAdmin=true) {
  const state={forms:[],publishCalls:[],submitted:0,saves:0};
  const controls={'#publish-task':{disabled:false},'#confirm-publish':{disabled:true},'#cancel-publish':{},'#publish-error':{hidden:true}};
  const modal={dataset:{},querySelector:()=>null,querySelectorAll:()=>[]};
  const context=vm.createContext({store:{data:{draft:task},members:[],async saveTask(value){state.saves++;return value;}},ui:{isSuperAdmin},materialUploadsPending:false,
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
  assert.equal(h.state.publishCalls[0][1].length,0);
  assert.equal(h.state.submitted,0);
});

test('ordinary task publish buttons submit both camps to review without opening direct publication',async()=>{
  for (const task of [novice, exploration]) {
    const h=publishHarness(task,false);
    await h.run();
    assert.equal(h.state.saves,1);
    assert.equal(h.state.submitted,1);
    assert.equal(h.state.publishCalls.length,0);
  }
});
