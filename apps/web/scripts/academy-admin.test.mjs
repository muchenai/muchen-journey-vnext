import assert from 'node:assert/strict';
import test from 'node:test';
import { createAcademyApi, ACADEMY_TAGS } from '../public/review-native/academy-api.js';
import { createAcademyController } from '../public/review-native/academy.js';

const course = (extra = {}) => ({ id: 'course-1', type: 'link', title: 'AI 实践', summary: '整理会议记录', minutes: 15, url: 'https://example.com/course', tags: ['AI 整理会议纪要'], author: { id: 'admin', name: '管理员' }, revision: 1, visibility: 'published', createdAt: '2026-11-05T01:00:00Z', ...extra });
const snapshot = (courses = [], shares = []) => ({ courses, shares, stats: { total: courses.length, published: courses.filter(c => c.visibility !== 'unpublished').length, unpublished: courses.filter(c => c.visibility === 'unpublished').length, pending: shares.filter(s => s.status === 'pending').length }, tags: [...ACADEMY_TAGS] });
const response = (data, status = 200) => new Response(JSON.stringify(status === 200 ? { ok: true, data } : { ok: false, error: data }), { status, headers: { 'Content-Type': 'application/json' } });
function harness(handler) {
  const calls = [], user = { id: 'admin', accessRole: 'super_admin' };
  const store = createAcademyApi({ getCurrentUser: () => user, fetcher: async (url, options) => { const body = options.body instanceof Blob ? options.body : options.body ? JSON.parse(options.body) : undefined; const call = { url, ...options, body }; calls.push(call); return handler(call, calls); } });
  return { store, calls, user };
}

test('academy starts empty and reads authenticated server data instead of prototype courses', async () => {
  const h = harness(() => response(snapshot([course()])));
  assert.equal(h.store.loaded, false); assert.deepEqual(h.store.listManagedCourses(), []);
  await h.store.refresh();
  assert.equal(h.store.loaded, true); assert.equal(h.store.getAdminStats().total, 1);
  assert.equal(h.calls[0].credentials, 'same-origin'); assert.equal(h.calls[0].cache, 'no-store');
  assert.equal(h.store.listManagedCourses({ tag: 'AI 写邮件' }).length, 0);
  assert.equal(h.store.listManagedCourses({ tag: 'AI 整理会议纪要', query: '会议' }).length, 1);
  const copy = h.store.getManagedCourse('course-1'); copy.title = '不可改写缓存';
  assert.equal(h.store.getManagedCourse('course-1').title, 'AI 实践');
});

test('a failed refresh retains last acknowledged data and exposes a retry error', async () => {
  let fail = false;
  const h = harness(() => fail ? response('暂时无法连接', 503) : response(snapshot([course()])));
  await h.store.refresh(); fail = true;
  await assert.rejects(h.store.refresh(), /暂时无法连接/);
  assert.equal(h.store.loaded, true); assert.equal(h.store.getManagedCourse('course-1').title, 'AI 实践'); assert.equal(h.store.error, '暂时无法连接');
});

test('course mutations carry revisions and update the list only after acknowledgment', async () => {
  const h = harness(call => call.method === 'GET' ? response(snapshot([course()])) : response(course({ ...call.body, revision: 2, visibility: call.body.visible === false ? 'unpublished' : 'published' })));
  await h.store.refresh(); await h.store.setCourseVisibility('course-1', false);
  assert.deepEqual(h.calls[1].body, { visible: false, expected_revision: 1 });
  assert.equal(h.store.getAdminStats().unpublished, 1);
  await h.store.updateCourse('course-1', { ...course(), title: '新标题', expected_revision: 1 });
  assert.equal(h.calls[2].method, 'PATCH'); assert.equal(h.calls[2].body.expected_revision, 1);
});

test('video publishes after every chunk is acknowledged and complete verifies the upload', async () => {
  const h = harness(call => {
    if (call.url.endsWith('/uploads')) return response({ id: 'upload-1', chunkSize: 524288 });
    if (call.url.includes('/chunks/')) return response({ stored: true });
    if (call.url.endsWith('/complete')) return response({ id: 'upload-1' });
    if (call.url.endsWith('/courses')) return response(course({ ...call.body, id: 'video-1' }));
    return response(snapshot());
  });
  const file = new File([new Uint8Array(600000)], 'video.mp4', { type: 'video/mp4' }), progress = [];
  await h.store.addCourse({ ...course(), id: 'stable-create-id', type: 'video', file, onProgress: value => progress.push(value) });
  assert.deepEqual(h.calls.map(c => c.method), ['POST', 'PUT', 'PUT', 'POST', 'POST']);
  assert.equal(h.calls[1].body.size, 524288); assert.equal(h.calls[2].body.size, 75712);
  assert.equal(h.calls[4].body.uploadId, 'upload-1'); assert.equal(h.calls[4].body.id, 'stable-create-id');
  assert.equal(h.calls[4].body.file, undefined); assert.deepEqual(progress, [87, 99, 100]);
  assert.equal(h.store.getManagedCourse('video-1').type, 'video');
});

test('interrupted video transfer never publishes a course and attempts owned-upload cleanup', async () => {
  const h = harness(call => call.url.endsWith('/uploads') ? response({ id: 'upload-2', chunkSize: 524288 }) : call.method === 'DELETE' ? response({ deleted: true }) : response('分片上传失败', 503));
  await assert.rejects(h.store.addCourse({ ...course(), type: 'video', file: new File(['abc'], 'video.webm') }), /分片上传失败/);
  assert.ok(h.calls.some(c => c.method === 'DELETE')); assert.ok(!h.calls.some(c => c.url.endsWith('/courses')));
  assert.equal(h.store.getAdminStats().total, 0);
});

test('completed upload is reused when metadata is rejected, preserving stable create id', async () => {
  let failCreate = true;
  const h = harness(call => {
    if (call.url.endsWith('/uploads')) return response({ id: 'upload-3', chunkSize: 524288 });
    if (call.url.includes('/chunks/')) return response({ stored: true });
    if (call.url.endsWith('/complete')) return response({ id: 'upload-3' });
    if (call.url.endsWith('/courses')) return failCreate ? response('请检查课程名称', 422) : response(course({ ...call.body }));
    return response(snapshot());
  });
  const draft = { ...course(), id: 'stable-id', type: 'video', file: new File(['video'], 'video.mp4') };
  await assert.rejects(h.store.addCourse(draft), /请检查课程名称/); failCreate = false;
  await h.store.addCourse(draft);
  assert.equal(h.calls.filter(c => c.url.endsWith('/uploads')).length, 1);
  assert.deepEqual(h.calls.filter(c => c.url.endsWith('/courses')).map(c => c.body.id), ['stable-id', 'stable-id']);
});

test('review success is retained even if follow-up list refresh fails', async () => {
  let reviewed = false;
  const pending = course({ id: 'share-1', type: 'share', status: 'pending', reason: '' });
  const h = harness(call => {
    if (call.url.endsWith('/review')) { reviewed = true; return response({ ...pending, status: 'approved', revision: 2 }); }
    return reviewed ? response('临时读取失败', 503) : response(snapshot([], [pending]));
  });
  await h.store.refresh(); await h.store.reviewShare('share-1', { decision: 'approved', reason: '' });
  assert.equal(h.store.listShares()[0].status, 'approved'); assert.equal(h.store.getAdminStats().pending, 0);
  assert.deepEqual(h.calls.find(c => c.method === 'POST').body, { decision: 'approved', reason: '', expected_revision: 1 });
});

test('changed staff identity cannot reuse an existing academy cache to write', async () => {
  const h = harness(() => response(snapshot([course()])));
  await h.store.refresh(); h.user.id = 'other-admin';
  await assert.rejects(h.store.setCourseVisibility('course-1', false), /登录身份已变更/);
  assert.equal(h.calls.length, 1);
});

test('reference course screen renders twenty tag filters and server-authored course labels', async () => {
  const h = harness(() => response(snapshot([course({ title: '<script>bad</script>' })]))); await h.store.refresh();
  const controller = createAcademyController({ academy: h.store, ui: { icon: () => '', refresh() {}, toast() {} } });
  const html = controller.render();
  assert.equal(ACADEMY_TAGS.length, 20); assert.equal((html.match(/data-ac-tag=/g) || []).length, 21);
  assert.ok(html.includes('课程标签')); assert.ok(html.includes('员工分享审核')); assert.ok(html.includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert.ok(!html.includes('AI学院尚未接入')); assert.ok(!html.includes('<th>课程类型</th>'));
});

function eventNode(extra = {}) {
  const listeners = {};
  return { ...extra, addEventListener(name, callback) { listeners[name] = callback; },
    emit(name, event = {}) { return listeners[name]?.(event); } };
}

function controllerUi(store) {
  const state = { modal: null, modalHtml: '' };
  const ui = { icon: () => '', refresh() {}, toast() {}, closeModal() {},
    openModal(html, bind) { state.modalHtml = html; if (state.modal) bind(state.modal); } };
  const controller = createAcademyController({ academy: store, ui });
  const root = (nodes = {}, lists = {}) => ({ querySelector: selector => nodes[selector] || null,
    querySelectorAll: selector => lists[selector] || [] });
  return { controller, state,
    openNew() { const button=eventNode(); controller.bind(root({ '[data-ac-new]': button })); button.emit('click'); },
    openEdit(id) { const button={dataset:{acEdit:id}}; controller.bind(root({}, {'[data-ac-edit]':[button]})); button.onclick(); },
    openReview(id) { const button={dataset:{acReview:id}}; controller.bind(root({}, {'[data-ac-review]':[button]})); button.onclick(); },
    openPreview(id) { const button={dataset:{acPreview:id}}; controller.bind(root({}, {'[data-ac-preview]':[button]})); button.onclick(); },
    form(values = {}, checkedTags = []) {
      const source=eventNode(), file=eventNode();
      const fields=Object.fromEntries(Object.entries(values).map(([key,value])=>[key,{value}]));
      const form=eventNode({ elements:{namedItem:key=>fields[key]},
        querySelector: selector=>({'[data-ac-source]':source,'[data-ac-file]':file})[selector] || null,
        querySelectorAll: ()=>checkedTags.map(value=>({value})) });
      controller.bind(root({'[data-ac-form]':form}));
      return { source, file, submit:()=>form.onsubmit({preventDefault(){}}) };
    },
  };
}

test('new course uses one entry and defaults to the reference external-link source selector', async () => {
  const h=harness(()=>response(snapshot([course({type:'link'}),course({id:'video',type:'video'}),course({id:'share',type:'share'})])));
  await h.store.refresh(); const ui=controllerUi(h.store);
  const list=ui.controller.render();
  assert.match(list, /<th>课程名称<\/th><th>课程来源<\/th><th>课程标签<\/th>/);
  for(const label of ['外部链接','内部视频','员工分享']) assert.ok(list.includes(`<td>${label}</td>`));
  assert.equal((list.match(/data-ac-new(?:\s|>)/g)||[]).length,1);
  assert.doesNotMatch(list,/data-ac-new-link|添加外链课程/);
  ui.openNew(); const form=ui.controller.render();
  assert.match(form, /<option value="link" selected>外部链接<\/option>/);
  assert.ok(form.indexOf('课程来源')<form.indexOf('课程名称'));
  assert.match(form,/课程链接 \*/); assert.doesNotMatch(form,/data-ac-file/);
});

test('changing source preserves draft fields and a video selection never leaks into external-link publication', async () => {
  const h=harness(call=>call.method==='GET'?response(snapshot()):response(course({...call.body})));
  await h.store.refresh(); const ui=controllerUi(h.store); ui.openNew();
  const values={title:'跨来源课程',summary:'说明仍然保留',url:'https://example.com/source',minutes:'25'};
  ui.form(values,['AI 写邮件']).source.emit('change',{target:{value:'video'}});
  let html=ui.controller.render();
  assert.match(html,/<option value="video" selected>内部视频<\/option>/);
  assert.ok(html.includes('value="跨来源课程"')&&html.includes('说明仍然保留')&&html.includes('value="25"'));
  assert.match(html,/value="AI 写邮件" checked/); assert.match(html,/视频文件 \*/);
  const file=new File(['media'],'remembered.mp4',{type:'video/mp4'});
  ui.form(values,['AI 写邮件']).file.emit('change',{target:{files:[file]}});
  ui.form(values,['AI 写邮件']).source.emit('change',{target:{value:'link'}});
  html=ui.controller.render(); assert.ok(html.includes('value="https://example.com/source"'));
  await ui.form(values,['AI 写邮件']).submit();
  const writes=h.calls.filter(call=>call.method!=='GET');
  assert.equal(writes.length,1); assert.equal(writes[0].url,'/api/review-native/academy/courses');
  assert.equal(writes[0].body.type,'link'); assert.equal(writes[0].body.uploadId,undefined);
  assert.deepEqual(writes[0].body.tags,['AI 写邮件']);
});

test('editing existing courses displays an immutable source as on the reference form', async () => {
  const sources=[['link','外部链接'],['video','内部视频'],['share','员工分享']];
  const h=harness(()=>response(snapshot(sources.map(([type])=>course({id:type,type})))));
  await h.store.refresh(); const ui=controllerUi(h.store);
  for(const [type,label] of sources) {
    ui.openEdit(type); const html=ui.controller.render();
    assert.ok(html.includes(`<input value="${label}" readonly aria-label="课程来源">`));
    assert.doesNotMatch(html,/data-ac-source/);
  }
});

test('share approval submits selected tags while rejection does not alter them', async () => {
  const pending=course({id:'share-1',type:'share',status:'pending',tags:['AI 入门']});
  const h=harness(call=>call.url.endsWith('/review')?response({...pending,status:call.body.decision,tags:call.body.tags??pending.tags}):response(snapshot([],[pending])));
  await h.store.refresh();
  await h.store.reviewShare('share-1',{decision:'approved',reason:'',tags:['AI 写邮件','AI 做表格']});
  assert.deepEqual(h.calls.find(call=>call.url.endsWith('/review')).body,
    {decision:'approved',reason:'',expected_revision:1,tags:['AI 写邮件','AI 做表格']});
  await h.store.reviewShare('share-1',{decision:'rejected',reason:'请补充内容',tags:['AI 查资料']});
  assert.equal(h.calls.filter(call=>call.url.endsWith('/review'))[1].body.tags,undefined);
});

test('review tag picker keeps selected tags after failure and shows approved tags read-only', async () => {
  const pending=course({id:'share-1',type:'share',status:'pending',tags:['AI 入门']});
  const h=harness(call=>call.url.endsWith('/review')?response('临时故障',503):response(snapshot([],[pending])));
  await h.store.refresh(); const ui=controllerUi(h.store);
  const checkbox={value:'AI 写邮件',checked:true,disabled:false}, reason={value:'',disabled:false}, error={textContent:''};
  const approve={dataset:{acDecision:'approved'},disabled:false}, reject={dataset:{acDecision:'rejected'},disabled:false};
  const close={disabled:false}, controls=[checkbox,reason,approve,reject,close];
  for(const control of controls) control.dataset??={};
  ui.state.modal={dataset:{},querySelector:selector=>({'[data-ac-modal-close]':close,'[data-ac-reason]':reason,'[data-ac-review-error]':error})[selector],
    querySelectorAll:selector=>selector==='[data-ac-decision]'?[approve,reject]:selector==='input[name="review-tags"]:checked'?[checkbox]:controls};
  ui.openReview('share-1');
  assert.equal((ui.state.modalHtml.match(/name="review-tags"/g)||[]).length,20);
  assert.match(ui.state.modalHtml,/value="AI 入门" checked/);
  const operation=approve.onclick();
  assert.ok(controls.every(control=>control.disabled));
  await operation;
  assert.equal(checkbox.checked,true); assert.ok(controls.every(control=>!control.disabled));
  assert.equal(error.textContent,'临时故障');
  assert.deepEqual(h.calls.find(call=>call.url.endsWith('/review')).body.tags,['AI 写邮件']);
  const readOnly=harness(()=>response(snapshot([],[{...pending,status:'approved'}])));
  await readOnly.store.refresh(); const detail=controllerUi(readOnly.store); detail.openReview('share-1');
  assert.match(detail.state.modalHtml,/<dt>课程标签<\/dt><dd>AI 入门<\/dd>/);
  assert.doesNotMatch(detail.state.modalHtml,/name="review-tags"/);
});

test('course detail shows reference source, field order and empty-tag label', async () => {
  const h=harness(()=>response(snapshot([course({tags:[]})])));
  await h.store.refresh(); const ui=controllerUi(h.store); ui.openPreview('course-1');
  const html=ui.state.modalHtml;
  const fields=['课程名称','课程简介','课程来源','课程标签','发布人 / 分享人','预计时长','状态'];
  const positions=fields.map(label=>html.indexOf(`<dt>${label}</dt>`));
  assert.ok(positions.every((value,index)=>value>=0&&(index===0||value>positions[index-1])));
  assert.match(html,/<dt>课程来源<\/dt><dd>外部链接<\/dd>/);
  assert.match(html,/<dt>课程标签<\/dt><dd>未设置<\/dd>/);
});
