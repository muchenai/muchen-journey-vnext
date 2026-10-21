import { BADGES, DIFFICULTY_PRESETS, REVIEW_CAMPS, getReviewCamp, getSubmissionStatus, applyDifficultyPreset, escapeHtml as e, icon, rewardBreakdown, validateTask } from './core.js?v=20261021-review-decision';
import { ApiStore, newDraft, createJourneyService } from './native-api.js';
import { createSandboxController } from './sandbox.js?v=20261021-brand-npc';
import { renderReview, bindReview, openSubmission } from './review.js?v=20261021-review-decision';
import { renderLibrary, bindLibrary, openCertification } from './library.js?v=20261021-admin-certification';
import { isInviteLoggedIn, getCurrentInviteUser, clearInviteSession, renderInviteLogin, bindInviteLogin, onInviteSessionChange } from './native-api.js';
import { createAcademyStore } from './native-api.js';
import { createAcademyController } from './academy.js?v=20261021-academy-management';

const store = await ApiStore.create().catch(error => { document.querySelector('#app').innerHTML = `<div class="card empty-state"><strong>${e(error.message)}</strong><a href="/review/login">重新登录</a></div>`; throw error; });
const service = createJourneyService({ store, getCurrentUser: getCurrentInviteUser });
let page = location.hash === '#academy' ? 'academy' : 'publish';
let reviewCamp = 'novice';
try { const savedCamp = localStorage.getItem('journey_admin_review_camp'); if (REVIEW_CAMPS.some(camp => camp.id === savedCamp)) reviewCamp = savedCamp; } catch {}
const $ = (s, root = document) => root.querySelector(s);
const ui = { toast, refresh: render, openModal, closeModal, navigate, editTask, icon, service, get currentUser() { return getCurrentInviteUser(); }, get reviewCamp() { return reviewCamp; }, get isSuperAdmin() { return getCurrentInviteUser()?.accessRole === 'super_admin'; }, newTask: () => { navigate('publish'); $('#new-task').click(); } };
const academyStore = createAcademyStore({ getCurrentUser: getCurrentInviteUser });
const academy = createAcademyController({ academy: academyStore, ui });
const badgeList = () => Array.isArray(BADGES) ? BADGES : Object.values(BADGES);
const badgeName = id => badgeList().find(b => b.id === id)?.name || id;
const format = n => Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 3 });
const sandbox = createSandboxController({ store, service, openModal, toast, onChange: () => updateAside() });

function themeToggleContent() {
  const dark = document.documentElement.dataset.theme === 'dark';
  const symbol = dark
    ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>'
    : '<path d="M20.8 13a8.8 8.8 0 0 1-9.8-9.8A9 9 0 1 0 20.8 13Z"/>';
  return `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${symbol}</svg><span>${dark ? '浅色' : '深色'}</span>`;
}
function applyTheme(theme, persist = false) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#151617' : '#f7f7f7';
  if (persist) { try { localStorage.setItem('journey_admin_theme', theme); } catch {} }
  const toggle = $('#theme-toggle');
  if (toggle) {
    toggle.innerHTML = themeToggleContent();
    toggle.setAttribute('aria-label', theme === 'dark' ? '切换为浅色模式' : '切换为深色模式');
    toggle.title = toggle.getAttribute('aria-label');
  }
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', event => {
  let saved;
  try { saved = localStorage.getItem('journey_admin_theme'); } catch {}
  if (saved !== 'light' && saved !== 'dark') applyTheme(event.matches ? 'dark' : 'light');
});

function toast(message, type = 'success') {
  const node = document.createElement('div');
  node.className = `toast ${type}`;
  node.innerHTML = `${icon(type === 'error' ? 'alert' : 'checkCircle', 18)}<span>${e(message)}</span>`;
  $('#toast-root').append(node);
  setTimeout(() => node.remove(), 4000);
}

let returnFocus;
function openModal(html, onReady) {
  returnFocus = document.activeElement;
  $('#modal-root').innerHTML = `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-label="详情"><button class="modal-close icon-btn" aria-label="关闭">${icon('close')}</button><div class="modal-content">${html}</div></section></div>`;
  document.body.classList.add('modal-open');
  $('.modal-close').onclick = closeModal;
  $('.modal-backdrop').onclick = event => { if (event.target.classList.contains('modal-backdrop')) closeModal(); };
  onReady?.($('.modal'));
  $('.modal').querySelector('input,button,textarea,select')?.focus();
}
function closeModal() {
  if ($('.modal[data-operation-pending="true"]')) return;
  $('#modal-root').innerHTML = '';
  document.body.classList.remove('modal-open');
  returnFocus?.focus?.();
}
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeModal();
  if (event.key === 'Tab' && $('.modal')) {
    const controls = [...$('.modal').querySelectorAll('button,input,select,textarea,a[href]')].filter(el => !el.disabled && el.offsetParent !== null);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
});
function navigate(next) { if (page === 'academy' && next !== 'academy') academy.deactivate(); page = next; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
function editTask(task) { if (!store.operatorId) { toast('当前账号没有任务配置权限。','error'); return; } store.data.draft = structuredClone(task); if (task.authorId && task.authorId !== store.operatorId) { store.data.draft.id = crypto.randomUUID(); store.data.draft.revision = 0; store.data.draft.authorId = store.operatorId; } store.data.draft.status = 'draft'; store.save(); navigate('publish'); }
function saveDraft() {
  Object.assign(store.data.draft, applyDifficultyPreset(store.data.draft));
  store.data.draft.updatedAt = new Date().toISOString();
  updateAside();
  try { store.save(); const saved = $('#saved-status'); if(saved) saved.innerHTML = `${icon('checkCircle',14)} 草稿已保存`; return true; }
  catch(error) { const saved=$('#saved-status');if(saved)saved.textContent='尚未保存，请减少附件后重试';toast(error.message||'保存失败，请重试','error');return false; }
}

function shell(content) {
  const currentUser = getCurrentInviteUser();
  const pendingInCamp = camp => store.data.submissions.filter(s => { const task=store.getTask(s.taskId)||{}; return !s.supersededBy&&getReviewCamp(s,task)===camp&&getSubmissionStatus(s,task)==='pending'; }).length;
  const pending = REVIEW_CAMPS.reduce((sum,camp)=>sum+pendingInCamp(camp.id),0);
  const labels = {publish:'发布任务配置',review:`${REVIEW_CAMPS.find(camp=>camp.id===reviewCamp).label}审核`,library:'任务库',academy:'AI学院'};
  const navigation = [
    { id: 'publish', symbol: 'grid', label: '发布任务配置' },
    ...REVIEW_CAMPS.map(camp => ({ id: 'review', camp: camp.id, symbol: 'checkCircle', label: `${camp.label}审核` })),
    { id: 'library', symbol: 'library', label: '任务库' },
    { id: 'academy', symbol: 'book', label: 'AI学院' },
  ].map(item => {
    const active = page === item.id && (!item.camp || reviewCamp === item.camp);
    const count = item.camp ? pendingInCamp(item.camp) : 0;
    return `<div class="nav-group"><button type="button" class="nav-item ${item.camp ? 'review-camp-primary ' : ''}${active ? 'active' : ''}" aria-label="${item.label}" title="${item.label}" ${item.camp ? `data-review-camp="${item.camp}"` : `data-page="${item.id}"`} ${active ? 'aria-current="page"' : ''}>${icon(item.symbol,19)}<span>${item.label}</span>${count ? `<span class="nav-count">${count}</span>` : ''}</button></div>`;
  }).join('');
  return `<header class="topbar"><a href="#" class="brand" aria-label="JOURNEY首页"><img src="./journey-logo-119.svg" alt="" width="34" height="34"><span class="brand-wordmark">JOURNEY <span class="brand-sub">管理系统</span></span></a><div class="topbar-right"><button id="theme-toggle" class="theme-toggle" type="button" aria-label="${document.documentElement.dataset.theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'}" title="${document.documentElement.dataset.theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'}">${themeToggleContent()}</button>${ui.isSuperAdmin?`<button id="cert-btn" class="cert-btn">${icon('shield',16)} 认证</button>`:''}<button id="notification-btn" class="icon-btn notification-btn" aria-label="审核通知">${icon('bell',19)}${pending?'<i></i>':''}</button><div class="header-user"><div class="avatar avatar-small">${e((currentUser?.name || '成').slice(0,1))}</div><span>${e(currentUser?.name || '学院成员')}</span></div><button id="logout-btn" class="logout-btn" type="button">退出登录</button></div></header>
  <aside class="sidebar"><nav aria-label="主导航">${navigation}</nav><div class="sidebar-bottom"><button class="guide-entry" id="guide-btn" type="button">${icon('book',20)}<span>使用指南</span></button></div></aside>
  <div class="app-main"><main class="main-content" aria-label="${labels[page]}">${content}</main></div>`;
}

function render() {
  const loggedIn = isInviteLoggedIn();
  document.body.classList.toggle('login-screen', !loggedIn);
  if (!loggedIn) {
    $('#modal-root').innerHTML = '';
    $('#toast-root').innerHTML = '';
    document.body.classList.remove('modal-open');
    $('#app').innerHTML = renderInviteLogin(themeToggleContent(), document.documentElement.dataset.theme === 'dark');
    bindInviteLogin({
      onLogin: () => { page = location.hash === '#academy' ? 'academy' : 'publish'; render(); window.scrollTo({ top: 0 }); },
      onThemeToggle: () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true)
    });
    return;
  }
  let content;
  try { content = page === 'academy' ? academy.render() : page === 'review' ? renderReview(store,ui) : page === 'library' ? renderLibrary(store,ui) : renderEditor(); }
  catch (err) { console.error(err); content = `<div class="card empty-state">页面暂时无法显示，请刷新重试。</div>`; }
  $('#app').innerHTML = shell(content);
  document.documentElement.style.setProperty('--editor-header-height','0px');
  document.querySelectorAll('[data-page]').forEach(btn => btn.onclick = () => navigate(btn.dataset.page));
  document.querySelectorAll('[data-review-camp]').forEach(btn => btn.onclick = () => { reviewCamp=btn.dataset.reviewCamp; try { localStorage.setItem('journey_admin_review_camp',reviewCamp); } catch {} navigate('review'); });
  $('.brand').onclick = event => { event.preventDefault(); navigate('publish'); };
  $('#cert-btn')?.addEventListener('click', () => { if (ui.isSuperAdmin) openCertification(store,ui); });
  $('#theme-toggle').onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true);
  $('#notification-btn').onclick = () => { const submission=store.data.submissions.find(s=>!s.supersededBy&&getSubmissionStatus(s,store.getTask(s.taskId)||{})==='pending'); if(submission)reviewCamp=getReviewCamp(submission,store.getTask(submission.taskId)||{}); navigate('review'); };
  $('#logout-btn').onclick = async () => { try { await clearInviteSession(); academy.reset(); } catch (error) { toast(error.message,'error'); } };
  $('#guide-btn').onclick = () => openModal(`<div class="modal-heading"><h2>使用指南</h2></div><div class="guide-list">${[['填写基础信息','填写任务标题与简述，选择难度及 1～2 个徽章。'],['添加学习材料','添加文档链接、图片或文件。'],['选择审核方式与评分标准','有固定答案选择 AI 自测并填写评分标准；无固定答案选择人工审核。'],['查看右侧预览','AI 自测任务可选用沙盒试测，确认后直接发布。']].map(([title,description])=>`<div><section><strong>${title}</strong><p>${description}</p></section></div>`).join('')}</div><div class="notice">任务、提交和审核记录来自本地服务。编辑中的草稿保存在当前账号的浏览器中；AI 自查仅供参考，最终由审核人确认。</div>`);
  if (page === 'publish') bindEditor();
  else if (page === 'academy') academy.bind($('.main-content'));
  else if (page === 'review') bindReview($('.main-content'),store,ui);
  else bindLibrary($('.main-content'),store,ui);
}

function renderEditor() {
  return `<div class="editor-layout"><div class="editor-primary" id="editor-primary">${renderBasics()}${renderMaterials()}${renderScoring()}</div><aside class="editor-aside" id="editor-aside">${renderAside()}</aside></div>
    <div class="editor-actionbar"><div id="saved-status">${icon('checkCircle',14)} 草稿已保存 <span class="muted">· 仅当前浏览器</span></div><div class="action-buttons"><button class="btn btn-plain" id="save-draft">保存草稿</button>${store.data.draft.reviewMode==='ai'?`<button class="btn btn-secondary" id="sandbox-test">${icon('sparkles',16)} 沙盒试测</button>`:''}<button class="btn btn-primary" id="publish-task">${icon('send',16)} 发布任务</button></div></div>`;
}
function cardHeader(title,right='') {
  return `<div class="card-header"><div class="section-title"><h2>${title}</h2></div>${right}</div>`;
}
function renderBasics() {
  const d = store.data.draft;
  return `<section class="card" id="task-basics" tabindex="-1" aria-label="基础信息">${cardHeader('基础信息',`<div class="basics-header-actions"><span class="required-note"><i>*</i> 为必填项</span><button class="btn btn-secondary btn-sm" id="new-task">${icon('plus',15)} 新建任务</button></div>`)}<div class="card-body form-grid">
    <label class="form-field full"><span class="field-label">任务标题 <i>*</i></span><div class="input-counter"><input data-field="title" value="${e(d.title)}" maxlength="60" placeholder="给任务起一个清晰、具体的名字"><span id="title-counter">${d.title.length}/60</span></div></label>
    <label class="form-field full"><span class="field-label">任务简述 <i>*</i></span><textarea data-field="summary" rows="3" maxlength="400" placeholder="简要介绍任务背景与学习目标">${e(d.summary)}</textarea><span class="field-hint">让学员快速了解：要做什么，以及为什么做。</span></label>
    <fieldset class="form-field full camp-field"><legend class="field-label">所属营地</legend><div class="camp-options">${REVIEW_CAMPS.map(camp=>`<label class="camp-option"><input type="radio" name="task-camp" data-field="camp" value="${camp.id}" ${getReviewCamp({},d)===camp.id?'checked':''}><span>${camp.label}</span></label>`).join('')}</div></fieldset>
    <label class="form-field"><span class="field-label">任务方向</span><select data-field="domain">${['产品开发','数据交付','技术开发','PMO','AI评测','质量检测','项目管理','AI 能力'].map(x=>`<option ${x===d.domain?'selected':''}>${x}</option>`).join('')}</select></label>
    <label class="form-field"><span class="field-label">难度 <i>*</i></span><select data-field="difficulty">${DIFFICULTY_PRESETS.map(({name})=>`<option ${name===d.difficulty?'selected':''}>${name}</option>`).join('')}</select></label>
  </div></section>
  <section class="card" id="task-badges" tabindex="-1" aria-label="关联徽章">${cardHeader('关联徽章',`<span class="subtle-label">已选 ${d.badges.length}/2</span>`)}<div class="card-body"><div class="badge-selector">${badgeList().map(b=>{const chosen=d.badges.some(x=>x.id===b.id);return `<button class="badge-option ${chosen?'selected':''}" data-badge="${b.id}" aria-pressed="${chosen}" ${!chosen&&d.badges.length>=2?'disabled':''}>${icon('award',16)}<span>${e(b.name)}</span>${chosen?icon('check',14):''}</button>`}).join('')}</div>${renderRatio()}</div></section>`;
}
function renderRatio() {
  const d=store.data.draft;
  if (!d.badges.length) return `<div class="notice">请选择至少一个徽章。</div>`;
  return `<div class="ratio-section"><div class="ratio-heading"><span>徽章占比</span><span class="muted">总占比 100%</span></div><div class="ratio-labels">${d.badges.map((b,i)=>`<div><i class="color-dot color-${i}"></i><span>${e(badgeName(b.id))}</span><strong id="ratio-weight-${i}">${b.weight}%</strong></div>`).join('')}</div>${d.badges.length===2?`<input class="ratio-slider" aria-label="${e(badgeName(d.badges[0].id))}占比" id="ratio-slider" type="range" min="1" max="99" value="${d.badges[0].weight}" style="--ratio:${d.badges[0].weight}%">`:'<div class="single-ratio"><span></span></div>'}</div>`;
}
function renderMaterials() {
  const d=store.data.draft;
  return `<section class="card" id="task-materials" tabindex="-1" aria-label="学习材料">${cardHeader('学习材料')}<div class="card-body"><div class="material-actions"><button class="btn btn-secondary" id="add-link">${icon('link',16)} 添加链接</button><label class="btn btn-secondary upload-label">${icon('upload',16)} 上传文件<input id="material-upload" type="file" multiple accept=".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.pptx,image/*" hidden></label></div><div class="material-list">${d.materials.length?d.materials.map((m,i)=>`<div class="material-row"><div class="file-icon ${m.type==='link'?'purple':''}">${icon(m.type==='link'?'link':m.type==='image'?'image':'file',20)}</div><div class="material-info"><strong>${e(m.name)}</strong><span>${m.type==='link'?e(m.url):`${m.type==='image'?'图片':'文档'} · ${m.size?format(m.size/1024)+' KB':'演示材料'}`}</span></div><button class="icon-btn" data-view-material="${i}" aria-label="查看材料">${icon('external',17)}</button><button class="icon-btn" data-remove-material="${i}" aria-label="移除材料">${icon('trash',17)}</button></div>`).join(''):'<div class="upload-empty">添加一份材料，帮助学员理解任务背景。</div>'}</div><p class="field-hint">原型中的上传文件保存在当前浏览器中，单文件不超过 2 MB。</p></div></section>`;
}
function renderScoring() {
  const d=store.data.draft; const total=d.rubric.reduce((sum,r)=>sum+Number(r.points||0),0);
  const ai=d.reviewMode==='ai';
  return `<section class="card" id="task-review" tabindex="-1" aria-label="审核方式">${cardHeader('审核方式')}<div class="card-body"><div class="review-options">${[['ai','sparkles','AI 自测','有固定答案，按评分标准自动判定。'],['manual','user','人工审核','无固定答案，由 NPC 或导师直接审核。']].map(([value,ic,title,desc])=>`<label class="review-option ${d.reviewMode===value?'selected':''}"><input type="radio" name="review-mode" value="${value}" ${d.reviewMode===value?'checked':''}><div class="review-option-icon">${icon(ic,20)}</div><div><strong>${title}</strong><p>${desc}</p></div><span class="radio-circle"></span></label>`).join('')}</div>${ai?`<label class="form-field pass-score-field"><span class="field-label">通过分数</span><div class="input-suffix"><input data-field="passScore" type="number" min="0" max="100" value="${d.passScore}"><span>/ 100</span></div><span class="field-hint">通过后全额发放奖励，每位学员每个任务仅领取一次。</span></label>`:''}</div></section>
  ${ai?`<section class="card" id="task-rubric" tabindex="-1" aria-label="AI 评分标准">${cardHeader('AI 评分标准',`<span id="rubric-total" class="tag ${total===100?'tag-green':'tag-red'}">合计 ${total}/100</span>`)}<div class="card-body rubric-list">${d.rubric.map((r,i)=>`<div class="rubric-row"><div class="rubric-index">${String(i+1).padStart(2,'0')}</div><div class="rubric-fields"><div class="rubric-top"><label class="form-field"><span class="field-label">评分维度</span><input data-rubric="${i}" data-key="name" value="${e(r.name)}" placeholder="例如：分析完整性"></label><label class="form-field rubric-score"><span class="field-label">分值</span><div class="input-suffix"><input type="number" min="1" max="100" data-rubric="${i}" data-key="points" value="${r.points}"><span>分</span></div></label><button class="icon-btn" data-remove-rubric="${i}" aria-label="删除评分维度">${icon('trash',17)}</button></div><textarea rows="2" data-rubric="${i}" data-key="description" placeholder="描述获得该分数需要满足的条件">${e(r.description)}</textarea></div></div>`).join('')}<div class="rubric-actions"><button class="btn btn-secondary" id="add-rubric">${icon('plus',16)} 添加维度</button><label class="btn btn-plain upload-label">${icon('upload',16)} 附加评分文档<input id="rubric-upload" type="file" accept=".pdf,.doc,.docx,.txt,.md" hidden></label></div>${(d.rubricAttachments||[]).map((a,i)=>`<div class="attachment-line">${icon('file',16)} ${e(a.name)} <button class="text-btn" data-remove-rubric-file="${i}">移除</button></div>`).join('')}</div></section>`:''}`;
}
function getReadiness() {
  const d=store.data.draft;
  const filled=value=>typeof value==='string'&&!!value.trim();
  const badges=d.badges||[], materials=d.materials||[], rubric=d.rubric||[];
  const validMaterial=m=>{
    if(!filled(m.name)||!['link','file','image'].includes(m.type))return false;
    if(m.type!=='link')return true;
    try{return ['http:','https:'].includes(new URL(m.url).protocol);}catch{return false;}
  };
  return [
    {id:'task-basics',title:'基础信息',ready:filled(d.title)&&d.title.trim().length<=80&&filled(d.summary)&&d.summary.trim().length<=500&&filled(d.domain)&&DIFFICULTY_PRESETS.some(p=>p.name===d.difficulty)},
    {id:'task-badges',title:'徽章配置',ready:badges.length>=1&&badges.length<=2&&new Set(badges.map(b=>b.id)).size===badges.length&&badges.every(b=>badgeList().some(x=>x.id===b.id)&&Number.isFinite(Number(b.weight))&&Number(b.weight)>0&&Number(b.weight)<=100)&&Math.abs(badges.reduce((sum,b)=>sum+Number(b.weight),0)-100)<0.000001},
    {id:'task-materials',title:'学习材料',ready:materials.length>0&&materials.every(validMaterial)},
    {id:'task-review',title:'审核方式',ready:['manual','ai'].includes(d.reviewMode)&&(d.reviewMode!=='ai'||(d.passScore!==null&&d.passScore!==undefined&&String(d.passScore).trim()!==''&&Number.isFinite(Number(d.passScore))&&Number(d.passScore)>=0&&Number(d.passScore)<=100))},
    ...(d.reviewMode==='ai'?[{id:'task-rubric',title:'评分标准',ready:rubric.length>0&&rubric.every(r=>filled(r.name)&&filled(r.description)&&Number.isFinite(Number(r.points))&&Number(r.points)>0)&&Math.abs(rubric.reduce((sum,r)=>sum+Number(r.points),0)-100)<0.000001}]:[]),
  ];
}
function focusSection(id) {
  const section=document.getElementById(id);
  if(!section)return;
  section.focus({preventScroll:true});
  section.scrollIntoView({behavior:'smooth',block:'start'});
  section.classList.add('jump-highlight');
  setTimeout(()=>section.classList.remove('jump-highlight'),1400);
}
function renderAside() {
  const d=applyDifficultyPreset(store.data.draft);
  const reward=rewardBreakdown(d);
  const checks=getReadiness();
  return `<section class="card overview-card compact-task-preview">
    <div class="overview-body"><div class="preview-meta-line"><span class="category-label">${e(d.domain)} <span>·</span> ${e(d.difficulty)}</span><span class="tag tag-neutral">实时预览</span></div><h3>${e(d.title||'等待你的第一个任务')}</h3>
      <div class="overview-time">${icon('clock',14)} 预计 ${d.minutes||0} 分钟 <span>${d.reviewMode==='manual'?'人工审核':'AI 自测'}</span></div>
      <div class="overview-rewards"><div><span class="metric-symbol">XP</span><strong>${format(reward.xp)}</strong><small>经验值</small></div><div>${icon('award',18)}<strong>${format(reward.totalPoints)}</strong><small>徽章点</small></div><div>${icon('star',18)}<strong>${format(reward.taskPoints)}</strong><small>任务点</small></div></div>
      <p class="preview-unlock-note">任务点可用于解锁其他任务</p>
      <div class="aside-distribution"><h4>徽章点分配</h4><div class="distribution-track">${d.badges.map((b,i)=>`<span class="bg-${i}" style="width:${b.weight}%"></span>`).join('')}</div>${reward.allocations.map((b,i)=>`<div class="distribution-row"><i class="color-dot color-${i}"></i><span>${e(b.name)}</span><strong>${format(b.points)}<small> 点</small></strong></div>`).join('')}</div>
    </div></section><section class="card checklist-card"><div class="checklist-heading"><h3>发布准备</h3><span>${checks.filter(x=>x.ready).length}/${checks.length}</span></div>${checks.map(({id,title,ready})=>`<button type="button" class="checklist-row ${ready?'complete':'incomplete'}" data-jump-section="${id}" aria-label="定位到${title}，${ready?'已完成':'待完成'}">${icon(ready?'checkCircle':'alert',16)}<span>${title}</span><small>${ready?'已完成':'待完成'}</small>${icon('chevronRight',13)}</button>`).join('')}</section>`;
}
function updateAside() { const aside=$('#editor-aside'); if(aside) aside.innerHTML=renderAside(); }

function bindEditor() {
  const d=store.data.draft;
  $('#save-draft').onclick=async()=>{if(!saveDraft())return;try{await store.saveTask({...structuredClone(d),status:'draft'});render();toast('草稿已保存，可在任务库中继续编辑');}catch(error){toast(error.message,'error');}};
  $('#publish-task').onclick=publish;
  $('#sandbox-test')?.addEventListener('click',()=>sandbox.open());
  $('#editor-aside').onclick=event=>{
    const button=event.target.closest('[data-jump-section]');
    if(button)focusSection(button.dataset.jumpSection);
  };
  $('#new-task').onclick=()=>openModal(`<div class="modal-heading"><h2>新建任务</h2><p>当前内容已自动保存，是否将它存入任务库后新建？</p></div><div class="modal-actions"><button class="btn btn-secondary" id="cancel-new">继续编辑</button><button class="btn btn-primary" id="confirm-new">保存并新建</button></div>`,modal=>{
    $('#cancel-new',modal).onclick=closeModal;
    $('#confirm-new',modal).onclick=async()=>{try{await store.saveTask({...structuredClone(d),status:'draft'});store.data.draft=newDraft();store.save();closeModal();render();window.scrollTo({top:0,behavior:'smooth'});toast('新任务已创建');}catch(error){toast(error.message||'新建失败，请先减少附件','error');}};
  });
  document.querySelectorAll('[data-field]').forEach(el=>el.addEventListener('input',()=>{ const key=el.dataset.field;d[key]=el.type==='number'?(el.value===''?'':Number(el.value)):el.value;if(key==='title'&&$('#title-counter'))$('#title-counter').textContent=`${el.value.length}/60`;saveDraft(); }));
  document.querySelectorAll('[data-badge]').forEach(btn=>btn.onclick=()=>{const id=btn.dataset.badge;const index=d.badges.findIndex(b=>b.id===id);if(index>=0)d.badges.splice(index,1);else if(d.badges.length<2)d.badges.push({id,weight:50});if(d.badges.length===1)d.badges[0].weight=100;if(d.badges.length===2)d.badges.forEach(b=>b.weight=50);saveDraft();render();});
  $('#ratio-slider')?.addEventListener('input',event=>{const value=Number(event.target.value);d.badges[0].weight=value;d.badges[1].weight=100-value;event.target.style.setProperty('--ratio',`${value}%`);d.badges.forEach((b,i)=>$(`#ratio-weight-${i}`).textContent=`${b.weight}%`);saveDraft();});
  $('#add-link')?.addEventListener('click',addLink);
  $('#material-upload')?.addEventListener('change',async event=>{await uploadFiles(event.target.files,'materials');render();});
  $('#rubric-upload')?.addEventListener('change',async event=>{await uploadFiles(event.target.files,'rubricAttachments');render();});
  document.querySelectorAll('[data-view-material]').forEach(b=>b.onclick=()=>viewMaterial(d.materials[Number(b.dataset.viewMaterial)]));
  document.querySelectorAll('[data-remove-material]').forEach(b=>b.onclick=()=>{d.materials.splice(Number(b.dataset.removeMaterial),1);saveDraft();render();});
  $('#add-rubric')?.addEventListener('click',()=>{d.rubric.push({id:crypto.randomUUID(),name:'',points:0,description:''});saveDraft();render();});
  document.querySelectorAll('[data-rubric]').forEach(el=>el.addEventListener('input',()=>{d.rubric[Number(el.dataset.rubric)][el.dataset.key]=el.type==='number'?Number(el.value):el.value;saveDraft();if(el.dataset.key==='points'){const total=d.rubric.reduce((s,r)=>s+Number(r.points||0),0);const tag=$('#rubric-total');if(tag){tag.textContent=`合计 ${total}/100`;tag.className=`tag ${total===100?'tag-green':'tag-red'}`;}}}));
  document.querySelectorAll('[data-remove-rubric]').forEach(b=>b.onclick=()=>{d.rubric.splice(Number(b.dataset.removeRubric),1);saveDraft();render();});
  document.querySelectorAll('[data-remove-rubric-file]').forEach(b=>b.onclick=()=>{d.rubricAttachments.splice(Number(b.dataset.removeRubricFile),1);saveDraft();render();});
  document.querySelectorAll('[name="review-mode"]').forEach(el=>el.onchange=()=>{d.reviewMode=el.value;saveDraft();render();});

}
function addLink() {
  openModal(`<div class="modal-heading"><h2>添加学习材料</h2><p>为学员提供可访问的文档或参考链接。</p></div><form id="link-form"><label class="form-field"><span class="field-label">材料名称</span><input name="name" required maxlength="120" placeholder="例如：用户访谈记录"></label><label class="form-field"><span class="field-label">链接地址</span><input name="url" type="url" required placeholder="https://"></label><div class="modal-actions"><button class="btn btn-secondary" type="button" id="cancel-link">取消</button><button class="btn btn-primary" type="submit">添加材料</button></div></form>`,modal=>{
    $('#cancel-link',modal).onclick=closeModal;
    $('#link-form',modal).onsubmit=event=>{event.preventDefault();const form=new FormData(event.target);const url=String(form.get('url')).trim();if(!/^https?:\/\//i.test(url)){toast('请输入 http 或 https 链接','error');return;}store.data.draft.materials.push({id:crypto.randomUUID(),name:String(form.get('name')).trim(),type:'link',url});saveDraft();closeModal();render();toast('材料已添加');};
  });
}
async function uploadFiles(files,target) {
  const d=store.data.draft; if(!d[target])d[target]=[];
  for(const file of files){
    if(file.size>2*1024*1024){toast(`${file.name} 超过 2 MB，请改用文档链接`,'error');continue;}
    const url=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});
    d[target].push({id:crypto.randomUUID(),name:file.name,type:file.type.startsWith('image/')?'image':'file',url,size:file.size,mime:file.type});
  }
  if(saveDraft())toast('文件已添加到当前草稿');
}
function viewMaterial(m) {
  if(m.type==='image'&&m.url?.startsWith('data:image/')) {openModal(`<div class="modal-heading"><h2>${e(m.name)}</h2></div><img src="${e(m.url)}" alt="${e(m.name)}" class="material-image">`);return;}
  if(/^https?:\/\//i.test(m.url||'')){window.open(m.url,'_blank','noopener,noreferrer');return;}
  if(m.url?.startsWith('data:')){const a=document.createElement('a');a.href=m.url;a.download=m.name;a.click();return;}
  openModal(`<div class="modal-heading"><h2>${e(m.name)}</h2><p>这是演示材料。你可以在“学习材料”中上传真实文件或添加文档链接。</p></div>`);
}
async function publish() {
  const errors=validateTask(store.data.draft);
  if(errors.length){render();toast(errors[0],'error');const missing=getReadiness().find(x=>!x.ready);if(missing)focusSection(missing.id);return;}
  const launch = $('#publish-task');
  if (launch.disabled) return;
  launch.disabled = true;
  try {
    const savedTask = await store.saveTask(structuredClone(store.data.draft));
    const links = [...new Set(savedTask.materials.filter(m=>m.type==='link').map(m=>m.url))];
    const reviewers = store.members.filter(m=>m.roles.includes('REVIEWER'));
    let key = crypto.randomUUID(), keySelection;
    openModal(`<div class="native-publish-confirm"><div class="modal-heading"><h2>确认发布任务</h2><p>${e(savedTask.title)}</p></div><label class="form-field"><span class="field-label">内容复核人</span><select id="publish-reviewer"><option value="">请选择审核人</option>${reviewers.map(m=>`<option value="${e(m.id)}">${e(m.name)}</option>`).join('')}</select></label><p class="field-hint">请逐项打开材料链接，确认可供学员访问。</p>${links.map((url,i)=>`<label class="admin-check-link"><input type="checkbox" data-verified-link="${i}"><a href="${e(url)}" target="_blank" rel="noopener noreferrer">${e(url)} ↗</a></label>`).join('')}<div class="notice">发布会创建新的任务版本；学员已有的任务和提交保留原版本。</div><p class="inline-error" id="publish-error" role="alert" hidden></p><div class="modal-actions"><button class="btn btn-secondary" id="cancel-publish">取消</button><button class="btn btn-primary" id="confirm-publish" disabled>确认发布</button></div></div>`, modal => {
      const reviewer = $('#publish-reviewer',modal), confirm = $('#confirm-publish',modal);
      const selected = () => [...modal.querySelectorAll('[data-verified-link]:checked')].map(el=>links[Number(el.dataset.verifiedLink)]);
      const ready = () => { confirm.disabled = !reviewer.value || selected().length !== links.length; };
      reviewer.onchange = ready;
      modal.querySelectorAll('[data-verified-link]').forEach(el=>el.onchange=ready);
      $('#cancel-publish',modal).onclick = closeModal;
      confirm.onclick = async () => {
        if (confirm.disabled) return;
        const selection = JSON.stringify([reviewer.value,selected()]);
        if (keySelection && keySelection !== selection) key = crypto.randomUUID();
        keySelection = selection;
        modal.dataset.operationPending = 'true';
        modal.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);
        confirm.textContent = '正在发布…';
        const error = $('#publish-error',modal); error.hidden = true;
        try {
          const published = await service.tasks.publish(savedTask,reviewer.value,selected(),key);
          modal.dataset.operationPending = 'false';
          sandbox.retainForPublishedTask(savedTask,published);
          render(); toast('任务发布成功，已加入任务库');
          openModal(`<div class="publication-result"><div class="publication-check">${icon('check',30)}</div><span class="eyebrow">READY FOR THE JOURNEY</span><h2>任务发布成功</h2><p>${e(published.title)}</p><div class="notice">任务已保存到任务库。</div><button class="btn btn-primary" id="go-library">前往任务库 ${icon('arrowRight',16)}</button></div>`,result=>$('#go-library',result).onclick=()=>{closeModal();navigate('library');});
        } catch (err) {
          modal.dataset.operationPending = 'false';
          modal.querySelectorAll('button,input,select').forEach(el=>el.disabled=false);
          confirm.textContent = '确认发布'; ready(); error.textContent=err.message; error.hidden=false;
        }
      };
    });
  } catch(err){toast(err.message||'发布准备失败，请检查配置','error');}
  finally { launch.disabled=false; }
}

onInviteSessionChange(render);
render();

let refreshing = false;
async function refreshRecords() {
  if (refreshing || document.hidden || document.querySelector('.modal') || ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) return;
  refreshing = true;
  try { await store.refresh(); if (page === 'review' || page === 'library') render(); }
  catch (error) { toast(error.message, 'error'); }
  finally { refreshing = false; }
}
setInterval(refreshRecords, 12000);
window.addEventListener('focus', refreshRecords);
const requestedReview = new URL(location.href).searchParams.get('review');
if (requestedReview) {
  const submission = store.data.submissions.find(s => s.id === requestedReview);
  if (submission) { reviewCamp = submission.camp; navigate('review'); await openSubmission(store, ui, requestedReview); }
  else toast('当前账号未找到这条审核记录。','error');
}
