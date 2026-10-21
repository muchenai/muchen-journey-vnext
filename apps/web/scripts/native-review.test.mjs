import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { taskView, taskWrite, reviewView, detailView, aiComment, reviewFeedbackError } from '../public/review-native/native-model.js';
import { renderReview, openSubmission } from '../public/review-native/review.js';
import { ApiStore, createJourneyService } from '../public/review-native/native-api.js';
import { learnerTaskTitles, learnerTaskTitle } from '../public/review-native/task-titles.js';
const id = '00000000-0000-4000-8000-000000000001';
const task = { id, title: '测评三', domain: '产品开发', reviewMode: 'ai', badges: [{ id: 'tech', weight: 100 }], revision: 4, materials: [], status: 'published' };
const row = { id, task_id: id, learner_id: 'learner', learner_name: '<script>私密</script>', camp: 'exploration', task_title: '提交时任务名称', domain: '探索营', status: 'ASSIGNED', allowed_commands: ['start'], decision: null, ai_statuses: ['COMPLETED'], submitted_at: '2026-10-21T00:00:00Z', submission_version_no: 2, revision: 6 };
const detail = { id, revision: 7, status: 'IN_REVIEW', allowed_commands: ['approve','request_revision'], submission_body: '当前学员自己的链接', task_title: '固定版本名称', task_purpose: '固定要求', completion_criteria: ['必须完整'], task_learning_materials: [{ title: '本次材料', body: '固定文本' }], materials: { attachments: [{ id: 'clean', original_filename: '安全文件', status: 'READY', scan_status: 'CLEAN' }, { id: 'bad', original_filename: '未扫描', status: 'READY', scan_status: 'PENDING' }] }, document_ai_checks: [{ document_url: 'https://example.com/docx/own', status: 'COMPLETED', record_id: 'r2', result: '最新建议', generated_at: 'today', history: [{ record_id: 'r2', result: '最新建议' }, { record_id: 'r1', result: '上次建议' }] }] };
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
test('approval and return feedback validation counts characters and agrees with server limits', () => {
  assert.match(reviewFeedbackError('passed',' 写得好写得好写得好 '),/当前 9 个字/);
  assert.equal(reviewFeedbackError('passed','已核对全部要求符合标准'),'');
  assert.equal(reviewFeedbackError('passed',''),'');
  assert.match(reviewFeedbackError('returned',''),/至少 10/);
  assert.match(reviewFeedbackError('passed','🙂'.repeat(9)),/当前 9 个字/);
  assert.match(reviewFeedbackError('passed','字'.repeat(2001)),/2000/);
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
    await returned.onclick(); assert.equal(calls, 1);
    assert.equal(pass.disabled, true); assert.equal(returned.disabled, false); assert.equal(reason.disabled, false);
    assert.equal(modal.dataset.operationPending, 'false');
    reason.checked = false; reason.change();
    assert.equal(pass.disabled, false); assert.equal(hint.hidden, true);
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
    assert.match(renderReview({ data: { submissions: [reviewView(row)] }, getTask: () => task }, { reviewCamp: 'exploration' }), /td class="review-reason-cell"/);
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
