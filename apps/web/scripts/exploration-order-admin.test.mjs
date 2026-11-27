import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {isPinnedExplorationTask, nextExplorationOrder, explorationDisplayOrder} from '../public/review-native/exploration-order.js';
import {renderLibrary, bindLibrary, openTask} from '../public/review-native/library.js';
import {copyAsNewTask} from '../public/review-native/task-workflow.js';
import {ApiStore} from '../public/review-native/native-api.js';
import {getReviewCamp, escapeHtml, REVIEW_CAMPS} from '../public/review-native/core.js';
import {EXPLORATION_COMPLETION_MODES, explorationCompletionMode, requiresTaskAssessment} from '../public/review-native/exploration-completion.js';
import {TASK_FIELD_LIMITS, taskFieldLength} from '../public/review-native/task-field-limits.js';

const fixedKey='EXPLORATION-DYNAMIC-20261117-08';
const task=(id,order,extra={})=>({id,camp:'exploration',title:id,summary:'完整的探索营学习任务内容。',order,publishedOrder:order,status:'published',completionMode:'learning',materials:[],badges:[],rubric:[],...extra});
const signout=task('signout',2,{stableKey:fixedKey,completionMode:'checkin'});

test('only the canonical sign-out identity is fixed; title and completion mode do not pin ordinary tasks',()=>{
  assert.equal(isPinnedExplorationTask(signout),true);
  assert.equal(isPinnedExplorationTask(task('flagged',2,{pinnedLast:true})),true);
  assert.equal(isPinnedExplorationTask(task('renamed',2,{stableKey:fixedKey,title:'培训签退新版'})),true);
  assert.equal(isPinnedExplorationTask(task('ordinary',2,{title:'培训签退',completionMode:'checkin'})),false);
  assert.equal(isPinnedExplorationTask({...signout,camp:'novice'}),false);
});

test('new ordinary tasks append before sign-out even when historical stored positions have tasks after it',()=>{
  const tasks=[task('first',1),signout,task('later',9),task('novice',100,{camp:'novice'}),task('archived',200,{status:'archived'}),task('draft',500,{status:'draft',publishedOrder:undefined})];
  assert.equal(nextExplorationOrder(tasks),3);
  assert.equal(explorationDisplayOrder(task('new',9999),tasks),3);
  assert.equal(explorationDisplayOrder(task('later',9999),tasks),2);
  assert.equal(explorationDisplayOrder(task('new',1),tasks),1);
  assert.equal(explorationDisplayOrder(task('new',''),tasks),null);
  assert.equal(nextExplorationOrder([task('ordinary',4),{...signout,status:'archived'}]),5);
  assert.equal(nextExplorationOrder([task('first',1),task('ordinary-checkin',2,{completionMode:'checkin'})]),3);
});

const appSource=await readFile(new URL('../public/review-native/app.js',import.meta.url),'utf8');
function basics(draft){
  const context=vm.createContext({store:{data:{draft}},ui:{isSuperAdmin:true},getReviewCamp,isPinnedExplorationTask,cardHeader:()=>'',icon:()=>'',e:escapeHtml,
    REVIEW_CAMPS,TASK_FIELD_LIMITS,taskFieldLength,EXPLORATION_COMPLETION_MODES,explorationCompletionMode,requiresTaskAssessment});
  vm.runInContext(appSource.slice(appSource.indexOf('function renderCampField('),appSource.indexOf('function renderRatio()')),context);
  return vm.runInContext('renderBasics()',context);
}

test('actual sign-out editor explains its fixed position without an editable numeric order control',()=>{
  const fixed=basics(signout);
  assert.match(fixed,/<input[^>]+value="固定在毕业码前"[^>]+readonly/);
  assert.doesNotMatch(fixed,/data-field="order"/);
  assert.match(fixed,/新增普通任务自动排在它前面/);
  const ordinary=basics(task('ordinary',3,{title:'培训签退',completionMode:'checkin'}));
  assert.match(ordinary,/data-field="order" type="number"/);
  assert.match(ordinary,/超出普通任务数量时插入培训签退前/);
  assert.doesNotMatch(ordinary,/大于任务总数时排在最后/);
});

test('copying sign-out creates an ordinary task before it and does not inherit fixed identity',()=>{
  const original={...signout,pinnedLast:true};
  const copy=copyAsNewTask(original,{id:'copy',order:3});
  assert.equal(copy.order,3);
  assert.equal(copy.stableKey,undefined);
  assert.equal(copy.pinnedLast,undefined);
  assert.equal(isPinnedExplorationTask(copy),false);
});

test('library puts sign-out after ordinary tasks and consistently labels its fixed position',()=>{
  const store={data:{tasks:[signout,task('later',9),task('first',1)],submissions:[]}};
  const ui={isSuperAdmin:true,refresh(){}};
  const filter={addEventListener(_event,handler){handler({target:{value:'exploration'}});}};
  bindLibrary({querySelectorAll:()=>[],querySelector:selector=>selector==='#library-camp'?filter:null},store,ui);
  const html=renderLibrary(store,ui);
  assert.ok(html.indexOf('data-task-view="first"')<html.indexOf('data-task-view="later"'));
  assert.ok(html.indexOf('data-task-view="later"')<html.indexOf('data-task-view="signout"'));
  const signoutRow=html.match(/<tr>\s*<td><strong>固定在毕业码前<\/strong>[\s\S]*?<\/tr>/)?.[0];
  assert.ok(signoutRow);
  assert.doesNotMatch(signoutRow,/草稿：/);
  let detail;
  openTask(signout,store,{...ui,openModal(value){detail=value;}});
  assert.match(detail,/任务排序 <strong>固定在毕业码前<\/strong>/);
});

test('restored sign-out drafts take fixed metadata and numeric validity from the current server catalog',async()=>{
  const before={fetch:globalThis.fetch,location:globalThis.location,localStorage:globalThis.localStorage};
  globalThis.location={search:'?camp=exploration'};
  globalThis.localStorage={getItem:()=>JSON.stringify({...signout,stableKey:undefined,pinnedLast:undefined,order:'',title:'保留我未保存的标题'})};
  globalThis.fetch=async()=>({ok:true,status:200,json:async()=>({ok:true,data:{actor:{id:'actor',name:'管理员'},operatorId:'actor',members:[],tasks:[{...signout,pinnedLast:true,order:3,publishedOrder:3}],reviews:[],capabilities:{isSuperAdmin:true}}})});
  try{
    const store=await ApiStore.create();
    assert.equal(isPinnedExplorationTask(store.data.draft),true);
    assert.equal(store.data.draft.order,3);
    assert.equal(store.data.draft.title,'保留我未保存的标题');
  }finally{Object.assign(globalThis,before);}
});
