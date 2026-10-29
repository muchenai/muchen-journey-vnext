import test from 'node:test';
import assert from 'node:assert/strict';
import {visiblePublications,createPublicationReviewController} from '../public/review-native/publication-review.js';

const record=(id,status,day,owner='mine')=>({id,taskId:'task-one',status,submittedAt:`2026-10-${day}T08:00:00Z`,submittedBy:{id:owner,name:owner},task:{title:'原任务',camp:'novice',difficulty:'入门',domain:'产品开发',badges:[]},comment:'补充材料 <详情>'});
function harness(rows,superAdmin=false){
  const task={id:'task-one',authorId:'mine',status:'draft',publication:{id:rows[0].id,status:rows[0].status}};
  const store={data:{publicationRequests:rows},getTask:()=>task,refresh:async()=>{}};
  const observed={};
  const ui={isSuperAdmin:superAdmin,currentUser:{id:'mine'},icon:()=>'',toast:message=>observed.toast=message,refresh:()=>{},closeModal:()=>{},openModal:html=>observed.modal=html,editTask:value=>observed.edited=value};
  const controller=createPublicationReviewController({store,service:{},ui});
  const page={contains:()=>true,querySelector:()=>({})};
  controller.bind({querySelector:()=>page});
  const click=dataset=>page.onclick({target:{closest:()=>({dataset})}});
  return {controller,click,store,task,observed};
}
test('ordinary submissions are owned and only latest request determines task status',()=>{
  const rows=[record('old','rejected','21'),record('other','rejected','24','someone-else'),record('new','pending','23')];
  assert.deepEqual(visiblePublications(rows,'mine',false).map(r=>r.id),['new']);
  assert.equal(visiblePublications(rows,'super',true).length,3);
});
test('ordinary pending detail is read-only; super administrator retains decision controls',()=>{
  const ordinary=harness([record('pending','pending','23')]);
  assert.match(ordinary.controller.render(),/我的发布/);
  ordinary.click({pubOpen:'pending'});
  assert.match(ordinary.observed.modal,/等待超级管理员审核/);
  assert.doesNotMatch(ordinary.observed.modal,/data-pub-submit|data-pub-decision=/);
  const boss=harness([record('pending','pending','23')],true);
  boss.click({pubOpen:'pending'});
  assert.match(boss.observed.modal,/data-pub-submit/);
});
test('returned list shows escaped reason and reopens original task for resubmission',async()=>{
  const h=harness([record('return','rejected','23')]);
  h.click({pubStatus:'rejected'});
  const html=h.controller.render();
  assert.match(html,/补充材料 &lt;详情&gt;/);
  assert.match(html,/修改并重新提交/);
  assert.equal(h.controller.badgeCount(),1);
  h.click({pubRevise:'return'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.observed.edited,h.task);
  assert.equal(h.observed.edited.id,'task-one');
});
test('outdated return action cannot reopen a task already resubmitted',async()=>{
  const h=harness([record('return','rejected','23')]);
  h.store.refresh=async()=>{
    h.store.data.publicationRequests.unshift(record('next','pending','24'));
    h.task.publication={id:'next',status:'pending'};
  };
  h.click({pubRevise:'return'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.observed.edited,undefined);
  assert.match(h.observed.toast,/状态已变化/);
  assert.equal(h.controller.badgeCount(),0);
});
