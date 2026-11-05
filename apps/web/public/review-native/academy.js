import { validateExternalUrl } from './academy-store.js?v=20261021-academy-management';
import { ACADEMY_TAGS } from './academy-api.js?v=20261105-sources';

const e = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const date = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('zh-CN'); };
const errorText = error => error?.message || '操作失败，请重试';
const fresh = (type = 'link') => ({ id: crypto.randomUUID(), type, title: '', summary: '', url: '', minutes: 15, tags: [], file: null });
const sourceLabel = type => ({ link: '外部链接', video: '内部视频', share: '员工分享' })[type] || '外部链接';

export function createAcademyController({ academy, ui }) {
  const state = { tab: 'courses', view: 'list', query: '', tag: 'all', reviewStatus: 'pending', editId: null, draft: fresh(), busy: false, error: '', progress: 0 };
  const ic = (name, size = 16) => ui.icon(name, size);
  const admin = () => academy.isAdmin();
  const guard = () => { if (admin()) return true; ui.toast('仅管理员可管理学院内容', 'error'); return false; };
  const visibility = course => course.visibility !== 'unpublished';
  const reviewStatus = share => `<span class="ac-status ac-status-${e(share.status)}">${({ pending: '待审核', approved: '已通过', rejected: '已驳回' })[share.status] || '待审核'}</span>`;
  const courseStatus = course => `<span class="ac-status ac-status-${visibility(course) ? 'published' : 'unpublished'}">${visibility(course) ? '已上架' : '已下架'}</span>${course.type !== 'video' && course.linkState === 'expired' ? ' <span class="ac-status ac-status-expired">链接失效</span>' : ''}`;
  const tags = () => academy.getTags?.() || ACADEMY_TAGS;
  const managed = () => academy.listManagedCourses({ query: state.query, tag: state.tag });
  const shares = () => academy.listShares({ mine: false }).filter(share => share.status === state.reviewStatus && (!state.query.trim() || [share.title, share.summary, share.author?.name].some(text => String(text || '').toLowerCase().includes(state.query.trim().toLowerCase()))));

  function changeTab(tab) { if (state.busy) return; state.tab = tab; state.view = 'list'; state.query = ''; ui.refresh(); }
  function formFor(course = null, type = 'link') {
    if (!guard() || state.busy) return;
    state.editId = course?.id || null;
    state.draft = course ? { type: course.type, title: course.title, summary: course.summary, url: course.url || '', minutes: course.minutes, tags: [...(course.tags || [])], expected_revision: course.revision, file: null, videoName: course.videoName } : fresh(type);
    state.error = ''; state.view = 'form'; ui.refresh();
  }

  function search() {
    return `<label class="ac-search">${ic('search')}<input type="search" data-ac-search value="${e(state.query)}" placeholder="搜索课程名称或发布人" aria-label="搜索学院内容"></label>`;
  }

  function courseTable() {
    const list = managed();
    if (!list.length) return `<div class="ac-empty"><strong>${academy.getAdminStats().total ? '没有找到相关课程' : '暂无课程'}</strong><p>${academy.getAdminStats().total ? '试试其他标签或搜索词。' : '发布课程后，学员即可在 AI 学院查看和学习。'}</p></div>`;
    return `<div class="ac-table-wrap"><table class="ac-table"><thead><tr><th>课程名称</th><th>课程来源</th><th>课程标签</th><th>发布人 / 分享人</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${list.map(course => `<tr><td><button type="button" class="ac-row-title" data-ac-preview="${e(course.id)}">${e(course.title)}</button><span class="ac-row-summary">${e(course.summary)}</span></td><td>${sourceLabel(course.type)}</td><td><div class="ac-course-tags">${course.tags?.length ? course.tags.map(tag=>`<span class="ac-badge">${e(tag)}</span>`).join('') : '—'}</div></td><td>${e(course.author?.name || '管理员')}</td><td>${courseStatus(course)}</td><td>${date(course.updatedAt || course.createdAt)}</td><td><div class="ac-row-actions"><button type="button" class="ac-btn ac-btn-ghost" data-ac-preview="${e(course.id)}">查看</button><button type="button" class="ac-btn ac-btn-ghost" data-ac-edit="${e(course.id)}">编辑</button><button type="button" class="ac-btn ac-btn-ghost" data-ac-visibility="${e(course.id)}">${visibility(course) ? '下架' : '上架'}</button></div></td></tr>`).join('')}</tbody></table></div>`;
  }

  function reviewTable() {
    const list = shares();
    if (!list.length) return '<div class="ac-empty"><strong>暂无相关分享</strong></div>';
    return `<div class="ac-table-wrap"><table class="ac-table"><thead><tr><th>分享内容</th><th>分享人</th><th>提交时间</th><th>审核状态</th><th>操作</th></tr></thead><tbody>${list.map(share => `<tr><td><button type="button" class="ac-row-title" data-ac-review="${e(share.id)}">${e(share.title)}</button><span class="ac-row-summary">${e(share.summary)}</span>${share.status === 'rejected' ? `<span class="ac-inline-error">驳回原因：${e(share.reason)}</span>` : ''}</td><td>${e(share.author?.name || '未记录')}</td><td>${date(share.createdAt)}</td><td>${reviewStatus(share)}</td><td><button type="button" class="ac-btn ac-btn-ghost" data-ac-review="${e(share.id)}">${share.status === 'pending' ? '审核' : '查看详情'}</button></td></tr>`).join('')}</tbody></table></div>`;
  }

  function renderList() {
    const stats = academy.getAdminStats();
    const allShares = academy.listShares({ mine: false });
    const tagFilters = `<div class="ac-tag-filters" role="group" aria-label="课程标签">${['全部标签', ...tags()].map((tag,index)=>{const value=index?tag:'all';return `<button type="button" class="ac-tag-filter ${state.tag===value?'active':''}" data-ac-tag="${e(value)}" aria-pressed="${state.tag===value}">${e(tag)}</button>`;}).join('')}</div>`;
    return `<header class="ac-heading"><h1>AI学院</h1><div class="ac-actions"><button type="button" class="ac-btn ac-btn-primary" data-ac-new>${ic('plus')} 新增课程</button></div></header><div class="ac-admin-tabs"><button type="button" class="${state.tab==='courses'?'active':''}" data-ac-tab="courses">课程管理</button><button type="button" class="${state.tab==='review'?'active':''}" data-ac-tab="review">员工分享审核 ${stats.pending?`<span class="ac-badge">${stats.pending}</span>`:''}</button></div>${academy.error?`<div class="ac-notice ac-notice-warning" role="alert">${e(academy.error)}<button type="button" class="ac-btn ac-btn-ghost" data-ac-reload>重新加载</button></div>`:''}${state.tab==='courses'?`<div class="ac-admin-stats">${[['全部课程',stats.total],['已上架',stats.published],['已下架',stats.unpublished],['待审核分享',stats.pending]].map(([label,value])=>`<div class="ac-stat"><span>${label}</span><strong>${Number(value)||0}</strong></div>`).join('')}</div>${tagFilters}<div class="ac-toolbar">${search()}</div><div data-ac-results>${courseTable()}</div>`:`<div class="ac-toolbar"><div class="ac-type-tabs" aria-label="审核状态">${[['pending','待审核'],['approved','已通过'],['rejected','已驳回']].map(([id,label])=>`<button type="button" class="ac-tab ${state.reviewStatus===id?'active':''}" data-ac-review-status="${id}" aria-pressed="${state.reviewStatus===id}">${label} ${allShares.filter(item=>item.status===id).length}</button>`).join('')}</div>${search()}</div><div data-ac-results>${reviewTable()}</div>`}`;
  }

  function renderForm() {
    const d=state.draft;
    const sourceField = `<label class="ac-field"><span>课程来源</span>${state.editId ? `<input value="${sourceLabel(d.type)}" readonly aria-label="课程来源">` : `<select name="type" data-ac-source aria-label="课程来源"><option value="link" ${d.type==='link'?'selected':''}>外部链接</option><option value="video" ${d.type==='video'?'selected':''}>内部视频</option></select>`}</label>`;
    const fileField=d.type==='video'?`<div class="ac-field"><span>视频文件 ${state.editId?'':'*'}</span><label class="ac-upload">${ic('upload',26)}<strong class="ac-upload-name">${e(d.file?.name||d.videoName||'选择本地视频')}</strong><span>${d.file?(d.file.size/1024/1024).toFixed(1)+' MB':state.editId?'重新选择可替换视频':'上传 MP4、WebM 等视频文件'}</span><input type="file" accept="video/mp4,video/webm,video/ogg,video/quicktime,.mp4,.m4v,.webm,.ogv,.ogg,.mov" data-ac-file aria-label="选择课程视频"></label><small>支持最大 500 MB 的视频，发布后学员可在站内观看。</small></div>`:`<label class="ac-field"><span>课程链接 *</span><input name="url" type="url" value="${e(d.url)}" placeholder="https://" required><small>支持飞书文档、网页及外部视频链接。</small></label>`;
    return `<header class="ac-heading"><h1>${state.editId?'编辑课程':'新增课程'}</h1><button type="button" class="ac-btn ac-btn-secondary" data-ac-cancel ${state.busy?'disabled':''}>返回课程管理</button></header><section class="ac-form-card"><form class="ac-form" data-ac-form novalidate><fieldset class="ac-form-fields" ${state.busy?'disabled':''}>${sourceField}<label class="ac-field"><span>课程名称 *</span><input name="title" maxlength="100" value="${e(d.title)}" placeholder="填写课程名称" required></label><label class="ac-field"><span>课程简介 *</span><textarea name="summary" rows="4" maxlength="1200" placeholder="填写课程内容与适用场景" required>${e(d.summary)}</textarea></label>${fileField}<fieldset class="ac-field ac-tag-options"><legend>课程标签（可多选）</legend><div>${tags().map(tag=>`<label><input type="checkbox" name="tags" value="${e(tag)}" ${d.tags.includes(tag)?'checked':''}><span>${e(tag)}</span></label>`).join('')}</div></fieldset><label class="ac-field"><span>预计时长（分钟）</span><input name="minutes" type="number" min="1" max="1440" value="${e(d.minutes)}"></label></fieldset><p class="ac-inline-error" role="alert">${e(state.error)}</p>${state.busy?`<div class="ac-upload-progress" role="status" aria-live="polite"><progress max="100" value="${state.progress}" data-ac-progress></progress><span data-ac-progress-label>${d.type==='video'&&d.file?'正在上传视频 '+state.progress+'%':'正在保存课程…'}</span></div>`:''}<div class="ac-form-footer"><button type="button" class="ac-btn ac-btn-secondary" data-ac-cancel ${state.busy?'disabled':''}>取消</button><button type="submit" class="ac-btn ac-btn-primary" ${state.busy?'disabled':''}>${state.busy?'保存中…':state.editId?'保存修改':'发布课程'}</button></div></form></section>`;
  }

  function render() {
    if (!admin()) return '<div class="academy-page"><div class="ac-empty"><strong>仅管理员可管理 AI学院</strong></div></div>';
    if (!academy.loaded) return `<div class="academy-page"><div class="ac-empty" role="status"><strong>${academy.error ? e(academy.error) : '正在读取学院课程…'}</strong>${academy.error ? '<button type="button" class="ac-btn ac-btn-secondary" data-ac-reload>重新加载</button>' : ''}</div></div>`;
    return `<div class="academy-page">${state.view === 'form' ? renderForm() : renderList()}</div>`;
  }

  function capture(form) {
    for (const key of ['title','summary','url','minutes']) { const field = form.elements.namedItem(key); if (field) state.draft[key] = field.value; }
    state.draft.tags = [...form.querySelectorAll('input[name="tags"]:checked')].map(input => input.value);
  }

  function previewCourse(id) {
    if (!guard()) return;
    const course = academy.getManagedCourse(id);
    if (!course) { ui.toast('未找到课程','error'); return; }
    const link = validateExternalUrl(course.url);
    ui.openModal(`<div class="ac-modal-heading"><h2>课程详情</h2></div><div class="ac-modal-body"><dl class="ac-detail-list">${[['课程名称',course.title],['课程简介',course.summary],['课程来源',sourceLabel(course.type)],['课程标签',(course.tags||[]).join('、')||'未设置'],['发布人 / 分享人',course.author?.name || '管理员'],['预计时长',`${course.minutes} 分钟`],['状态',visibility(course)?'已上架':'已下架']].map(([key,value])=>`<div><dt>${e(key)}</dt><dd>${e(value)}</dd></div>`).join('')}</dl>${course.demo?'<div class="ac-notice">演示内容，外链仅用于跳转示例。</div>':''}${course.type === 'video' ? `<div class="ac-media-preview" data-ac-media><p class="ac-muted">正在读取视频文件…</p></div>` : `<div class="ac-notice ${course.linkState==='expired'?'ac-notice-warning':''}">${course.linkState==='expired'?'链接已标记失效，可编辑课程更新链接。':e(course.url)}</div>${link.valid ? `<a class="ac-btn ac-btn-secondary" href="${e(link.url)}" target="_blank" rel="noopener noreferrer">检查原链接 ${ic('external')}</a>`:''}`}</div><div class="ac-modal-footer"><button type="button" class="ac-btn ac-btn-secondary" data-ac-modal-close>关闭</button><button type="button" class="ac-btn ac-btn-primary" data-ac-modal-edit>编辑课程</button></div>`,modal=>{
      modal.querySelector('[data-ac-modal-close]').onclick=ui.closeModal;
      modal.querySelector('[data-ac-modal-edit]').onclick=()=>{ui.closeModal();formFor(course);};
      if(course.type==='video') {
        const media=modal.querySelector('[data-ac-media]');
        Promise.resolve().then(()=>academy.getVideoUrl(course.id)).then(url=>{
          if(!media.isConnected)return;
          media.innerHTML=url?`<video controls preload="metadata" src="${e(url)}" aria-label="课程视频核验"></video><p class="ac-inline-error" data-ac-video-error role="alert"></p>`:'<p class="ac-muted">尚无视频文件，可在编辑课程中上传。</p>';
          const video=media.querySelector('video');
          if(video){video.onerror=()=>{media.querySelector('[data-ac-video-error]').textContent='视频暂时无法播放，请检查文件编码或刷新后重试。';};modal.addEventListener('review-close',()=>video.pause(),{once:true});}
        }).catch(error=>{if(media.isConnected)media.innerHTML=`<p class="ac-inline-error">${e(errorText(error))}</p>`;});
      }
    });
  }

  function reviewShare(id) {
    if(!guard())return;
    const share=academy.listShares({mine:false}).find(item=>item.id===id);
    if(!share)return;
    const link=validateExternalUrl(share.url);
    const pending=share.status==='pending';
    const tagField=pending?`<fieldset class="ac-field ac-tag-options"><legend>课程标签（可多选）</legend><div>${tags().map(tag=>`<label><input type="checkbox" name="review-tags" value="${e(tag)}" ${(share.tags||[]).includes(tag)?'checked':''}><span>${e(tag)}</span></label>`).join('')}</div></fieldset>`:`<dl class="ac-detail-list"><div><dt>课程标签</dt><dd>${e((share.tags||[]).join('、')||'—')}</dd></div></dl>`;
    ui.openModal(`<div class="ac-modal-heading"><h2>${pending?'审核员工分享':'分享详情'}</h2></div><div class="ac-modal-body"><dl class="ac-detail-list">${[['课程名称',share.title],['课程简介',share.summary],['分享人',share.author?.name||'未记录'],['提交时间',date(share.createdAt)],['课程链接',share.url]].map(([key,value])=>`<div><dt>${e(key)}</dt><dd>${e(value)}</dd></div>`).join('')}</dl>${share.demo?'<div class="ac-notice">演示分享，链接仅用于跳转示例。</div>':''}${link.valid?`<a class="ac-btn ac-btn-secondary" href="${e(link.url)}" target="_blank" rel="noopener noreferrer">检查分享链接 ${ic('external')}</a>`:'<div class="ac-notice ac-notice-warning">链接无效，无法批准发布。</div>'}${tagField}${pending?'<label class="ac-field"><span>驳回理由（驳回时必填）</span><textarea rows="3" maxlength="1000" data-ac-reason placeholder="填写需要修改的内容"></textarea></label>':`<p>${reviewStatus(share)}</p>${share.status==='rejected'?`<div class="ac-notice ac-notice-warning">驳回理由：${e(share.reason)}</div>`:''}`}<p class="ac-inline-error" data-ac-review-error role="alert"></p></div><div class="ac-modal-footer"><button type="button" class="ac-btn ac-btn-secondary" data-ac-modal-close>关闭</button>${pending?`<button type="button" class="ac-btn ac-btn-danger" data-ac-decision="rejected">驳回</button><button type="button" class="ac-btn ac-btn-primary" data-ac-decision="approved" ${link.valid?'':'disabled'}>通过并上架</button>`:''}</div>`,modal=>{
      modal.querySelector('[data-ac-modal-close]').onclick=ui.closeModal;
      modal.querySelectorAll('[data-ac-decision]').forEach(button=>button.onclick=async()=>{
        if(!guard()||modal.dataset.operationPending==='true')return;
        const reason=modal.querySelector('[data-ac-reason]').value.trim();
        const decision=button.dataset.acDecision;
        const selectedTags=[...modal.querySelectorAll('input[name="review-tags"]:checked')].map(input=>input.value);
        const error=modal.querySelector('[data-ac-review-error]');
        if(decision==='rejected'&&!reason){error.textContent='请填写驳回理由';modal.querySelector('[data-ac-reason]').focus();return;}
        modal.dataset.operationPending='true';modal.querySelectorAll('button,textarea,input').forEach(item=>item.disabled=true);
        try{await academy.reviewShare(id,{decision,reason,...(decision==='approved'?{tags:selectedTags}:{})});modal.dataset.operationPending='false';ui.closeModal();ui.toast(decision==='approved'?'分享已通过并上架':'分享已驳回');ui.refresh();}
        catch(err){modal.dataset.operationPending='false';error.textContent=errorText(err);modal.querySelectorAll('button,textarea,input').forEach(item=>item.disabled=item.dataset.acDecision==='approved'&&!link.valid);}
      });
    });
  }

  function bindRows(root) {
    root.querySelectorAll('[data-ac-preview]').forEach(button=>button.onclick=()=>previewCourse(button.dataset.acPreview));
    root.querySelectorAll('[data-ac-edit]').forEach(button=>button.onclick=()=>formFor(academy.getManagedCourse(button.dataset.acEdit)));
    root.querySelectorAll('[data-ac-review]').forEach(button=>button.onclick=()=>reviewShare(button.dataset.acReview));
    root.querySelectorAll('[data-ac-visibility]').forEach(button=>button.onclick=async()=>{
      if(!guard())return;
      const course=academy.getManagedCourse(button.dataset.acVisibility);
      if(!course)return;
      button.disabled=true;
      try{await academy.setCourseVisibility(course.id,!visibility(course));ui.toast(visibility(course)?'课程已下架':'课程已上架');ui.refresh();}
      catch(error){ui.toast(errorText(error),'error');button.disabled=false;}
    });
  }

  function bind(root) {
    if(!admin())return;
    const page=root.querySelector('.academy-page')||root;
    page.querySelector('[data-ac-reload]')?.addEventListener('click',activate);
    if (!academy.loaded) { if (!academy.error && !academy.loading) void activate(); return; }
    page.querySelector('[data-ac-new]')?.addEventListener('click',()=>formFor());
    page.querySelectorAll('[data-ac-tab]').forEach(button=>button.onclick=()=>changeTab(button.dataset.acTab));
    page.querySelectorAll('[data-ac-tag]').forEach(button=>button.onclick=()=>{state.tag=button.dataset.acTag;ui.refresh();});
    page.querySelectorAll('[data-ac-review-status]').forEach(button=>button.onclick=()=>{state.reviewStatus=button.dataset.acReviewStatus;ui.refresh();});
    page.querySelector('[data-ac-search]')?.addEventListener('input',event=>{state.query=event.target.value;const results=page.querySelector('[data-ac-results]');results.innerHTML=state.tab==='courses'?courseTable():reviewTable();bindRows(results);});
    page.querySelectorAll('[data-ac-cancel]').forEach(button=>button.onclick=()=>{if(!state.busy)changeTab('courses');});
    bindRows(page);
    const form=page.querySelector('[data-ac-form]');
    if(!form)return;
    form.addEventListener('input',()=>capture(form));
    form.querySelector('[data-ac-source]')?.addEventListener('change',event=>{
      if(state.busy||state.editId)return;
      capture(form);
      state.draft.type=event.target.value==='video'?'video':'link';
      state.error='';
      ui.refresh();
    });
    form.querySelector('[data-ac-file]')?.addEventListener('change',event=>{capture(form);state.draft.file=event.target.files?.[0]||state.draft.file;ui.refresh();});
    form.onsubmit=async event=>{
      event.preventDefault();if(state.busy||!guard())return;capture(form);
      const d=state.draft;
      state.error='';
      if(!d.title.trim()||!d.summary.trim())state.error='请填写课程名称和简介';
      else if(!Number.isFinite(Number(d.minutes))||Number(d.minutes)<1||Number(d.minutes)>1440)state.error='预计时长需为 1～1440 分钟';
      else if(d.type!=='video'&&!validateExternalUrl(d.url).valid)state.error=validateExternalUrl(d.url).message;
      else if(d.type==='video'&&!state.editId&&!d.file)state.error='请选择视频文件';
      else if(d.type==='video'&&d.file?.size>524288000)state.error='视频不能超过 500 MB';
      if(state.error){ui.refresh();return;}
      state.busy=true;state.progress=0;ui.refresh();
      try{
        const payload={...d,file:d.type==='video'?d.file:null,minutes:Number(d.minutes),onProgress(value){
          state.progress=value;
          const progress=document.querySelector('[data-ac-progress]'),label=document.querySelector('[data-ac-progress-label]');
          if(progress)progress.value=value;
          if(label)label.textContent=value<100?`正在上传视频 ${value}%`:'视频上传完成，正在保存课程…';
        }};
        if(state.editId)await academy.updateCourse(state.editId,payload);else await academy.addCourse(payload);
        const edited=Boolean(state.editId);state.busy=false;state.draft=fresh();state.editId=null;state.tag='all';changeTab('courses');ui.toast(edited?'课程已更新':'课程已发布，学员可在 AI 学院查看');
      }catch(error){state.busy=false;state.error=errorText(error);ui.refresh();}
    };
  }

  function reset() { if(state.busy)return;state.tab='courses';state.view='list';state.query='';state.tag='all';state.reviewStatus='pending';state.editId=null;state.draft=fresh();state.error=''; }
  async function activate() { if(!admin()||academy.loading)return;try{await academy.refresh();}catch{}if(state.view==='list')ui.refresh(); }
  function canRefresh() { return state.view==='list'&&!state.busy; }
  function deactivate() { document.querySelectorAll('.ac-media-preview video').forEach(video=>video.pause()); }
  return {render,bind,reset,deactivate,activate,canRefresh};
}
