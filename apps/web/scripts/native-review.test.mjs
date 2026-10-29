import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { taskView, taskWrite, reviewView, detailView, aiComment, reviewFeedbackError } from '../public/review-native/native-model.js';
import { renderReview, openSubmission, bindReview } from '../public/review-native/review.js';
import { ApiStore, createJourneyService } from '../public/review-native/native-api.js';
import { learnerTaskTitles, learnerTaskTitle } from '../public/review-native/task-titles.js';
import { renderPublishMaterials } from '../public/review-native/publish-materials.js';
import { createTaskWorkflow, copyAsNewTask, hasUnsavedChanges, isTaskUpdate } from '../public/review-native/task-workflow.js';
import {BADGES, rewardBreakdown, applyDifficultyPreset, validateTask} from '../public/review-native/core.js';

test('all eighteen reward types survive the server adapter and split preview',()=>{
  assert.equal(BADGES.length,18);
  assert.equal(new Set(BADGES.map(b=>b.id)).size,18);
  for (const badge of BADGES) {
    const task={difficulty:'进阶',badges:[{id:badge.id,weight:100}]};
    assert.deepEqual(taskView(taskWrite(task)).badges,task.badges);
    const reward=rewardBreakdown(task);
    assert.equal(reward.allocations[0].name,badge.name);
    assert.equal(reward.allocations[0].points,10);
    assert.ok(!validateTask(task).some(e=>e.includes('系统已有的徽章')));
  }
  const reward=rewardBreakdown({difficulty:'挑战',badges:[{id:'it-service',weight:40},{id:'business-operations',weight:60}]});
  assert.deepEqual(reward.allocations.map(b=>b.points),[6,9]);
});

test('integer badge allocations preserve total at every ten percent split',()=>{
  for(const difficulty of ['入门','进阶','挑战']) for(let weight=10;weight<100;weight+=10){
    const reward=rewardBreakdown({difficulty,badges:[{id:'product',weight},{id:'data',weight:100-weight}]});
    assert.ok(reward.allocations.every(item=>Number.isInteger(item.points)));
    assert.equal(reward.allocations.reduce((sum,item)=>sum+item.points,0),reward.totalPoints);
  }
  assert.deepEqual(rewardBreakdown({difficulty:'挑战',badges:[{id:'product',weight:50},{id:'data',weight:50}]}).allocations.map(b=>b.points),[8,7]);
});
test('new publications are free and use twenty-percent allocations',()=>{
  const task=applyDifficultyPreset({difficulty:'挑战',unlockTaskPoints:50,badges:[{id:'product',weight:100}]});
  assert.equal(task.taskPoints,0);assert.equal(task.unlockTaskPoints,0);
  assert.equal(applyDifficultyPreset({...task,difficulty:'入门'}).unlockTaskPoints,0);
  assert.ok(validateTask({...task,badges:[{id:'product',weight:55},{id:'data',weight:45}]}).some(e=>e.includes('20%')));
});

function workflowHarness(dirty=false) {
  const original={id:'original',version:4,versionId:'v4',revision:7,status:'published',title:'已发布任务',summary:'完整的原任务介绍',materials:[],badges:[],camp:'novice',domain:'产品开发'};
  const empty={id:'new',revision:0,status:'draft',title:'',summary:'',materials:[],badges:[],camp:'novice',domain:'产品开发'};
  const controls=Object.fromEntries(['cancel','discard','save','error'].map(key=>[`[data-new-${key}]`,{disabled:false,hidden:true}]));
  const modal={dataset:{},querySelector:key=>controls[key],querySelectorAll:()=>Object.values(controls)};
  const store={data:{draft:{...original,title:dirty?'修改后的标题':original.title}},getTask:()=>original,save(){},async saveTask(value){this.writes=(this.writes||0)+1;if(this.fail)throw Error('保存失败');this.data.draft=value;}};
  const view={opens:0,shows:0,closes:0};
  const workflow=createTaskWorkflow({store,newDraft:()=>structuredClone(empty),openModal:(html,ready)=>{view.opens++;view.html=html;ready(modal);},closeModal:()=>view.closes++,showEditor:()=>view.shows++,toast(){}});
  return {workflow,store,view,controls,original,empty};
}
test('new task opens immediately when published content is unchanged, without resaving or publishing it',()=>{
  const h=workflowHarness();h.workflow.start();
  assert.equal(h.view.opens,0);assert.equal(h.view.shows,1);
  assert.equal(h.store.writes,undefined);assert.equal(h.store.data.draft.id,'new');
  assert.equal(h.original.status,'published');
});
test('unsaved new-task choices preserve, discard or save current edits explicitly',async()=>{
  let h=workflowHarness(true);h.workflow.start();h.controls['[data-new-cancel]'].onclick();
  assert.equal(h.store.data.draft.id,'original');assert.equal(h.view.shows,0);
  h=workflowHarness(true);h.workflow.start();h.controls['[data-new-discard]'].onclick();
  assert.equal(h.store.writes,undefined);assert.equal(h.store.data.draft.id,'new');
  h=workflowHarness(true);h.store.fail=true;h.workflow.start();
  await h.controls['[data-new-save]'].onclick();
  assert.equal(h.store.data.draft.id,'original');assert.equal(h.view.shows,0);
  assert.equal(h.controls['[data-new-error]'].textContent,'保存失败');
  h.store.fail=false;await h.controls['[data-new-save]'].onclick();
  assert.equal(h.store.data.draft.id,'new');assert.equal(h.view.shows,1);
});
test('copy retains editable content but never carries source identity, release version, or learner statistics',()=>{
  const h=workflowHarness();const source={...h.original,participants:99,completions:8,authorId:'other',stableKey:'ADMIN-original'};
  const copy=copyAsNewTask(source,h.empty);
  assert.equal(copy.id,'new');assert.equal(copy.revision,0);assert.equal(copy.title,source.title);
  for(const key of ['version','versionId','participants','completions','authorId','stableKey'])assert.equal(copy[key],undefined);
  assert.equal(isTaskUpdate(copy),false);assert.equal(isTaskUpdate(source),true);
  assert.equal(hasUnsavedChanges({...source,updatedAt:'later',participants:100},source,h.empty),false);
  h.workflow.start(source);assert.equal(h.store.data.draft.id,'new');assert.equal(h.store.writes,undefined);
});

test('publication confirmation retains image and document downloads alongside named external links', () => {
  const materials = [
    {type:'image',name:'测试图片.png',mime:'image/png',size:1024,url:'data:image/png;base64,YQ=='},
    {type:'file',name:'学习资料.pdf',mime:'application/pdf',size:2048,url:'data:application/pdf;base64,Yg=='},
    {type:'link',name:'公司资料',url:'https://example.com/material'},
    {type:'link',name:'资料副本',url:'https://example.com/material'},
  ];
  const before=JSON.stringify(materials), html=renderPublishMaterials(materials);
  for(const m of materials) assert.ok(html.includes(m.name));
  assert.match(html,/学习材料（4）/);
  assert.match(html,/download="测试图片.png"/);
  assert.match(html,/download="学习资料.pdf"/);
  assert.match(html,/<details><summary>查看图片/);
  assert.match(html,/image\/png · 1 KB/);
  assert.equal((html.match(/data-verified-link=/g)||[]).length,1);
  assert.equal(JSON.stringify(materials),before);
});

test('publication material names are escaped and unsafe links cannot execute', () => {
  const html=renderPublishMaterials([{type:'link',name:'<img onerror=alert(1)>',url:'javascript:alert(1)'}]);
  assert.doesNotMatch(html,/<img|href="javascript:/);
  assert.match(html,/&lt;img/);
  assert.doesNotMatch(renderPublishMaterials([{type:'file',name:'a.txt',mime:'text/plain',size:1,url:'data:text/plain;base64,YQ=='}]),/data-verified-link/);
});
const id = '00000000-0000-4000-8000-000000000001';
const task = { id, title: '测评三', domain: '产品开发', reviewMode: 'ai', badges: [{ id: 'tech', weight: 100 }], revision: 4, materials: [], status: 'published' };
const row = { id, task_id: id, learner_id: 'learner', learner_name: '<script>私密</script>', camp: 'exploration', task_title: '提交时任务名称', domain: '探索营', status: 'ASSIGNED', allowed_commands: ['start'], decision: null, ai_statuses: ['COMPLETED'], submitted_at: '2026-10-21T00:00:00Z', submission_version_no: 2, revision: 6 };
const detail = { id, revision: 7, status: 'IN_REVIEW', allowed_commands: ['approve','request_revision'], submission_body: '当前学员自己的链接', task_title: '固定版本名称', task_purpose: '固定要求', completion_criteria: ['必须完整'], task_learning_materials: [{ title: '本次材料', body: '固定文本' }], materials: { attachments: [{ id: 'clean', original_filename: '安全文件', status: 'READY', scan_status: 'CLEAN' }, { id: 'bad', original_filename: '未扫描', status: 'READY', scan_status: 'PENDING' }] }, document_ai_checks: [{ document_url: 'https://example.com/docx/own', status: 'COMPLETED', record_id: 'r2', result: '最新建议', generated_at: 'today', history: [{ record_id: 'r2', result: '最新建议' }, { record_id: 'r1', result: '上次建议' }] }] };
function selectReviewTab(store, tab, camp = 'exploration') {
  const page = { querySelector() { return null; } };
  bindReview({querySelector: () => page}, store, {reviewCamp:camp, refresh() {}});
  page.onclick({target:{closest: selector => selector === '[data-review-tab]' ? {dataset:{reviewTab:tab}} : null}});
}

test('Feishu learners show a real employee number in every camp and review tab', () => {
  const base = reviewView({...row, learner_is_feishu:true, learner_employee_no:'MCE0000042'});
  const store = {data:{submissions:[base]},getTask:()=>task};
  for (const camp of ['exploration','novice']) {
    for (const tab of ['pending','reviewing','ai','reviewed','passed','failed']) {
      store.data.submissions = [{...base,camp,status:['reviewed','passed'].includes(tab) ? 'passed' : tab === 'failed' ? 'returned' : 'pending',
        claim:tab === 'reviewing' ? {owner_name:'审核员',mine:false} : null}];
      selectReviewTab(store,tab,camp);
      const html = renderReview(store,{reviewCamp:camp});
      assert.ok(html.includes('工号：MCE0000042'), `${camp}/${tab}`);
      assert.ok(!html.includes('class="cell-subtext">learner</span>'));
    }
  }
  selectReviewTab(store,'pending');
  store.data.submissions = [{...base, studentEmployeeNo:''}];
  assert.match(renderReview(store,{reviewCamp:'exploration'}), /工号未填写/);
  store.data.submissions = [{...base, studentEmployeeNo:'<b>123</b>'}];
  assert.match(renderReview(store,{reviewCamp:'exploration'}), /工号：&lt;b&gt;123&lt;\/b&gt;/);
  store.data.submissions = [reviewView(row)];
  assert.match(renderReview(store,{reviewCamp:'exploration'}), /手机号未补充/);
  selectReviewTab(store,'pending','novice');
  selectReviewTab(store,'pending','exploration');
});
test('phone learners show name and phone, while Feishu keeps its employee number', () => {
  const phone = reviewView({...row, learner_phone:'13900000042'});
  const store = {data:{submissions:[phone]},getTask:()=>task};
  selectReviewTab(store,'pending');
  const html = renderReview(store,{reviewCamp:'exploration'});
  assert.match(html,/手机号：13900000042/);
  assert.doesNotMatch(html,/class="cell-subtext">learner<\/span>/);
  store.data.submissions = [{...phone,studentIsFeishu:true,studentEmployeeNo:'MCE0042'}];
  const corporate = renderReview(store,{reviewCamp:'exploration'});
  assert.match(corporate,/工号：MCE0042/);
  assert.doesNotMatch(corporate,/13900000042/);
});

test('actual reviewer and server time render safely, without falling back to an assignee', async () => {
  const credit = { id: 'executor', name: '<b>实际审核员</b>' };
  const at = '2026-10-22T08:09:10Z';
  const base = reviewView({ ...row, decision: 'PASS', actual_reviewer: credit, reviewed_at: at });
  const store = { data: { submissions: [base], claims: {}, learners: [] }, getTask: () => task, async loadSubmission() {} };
  selectReviewTab(store, 'reviewed');
  const html = renderReview(store, { reviewCamp: 'exploration' });
  assert.ok(html.includes('<th>实际审核人</th><th>审核时间</th>'));
  assert.ok(html.includes('&lt;b&gt;实际审核员&lt;/b&gt;'));
  assert.ok(html.includes('16:09:10'));
  const final = detailView(base, { ...detail, status: 'FINALIZED', allowed_commands: [],
    actual_reviewer: credit, reviewed_at: at, evaluation: { decision: 'PASS', overall_feedback: '已完成' } }, task, 'http://localhost');
  store.data.submissions = [final];
  let modalHtml;
  await openSubmission(store, { reviewCamp: 'exploration', openModal(html) { modalHtml = html; }, toast(message) { assert.fail(message); } }, id);
  assert.match(modalHtml, /实际审核人：<strong>&lt;b&gt;实际审核员&lt;\/b&gt;<\/strong>/);
  assert.match(modalHtml, /审核时间：[\s\S]*16:09:10/);
  const pending = detailView(base, detail, task, 'http://localhost');
  assert.equal(pending.actualReviewer, null);
  assert.equal(pending.reviewedAt, null);
  assert.equal(reviewView({ ...row, reviewer_name: '原负责人' }).actualReviewer, null);
  selectReviewTab(store, 'pending');
});

test('each review tab has only relevant columns and claims separate pending from in-progress', () => {
  const pending = reviewView(row), active = { ...reviewView(row), id:'active', claim:{owner_name:'另一审核员', mine:false, started_at:'2026-10-22T08:00:00Z'} };
  const store = { data:{submissions:[pending,active]}, getTask: () => task };
  const expected = {
    pending:['学员','任务','提交时间','状态','操作'],
    reviewing:['学员','任务','提交时间','正在审核人','开始审核时间','操作'],
    ai:['学员','任务','自测状态','自测时间','操作'],
    reviewed:['学员','任务','评分','提交时间','状态','实际审核人','审核时间','操作'],
    passed:['学员','任务','评分','提交时间','实际审核人','审核时间','操作'],
    failed:['学员','任务','提交时间','未通过原因','实际审核人','审核时间','操作'],
  };
  for (const [tab, columns] of Object.entries(expected)) {
    selectReviewTab(store, tab);
    const html = renderReview(store,{reviewCamp:'exploration'});
    assert.deepEqual([...html.matchAll(/<th>(.*?)<\/th>/g)].map(m=>m[1]), columns);
    if (tab === 'pending') { assert.ok(html.includes('去审核')); assert.ok(!html.includes('data-review-open="active"')); }
    if (tab === 'reviewing') { assert.ok(html.includes('另一审核员')); assert.ok(html.includes('他人审核中')); }
  }
  selectReviewTab(store, 'pending');
});

test('reviewed combines both decisions while passed and failed remain separate within each camp', () => {
  const base=reviewView(row);
  for(const camp of ['exploration','novice']) {
    const store={data:{submissions:[
      {...base,id:'pass-result',camp,status:'passed'},
      {...base,id:'return-result',camp,status:'returned'},
      {...base,id:'pending-result',camp,status:'pending'},
      {...base,id:'old-result',camp,status:'passed',supersededBy:'pass-result'},
      {...base,id:'other-camp',camp:camp==='exploration'?'novice':'exploration',status:'passed'},
    ]},getTask:()=>task};
    for(const [tab,expected] of [['reviewed',['pass-result','return-result']],['passed',['pass-result']],['failed',['return-result']]]) {
      selectReviewTab(store,tab,camp);
      const html=renderReview(store,{reviewCamp:camp});
      assert.deepEqual([...html.matchAll(/data-review-tab="([^"]+)"/g)].map(m=>m[1]),['pending','reviewing','ai','reviewed','passed','failed']);
      assert.deepEqual([...html.matchAll(/data-review-open="([^"]+)"/g)].map(m=>m[1]),expected);
      assert.match(html,/data-review-tab="reviewed">已审核<span class="count-badge">2<\/span>/);
      assert.match(html,/data-review-tab="passed">审核通过<span class="count-badge">1<\/span>/);
      assert.match(html,/data-review-tab="failed">审核未通过<span class="count-badge">1<\/span>/);
    }
    selectReviewTab(store,'pending',camp);
  }
});

test('failed exclusive claim prevents opening submission or loading its document', async () => {
  let reads=0, opened=0, notice;
  const store = {data:{submissions:[reviewView(row)]}, async updateReviewClaim() {throw new Error('该文档正在被其他人审核');}, async loadSubmission(){reads++;}};
  await openSubmission(store,{reviewCamp:'exploration',openModal(){opened++;},toast(text){notice=text;}}, id);
  assert.equal(reads,0); assert.equal(opened,0); assert.match(notice,/正在被其他人审核/);
});

test('historical submissions retain their own reviewer and never inherit current attribution', async () => {
  const originalFetch = globalThis.fetch, originalLocation = globalThis.location;
  const oldReviewer = { id: 'old', name: '上次审核员' }, currentReviewer = { id: 'current', name: '本次审核员' };
  const history = [
    { id: 'v1', version_no: 1, review_id: 'r1', decision: 'REVISION_REQUIRED', actual_reviewer: oldReviewer, reviewed_at: '2026-10-20T02:00:00Z' },
    { id: 'v2', version_no: 2, review_id: null },
  ];
  try {
    globalThis.location = { origin: 'http://localhost' };
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ ok: true, data: {
      ...detail, submission_version_id: 'v3', actual_reviewer: currentReviewer, reviewed_at: '2026-10-22T02:00:00Z', submission_history: history,
    } }) });
    const store = new ApiStore(); store.data = { tasks: [task], submissions: [reviewView(row)] };
    await store.loadSubmission(id);
    const older = store.data.submissions.filter(s => s.historical);
    assert.deepEqual(older[0].actualReviewer, oldReviewer);
    assert.equal(older[0].reviewedAt, history[0].reviewed_at);
    assert.equal(older[1].actualReviewer, null);
    assert.equal(older[1].reviewedAt, null);
  } finally { globalThis.fetch = originalFetch; globalThis.location = originalLocation; }
});
test('badge IDs round-trip without changing revision or task identity', () => {
  const view = taskView(task); assert.equal(view.badges[0].id, 'dev');
  const payload = taskWrite(view); assert.equal(payload.badges[0].id, 'tech'); assert.equal(payload.revision,4); assert.equal(payload.id,id);
});

test('all learner stage names replace legacy review titles while keeping identities and versioned requirements', async () => {
  const originalFetch = globalThis.fetch;
  const tasks = Object.keys(learnerTaskTitles).map((stableKey, i) => ({ ...task, id: String(i), stableKey, title: '旧任务名称' }));
  const reviews = tasks.map(t => ({ ...row, id: `review-${t.id}`, task_id: t.id, task_title: 'Day 0 / 启程' }));
  try {
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ ok: true, data: { actor: { id: 'reviewer' }, tasks, reviews, members: [] } }) });
    const store = new ApiStore(); store.data = {};
    await store.refresh();
    assert.equal(store.data.tasks.length, 8);
    for (const t of tasks) {
      const expected = learnerTaskTitles[t.stableKey];
      const base = store.data.submissions.find(s => s.taskId === t.id);
      assert.equal(store.getTask(t.id).title, expected);
      assert.equal(base.taskSnapshot.title, expected);
      for (const currentTask of [store.getTask(t.id), undefined]) {
        const view = detailView(base, detail, currentTask, 'http://localhost');
        assert.equal(view.taskSnapshot.title, expected);
        assert.equal(view.taskId, t.id);
        assert.equal(view.revision, detail.revision);
        assert.equal(view.taskSnapshot.materials[0].text, '固定文本');
      }
    }
    assert.equal(learnerTaskTitle('DAY-0', ''), 'Day 1｜启程-公司基础介绍材料');
    assert.equal(learnerTaskTitle('CUSTOM', '自定义任务'), '自定义任务');
    assert.equal(learnerTaskTitle('toString', '自定义任务'), '自定义任务');
  } finally { globalThis.fetch = originalFetch; }
});
test('AI advice never approves a human review, camps stay isolated and user content is escaped', () => {
  const value = reviewView(row); assert.equal(value.status,'pending'); assert.equal(value.reviewMode,'manual'); assert.equal(value.canReview,true);
  const store = { data: { submissions: [value] }, getTask: () => task };
  const html = renderReview(store,{reviewCamp:'exploration'});
  assert.ok(html.includes('&lt;script&gt;私密&lt;/script&gt;')); assert.ok(!html.includes('<script>私密'));
  assert.ok(renderReview(store,{reviewCamp:'novice'}).includes('暂无待审核答案'));
});
test('detail uses fixed-version requirements and exposes only clean attachment downloads', () => {
  const value = detailView(reviewView(row),detail,taskView(task),'http://localhost:3000');
  assert.equal(value.taskSnapshot.title,'固定版本名称'); assert.equal(value.answer, detail.submission_body);
  assert.equal(value.revision,7); assert.equal(value.ai.score,null); assert.ok(value.attachments[0].url.includes('/review/'));
  assert.equal(value.attachments[1].url,''); assert.equal(value.taskSnapshot.materials[0].text,'固定文本');
  assert.equal(value.ai.comment.match(/最新建议/g).length,1); assert.ok(value.ai.comment.includes('上次建议'));
  assert.equal(detailView(reviewView(row),{...detail,status:'SUPERSEDED'},task,'http://localhost').canReview,false);
});
test('AI history is per document and retains prior evaluations', () => {
  const text = aiComment([...detail.document_ai_checks,{document_url:'https://example.com/docx/second',status:'RUNNING',history:[]}]);
  assert.ok(text.includes('上次建议')); assert.ok(text.includes('/second')); assert.ok(text.includes('自查中'));
});
test('approval comments are optional and returns need five non-whitespace characters', () => {
  for (const value of ['', '  \n\t', '好', '写得好写得好写得好', '🙂']) {
    assert.equal(reviewFeedbackError('passed', value), '');
  }
  for (const value of ['', '  \n\t', '请补材料', '请 \n补\t材 料', '🙂'.repeat(4)]) {
    assert.match(reviewFeedbackError('returned', value), /至少 5/);
  }
  for (const value of ['请补充材料', '请 \n补\t充 材料', '🙂'.repeat(5)]) {
    assert.equal(reviewFeedbackError('returned', value), '');
  }
  for (const decision of ['passed', 'returned']) {
    assert.equal(reviewFeedbackError(decision, '字'.repeat(2000)), '');
    assert.match(reviewFeedbackError(decision, '字'.repeat(2001)), /2000/);
  }
});

test('designer decision controls disable approval for checked reasons and restore correctly after failure', async () => {
  const originalDocument = globalThis.document;
  const pass = { dataset: { reviewDecision: 'passed' }, setAttribute() {} };
  const returned = { dataset: { reviewDecision: 'returned' } };
  const reason = { value: 'incorrect_answer', checked: false, addEventListener(type, fn) { this[type] = fn; }, focus() {} };
  const error = {}, score = { value: '', focus() {} }, comment = { value: '请核对题目并补充相应的判断依据', focus() {} };
  let hint, calls = 0, closed = 0;
  const modal = { dataset: {}, classList: { add() {} },
    querySelectorAll(selector) {
      if (selector === '[data-review-reason-code]') return [reason];
      if (selector === '[data-review-reason-code]:checked') return reason.checked ? [reason] : [];
      if (selector === '[data-review-decision]') return [pass, returned];
      return [];
    },
    querySelector(selector) { return ({
      '[data-review-decision="passed"]': pass, '[data-review-score]': score,
      '[data-review-comment]': comment, '[data-review-error]': error,
      '.return-reason-options': { insertAdjacentElement(position, value) { hint = value; } },
    })[selector]; },
  };
  const store = { data: { submissions: [reviewView(row)], claims: {}, learners: [] }, getTask: () => task, async loadSubmission() {} };
  const ui = { reviewCamp: 'exploration', openModal(html, bind) { bind(modal); }, closeModal() { closed++; }, refresh() {}, toast() {},
    service: { submissions: { async review(id, payload) { calls++; if (payload.decision === 'returned') throw new Error('模拟连接失败'); return { ok: true }; } } },
  };
  try {
    globalThis.document = { createElement: () => ({ setAttribute() {} }) };
    await openSubmission(store, ui, id);
    assert.equal(pass.disabled, false);
    reason.checked = true; reason.change();
    assert.equal(pass.disabled, true); assert.equal(returned.disabled, false); assert.equal(hint.hidden, false);
    await pass.onclick(); assert.equal(calls, 0);
    for (const value of ['', '请补材料', '请 \n补\t材 料']) {
      comment.value = value;
      await returned.onclick(); assert.equal(calls, 0);
      assert.match(error.textContent, /至少 5/);
    }
    comment.value = '请补充材料';
    await returned.onclick(); assert.equal(calls, 1);
    assert.equal(pass.disabled, true); assert.equal(returned.disabled, false); assert.equal(reason.disabled, false);
    assert.equal(modal.dataset.operationPending, 'false');
    reason.checked = false; reason.change();
    assert.equal(pass.disabled, false); assert.equal(hint.hidden, true);
    comment.value = '';
    await pass.onclick(); assert.equal(calls, 2); assert.equal(closed, 1);
  } finally { globalThis.document = originalDocument; }
});

test('real API adapter rejects approval with return reasons without sending a request', async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  try {
    globalThis.fetch = async () => { calls++; throw new Error('unexpected request'); };
    const service = createJourneyService({ store: { data: { submissions: [reviewView(row)] } } });
    await assert.rejects(() => service.submissions.review(id, { decision: 'passed', comment: '', reasonCodes: ['incorrect_answer'] }), /取消勾选/);
    assert.equal(calls, 0);
    assert.doesNotMatch(renderReview({ data: { submissions: [reviewView(row)] }, getTask: () => task }, { reviewCamp: 'exploration' }), /<th>未通过原因<\/th>/);
  } finally { globalThis.fetch = originalFetch; }
});
test('publication requires a chosen reviewer and every material confirmation', async () => {
  const originalFetch=globalThis.fetch;
  const draft={...task,materials:[{id:'m',type:'link',url:'https://example.com/reference',name:'材料'}]};
  let calls=[];
  const store={members:[{id:'reviewer',roles:['REVIEWER']}],data:{tasks:[],draft},save(){},async refresh(){}};
  const service=createJourneyService({store});
  try {
    globalThis.fetch=async(url,init)=>{calls.push(JSON.parse(init.body));return {ok:true,json:async()=>({ok:true,data:{...draft,status:'published'}})};};
    await assert.rejects(()=>service.tasks.publish(draft,'',[],id),/复核人/);
    await assert.rejects(()=>service.tasks.publish(draft,'reviewer',[],id),/全部学习材料/);
    assert.equal(calls.length,0);
    await service.tasks.publish(draft,'reviewer',['https://example.com/reference'],id);
    assert.equal(calls[0].command,'publishTask'); assert.equal(calls[0].task.revision,4);
    assert.deepEqual(calls[0].payload,{reviewerId:'reviewer',verified:['https://example.com/reference']});
    assert.equal(store.data.draft.status,'published');
  } finally {globalThis.fetch=originalFetch;}
});
test('failed reads fail closed; saved review commands retain revisions and retry idempotency', async () => {
  const originalFetch=globalThis.fetch;
  try {
    globalThis.fetch=async()=>({ok:true,json:async()=>({ok:false,error:'无权限'})});
    await assert.rejects(()=>ApiStore.create(),/无权限/);
    const submission={...reviewView(row),revision:7};
    let calls=[];
    globalThis.fetch=async(url,init)=>{calls.push(JSON.parse(init.body));return {ok:true,json:async()=>({ok:false,error:'版本冲突'})};};
    const service=createJourneyService({store:{data:{submissions:[submission]}}});
    const input={decision:'returned',comment:'请补齐材料后再提交审核',score:null,reasonCodes:['materials_incomplete']};
    await assert.rejects(()=>service.submissions.review(id,input),/版本冲突/);
    await assert.rejects(()=>service.submissions.review(id,input),/版本冲突/);
    assert.equal(calls[0].key,calls[1].key); assert.equal(calls[0].payload.expected_revision,7);
    assert.equal(calls[0].payload.decision,'REQUEST_REVISION'); assert.deepEqual(calls[0].payload.reasons,['提交材料不完整']);
    assert.equal(submission.status,'pending'); assert.equal(submission.canReview,true);
  } finally {globalThis.fetch=originalFetch;}
});
test('all native modules parse and all visual assets retain supplied bytes', async () => {
  const base = new URL('../public/review-native/',import.meta.url);
  for (const name of await readdir(base)) if(name.endsWith('.js')) {
    const result=spawnSync(process.execPath,['--check',fileURLToPath(new URL(name,base))],{encoding:'utf8'});
    assert.equal(result.status,0,`${name}: ${result.stderr}`);
  }
  const manifest=JSON.parse(await readFile(new URL('../public/review-native/visual-assets.sha256.json',import.meta.url),'utf8'));
  for (const [name,expected] of Object.entries(manifest)) assert.equal(createHash('sha256').update(await readFile(new URL(name,base))).digest('hex'),expected,name);
});
