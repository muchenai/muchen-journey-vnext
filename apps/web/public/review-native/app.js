import {canConfigureTask, EXPLORATION_CONFIGURATION_NOTICE} from './task-publication-access.js';
import {createKnowledgeStore} from './knowledge-store.js?v=20261103-module-publication';
import {createKnowledgeController} from './knowledge.js?v=20261103-module-publication';
import {createGuildStore} from './guild-store.js?v=20261028-server';
import {createGuildController} from './guild.js?v=20261028-server';
import {createPublicationReviewController} from './publication-review.js?v=20261030-member-action-spacing';
import { createTaskWorkflow, isTaskUpdate } from './task-workflow.js?v=20261030-member-action-spacing';
import {createMedalsApi} from './medals-api.js?v=20261028-publication-local';
import {createMedalsController} from './medals.js?v=20261103-badge-layout-fix';
import { renderPublishMaterials } from './publish-materials.js';
import { uploadExplorationMaterial, localMaterialUrl, materialSizeLabel, materialImagePreviewUrl } from './exploration-material-files.js';
import { hasTransferredFiles, transferredFiles, normalizeLearningMaterialFile, isMaterialPasteTarget } from './material-upload-input.js';
import { nextExplorationOrder, isPinnedExplorationTask, explorationDisplayOrder } from './exploration-order.js';
import { EXPLORATION_COMPLETION_MODES, explorationCompletionMode, requiresTaskAssessment, taskCompletionLabel, explorationTaskFiles, explorationTaskResourceErrors, taskResourceLinks } from './exploration-completion.js';
import { BADGES, DIFFICULTY_PRESETS, REVIEW_CAMPS, getReviewCamp, getSubmissionStatus, applyDifficultyPreset, normalizeBadgeWeights, escapeHtml as e, icon, rewardBreakdown, validateTask } from './core.js?v=20261030-member-action-spacing';
import { ApiStore, newDraft, createJourneyService } from './native-api.js?v=20261030-member-action-spacing';
import { createSandboxController } from './sandbox.js?v=20261021-brand-npc';
import { renderReview, bindReview, openSubmission } from './review.js?v=20261026-passed-tab';
import { renderLibrary, bindLibrary, openTask } from './library.js?v=20261030-member-action-spacing';
import { openCertification } from './member-access.js?v=20261030-member-action-spacing';
import { isInviteLoggedIn, getCurrentInviteUser, clearInviteSession, renderInviteLogin, bindInviteLogin, onInviteSessionChange } from './native-api.js?v=20261030-member-action-spacing';
import { createAcademyStore } from './native-api.js?v=20261030-member-action-spacing';
import { createAcademyController } from './academy.js?v=20261105-sources';

import {departmentOptions, departmentLabel, isPublishingDepartment} from './publishing-departments.js';
import { createMaterialEditor } from './material-editor.js';
import { isMaterialLink } from './material-validation.js';
import { TASK_FIELD_LIMITS, taskFieldLength, validateTaskFieldLimits } from './task-field-limits.js';


const store = await ApiStore.create().catch(error => { document.querySelector('#app').innerHTML = `<div class="card empty-state"><strong>${e(error.message)}</strong><a href="/review/login">重新登录</a></div>`; throw error; });
const service = createJourneyService({ store, getCurrentUser: getCurrentInviteUser });
const editMaterial = createMaterialEditor({store,openModal,closeModal,saveDraft,refresh:render,toast});
let materialUploadsPending = false;
const readingCompletionModes = new WeakMap();
let page = location.hash.startsWith('#medals') ? 'medals' : ['publish','review','publications','library','knowledge','guild','academy'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'publish';
let reviewCamp = 'novice';
try { const savedCamp = localStorage.getItem('journey_admin_review_camp'); if (REVIEW_CAMPS.some(camp => camp.id === savedCamp)) reviewCamp = savedCamp; } catch {}
const $ = (s, root = document) => root.querySelector(s);
const taskWorkflow = createTaskWorkflow({store,newDraft,openModal,closeModal,showEditor:()=>{navigate('publish');window.scrollTo({top:0,behavior:'smooth'});},toast});
const ui = { toast, refresh: render, openModal, closeModal, navigate, editTask, icon, service, get currentUser() { return getCurrentInviteUser(); }, get reviewCamp() { return reviewCamp; }, get isSuperAdmin() { return getCurrentInviteUser()?.accessRole === 'super_admin'; }, get canGrantSuperAdmins() { return store.capabilities?.canGrantSuperAdmins === true; }, newTask: () => taskWorkflow.start(), copyTask: task => taskWorkflow.start(task) };
const knowledgeStore=createKnowledgeStore({getCurrentUser:getCurrentInviteUser});
const knowledge=createKnowledgeController({knowledge:knowledgeStore,ui});
const guildStore=createGuildStore({getCurrentUser:getCurrentInviteUser});
const guild=createGuildController({guild:guildStore,ui});
let guildError='',guildLoading=false,guildLoaded=false;
async function loadGuild(){guildLoading=true;guildError='';try{await guildStore.ready();guildLoaded=true;}catch(error){guildError=error.message;}finally{guildLoading=false;if(page==='guild')render();}}
const academyStore = createAcademyStore({ getCurrentUser: getCurrentInviteUser });
const academy = createAcademyController({ academy: academyStore, ui });
const economy = createMedalsApi(store);
const medals = createMedalsController({economy,ui});
ui.medalTabChanged = tab => history.replaceState(null, '', tab === 'artworks' ? '#medals/artworks' : tab === 'records' ? '#medals/records' : '#medals');
if (page === 'medals') {
  medals.selectTab(location.hash.split('/')[1]);
  await economy.refresh().catch(error => toast(error.message, 'error'));
}
const publicationReview = createPublicationReviewController({store,service,ui});
const badgeList = () => Array.isArray(BADGES) ? BADGES : Object.values(BADGES);
const badgeName = id => `${badgeList().find(b => b.id === id)?.category || id}徽章点`;
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
  $('.modal')?.dispatchEvent(new Event('review-close'));
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
  $('.modal')?.dispatchEvent(new Event('review-close'));
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
function navigate(next) { if(materialUploadsPending){toast('学习材料正在上传，请稍候。');return;} if(page==='knowledge')knowledge.reset();if(page==='guild')guild.deactivate();if(next==='guild')void loadGuild(); if (page === 'academy' && next !== 'academy') academy.deactivate(); page = next; if(next==='academy')void academy.activate(); history.replaceState(null, '', '#'+next); if(next==='medals'){medals.reset();void economy.refresh().catch(error=>toast(error.message,'error')).finally(()=>{if(page==='medals')render();});} render(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
function editTask(task) {
  if (!canConfigureTask(task, ui.isSuperAdmin)) { toast(EXPLORATION_CONFIGURATION_NOTICE, 'error'); return; }
  if (!store.operatorId) { toast('当前账号没有任务配置权限。','error'); return; }
  if (task.authorId && task.authorId !== store.operatorId) { taskWorkflow.start(task); return; }
  store.data.draft = normalizeBadgeWeights(task); store.save(); navigate('publish');
}
function saveDraft() {
  if (!canConfigureTask(store.data.draft, ui.isSuperAdmin)) { toast(EXPLORATION_CONFIGURATION_NOTICE, 'error'); return false; }
  Object.assign(store.data.draft, applyDifficultyPreset(store.data.draft));
  store.data.draft.updatedAt = new Date().toISOString();
  updateAside();
  try {
    const pending = store.save();
    const saved = $('#saved-status');
    if(saved) saved.innerHTML = pending?.then ? '正在保存本机草稿…' : `${icon('checkCircle',14)} 草稿已保存`;
    if(pending?.then) pending.then(()=>{const status=$('#saved-status');if(status)status.innerHTML=`${icon('checkCircle',14)} 草稿已保存`;}).catch(()=>{const status=$('#saved-status');if(status)status.textContent='本机草稿缓存未保存，请点击保存草稿写入本地任务库';});
    return true;
  }
  catch(error) { const saved=$('#saved-status');if(saved)saved.textContent='尚未保存，请减少附件后重试';toast(error.message||'保存失败，请重试','error');return false; }
}

function shell(content) {
  const currentUser = getCurrentInviteUser();
  const pendingInCamp = camp => store.data.submissions.filter(s => { const task=store.getTask(s.taskId)||{}; return !s.supersededBy&&getReviewCamp(s,task)===camp&&getSubmissionStatus(s,task)==='pending'; }).length;
  const pending = REVIEW_CAMPS.reduce((sum,camp)=>sum+pendingInCamp(camp.id),0);
  const labels = {knowledge:'知识库管理',guild:'交付线公会',publish:'发布任务配置',review:`${REVIEW_CAMPS.find(camp=>camp.id===reviewCamp).label}审核`,library:'任务库',academy:'AI学院',medals:'徽章系统',publications:ui.isSuperAdmin?'审核待发布的任务':'我的发布'};
  const navigation = [
    { id: 'publish', symbol: 'grid', label: '发布任务配置' },
    {id:'publications',symbol:'checkCircle',label:ui.isSuperAdmin?'审核任务':'我的发布'},
    ...REVIEW_CAMPS.map(camp => ({ id: 'review', camp: camp.id, symbol: 'checkCircle', label: `${camp.label}审核` })),
    { id: 'library', symbol: 'library', label: '任务库' },
    { id: 'medals', symbol: 'award', label: '徽章系统' },
    { id: 'academy', symbol: 'book', label: 'AI学院' },
    {id:'knowledge',symbol:'library',label:'知识库管理'},
    {id:'guild',symbol:'users',label:'交付线公会'},
  ].map(item => {
    const active = page === item.id && (!item.camp || reviewCamp === item.camp);
    const count = item.camp ? pendingInCamp(item.camp) : item.id==='publications' ? publicationReview.badgeCount() : 0;
    return `<div class="nav-group"><button type="button" class="nav-item ${item.camp ? 'review-camp-primary ' : ''}${active ? 'active' : ''}" aria-label="${item.label}" title="${item.label}" ${item.camp ? `data-review-camp="${item.camp}"` : `data-page="${item.id}"`} ${active ? 'aria-current="page"' : ''}>${icon(item.symbol,19)}<span>${item.label}</span>${count ? `<span class="nav-count">${count}</span>` : ''}</button></div>`;
  }).join('');
  return `<header class="topbar"><a href="#" class="brand" aria-label="JOURNEY首页"><img src="./journey-logo-119.svg" alt="" width="34" height="34"><span class="brand-wordmark">JOURNEY <span class="brand-sub">管理系统</span></span></a><div class="topbar-right"><button id="theme-toggle" class="theme-toggle" type="button" aria-label="${document.documentElement.dataset.theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'}" title="${document.documentElement.dataset.theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'}">${themeToggleContent()}</button>${ui.isSuperAdmin?`<button id="cert-btn" class="cert-btn">${icon('shield',16)} 认证</button>`:''}<button id="notification-btn" class="icon-btn notification-btn" aria-label="审核通知">${icon('bell',19)}${pending?'<i></i>':''}</button><div class="header-user"><div class="avatar avatar-small">${e((currentUser?.name || '成').slice(0,1))}</div><span>${e(currentUser?.name || '学院成员')}</span></div><button id="logout-btn" class="logout-btn" type="button">退出登录</button></div></header>
  <aside class="sidebar"><nav aria-label="主导航">${navigation}</nav><div class="sidebar-bottom"><button class="guide-entry" id="guide-btn" type="button">${icon('book',20)}<span>使用指南</span></button></div></aside>
  <div class="app-main"><main class="main-content" aria-label="${labels[page]}">${content}</main></div>`;
}

function render() {
  if(materialUploadsPending)return;
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
  try { content = page==='knowledge' ? knowledge.render() : page==='guild' ? (guildError ? `<div class="gd-empty" role="alert">${e(guildError)}<button class="btn" data-page="guild">重新加载</button></div>` : !guildLoaded || guildLoading ? '<div class="gd-empty">正在加载公会…</div>' : guild.render()) : page === 'publications' ? publicationReview.render() : page === 'medals' ? (economy.loading ? '<div class="md-empty">正在读取徽章…</div>' : economy.error ? `<div class="md-empty" role="alert">${e(economy.error)}<button class="btn btn-secondary" data-page="medals">重新加载</button></div>` : medals.render()) : page === 'academy' ? academy.render() : page === 'review' ? renderReview(store,ui) : page === 'library' ? renderLibrary(store,ui) : renderEditor(); }
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
  $('#guide-btn').onclick = () => openModal(`<div class="modal-heading"><h2>使用指南</h2></div><div class="guide-list">${[['填写基础信息','填写任务标题与简述，选择难度及 1～2 个徽章。'],['添加学习材料','添加文档链接、图片或文件。'],['选择审核方式与评分标准','有固定答案选择 AI 自测并填写评分标准；无固定答案选择人工审核。'],['查看右侧预览','AI 自测任务可选用沙盒试测，超级管理员确认后发布；普通管理员提交发布审核。']].map(([title,description])=>`<div><section><strong>${title}</strong><p>${description}</p></section></div>`).join('')}</div><div class="notice">任务、提交和审核记录来自本地服务。编辑中的草稿保存在当前账号的浏览器中；AI 自查仅供参考，最终由审核人确认。</div>`);
  if (page === 'publish') {if(canConfigureTask(store.data.draft,ui.isSuperAdmin))bindEditor();else $('#new-task').onclick=()=>taskWorkflow.start();if(canConfigureTask(store.data.draft,ui.isSuperAdmin)&&draftPublication()?.status==='pending'){$('.main-content').querySelectorAll('input,textarea,select,button').forEach(el=>el.disabled=true);$('#new-task').disabled=false;$('#publish-task').textContent='待审核';}}
  else if(page==='knowledge')knowledge.bind($('.main-content'));
  else if(page==='guild'){if(guildLoaded&&!guildLoading&&!guildError)guild.bind($('.main-content'));else if(!guildLoading&&!guildError)void loadGuild();}
  else if (page === 'publications') publicationReview.bind($('.main-content'));
  else if (page === 'medals') medals.bind($('.main-content'));
  else if (page === 'academy') academy.bind($('.main-content'));
  else if (page === 'review') bindReview($('.main-content'),store,ui);
  else bindLibrary($('.main-content'),store,ui);
}

function draftPublication() {return store.getTask(store.data.draft.id)?.publication || store.data.draft.publication;}
function renderEditor() {
  if (!canConfigureTask(store.data.draft,ui.isSuperAdmin)) return `<section class="card empty-state exploration-config-restricted"><strong>${EXPLORATION_CONFIGURATION_NOTICE}</strong><p>你可以在任务库中查看探索营任务，或新建新手村任务。</p><button class="btn btn-primary" id="new-task">新建新手村任务</button></section>`;
  const publication=draftPublication();
  const publicationNote=publication?.status==='pending'?'任务已提交，等待超级管理员审核。审核期间暂不能编辑；已发布版本保持不变。':publication?.status==='rejected'?`发布申请已退回：${e(publication.comment)}。修改后可重新提交。`:!ui.isSuperAdmin?'普通管理员提交后，由超级管理员审核通过再发布。':'';
  return `${publicationNote?`<div class="notice publication-editor-note" role="status">${publicationNote}</div>`:""}<div class="editor-layout"><div class="editor-primary" id="editor-primary"><div class="notice" role="status">${isTaskUpdate(store.data.draft) ? (store.data.draft.status==='archived' ? '正在编辑已下架任务。发布更新后将重新开放领取。' : '正在编辑已发布任务。发布更新会更新现有任务，不会新增任务卡；保存草稿不影响当前已发布版本。') : publication?.status==='rejected' ? '正在修改退回的任务。重新提交仍使用原任务，不会创建重复任务。' : '正在创建新任务。发布后将在学员端新增一张任务卡。'}</div>${renderBasics()}${renderMaterials()}${renderTaskFiles()}${renderScoring()}</div><aside class="editor-aside" id="editor-aside">${renderAside()}</aside></div>
    <div class="editor-actionbar"><div id="saved-status">${icon('checkCircle',14)} 草稿已保存 <span class="muted">· 仅当前浏览器</span></div><div class="action-buttons"><button class="btn btn-plain" id="save-draft">保存草稿</button>${requiresTaskAssessment(store.data.draft)&&store.data.draft.reviewMode==='ai'?`<button class="btn btn-secondary" id="sandbox-test">${icon('sparkles',16)} 沙盒试测</button>`:''}<button class="btn btn-primary" id="publish-task">${icon('send',16)} ${ui.isSuperAdmin?(isTaskUpdate(store.data.draft)?'发布更新':'发布新建任务'):'提交审核'}</button></div></div>`;
}
function cardHeader(title,right='') {
  return `<div class="card-header"><div class="section-title"><h2>${title}</h2></div>${right}</div>`;
}
function renderBasics() {
  const d = store.data.draft;
  const exploration = getReviewCamp({}, d) === 'exploration';
  const pinned = isPinnedExplorationTask(d);
  return `<section class="card" id="task-basics" tabindex="-1" aria-label="基础信息">${cardHeader('基础信息',`<div class="basics-header-actions"><span class="required-note"><i>*</i> 为必填项</span><button class="btn btn-secondary btn-sm" id="new-task">${icon('plus',15)} 新建任务</button></div>`)}<div class="card-body form-grid">
    <label class="form-field full"><span class="field-label">任务标题 <i>*</i></span><div class="input-counter"><input data-field="title" value="${e(d.title)}" maxlength="${TASK_FIELD_LIMITS.title}" placeholder="给任务起一个清晰、具体的名字"><span id="title-counter">${taskFieldLength(d.title)}/${TASK_FIELD_LIMITS.title}</span></div></label>
    <label class="form-field full"><span class="field-label">任务简述 <i>*</i></span><textarea data-field="summary" rows="3" maxlength="${TASK_FIELD_LIMITS.summary}" placeholder="简要介绍任务背景与学习目标">${e(d.summary)}</textarea><span class="field-hint task-summary-hint"><span>让学员快速了解：要做什么，以及为什么做。</span><span id="summary-counter">${taskFieldLength(d.summary)}/${TASK_FIELD_LIMITS.summary}</span></span></label>
    <fieldset class="form-field full camp-field"><legend class="field-label">所属营地</legend><div class="camp-options">${REVIEW_CAMPS.map(camp=>`<label class="camp-option"><input type="radio" name="task-camp" data-field="camp" value="${camp.id}" ${getReviewCamp({},d)===camp.id?'checked':''} ${!canConfigureTask({camp:camp.id},ui.isSuperAdmin)?'disabled title="探索营任务仅限超级管理员配置"':''}><span>${camp.label}</span></label>`).join('')}</div></fieldset>
    ${exploration ? `<label class="form-field full"><span class="field-label">任务排序${pinned?'':' <i>*</i>'}</span>${pinned?'<input type="text" value="固定在毕业码前" readonly aria-label="任务排序：固定在毕业码前"><span class="field-hint">培训签退固定为倒数第二项，新增普通任务自动排在它前面。</span>':`<input data-field="order" type="number" min="1" max="9999" step="1" required value="${e(d.order ?? 1)}" placeholder="例如：1"><span class="field-hint">发布后按此位置插入，后续普通任务自动顺延；培训签退固定在毕业码前，超出普通任务数量时插入培训签退前。${Number.isInteger(d.publishedOrder)?` 当前已发布排序：第 ${d.publishedOrder} 个。`:''}</span>`}</label>` : ''}
    ${exploration ? `<fieldset class="form-field full exploration-task-choice"><legend class="field-label">是否需要做任务 <i>*</i></legend><div class="review-options">${[[false,'不需要','阅读学习材料后即可完成'],[true,'需要','阅读学习材料后，还需完成题目并提交成果']].map(([required,label,description])=>`<label class="review-option ${requiresTaskAssessment(d)===required?'selected':''}"><input type="radio" name="requires-task" data-requires-task="${required}" ${requiresTaskAssessment(d)===required?'checked':''}><div><strong>${label}</strong><p>${description}</p></div><span class="radio-circle"></span></label>`).join('')}</div><span class="field-hint">任务文件可以包含选择题、解答题等；学习材料和任务文件分别添加。</span></fieldset>${!requiresTaskAssessment(d)?`<label class="form-field full"><span class="field-label">完成方式 <i>*</i></span><select data-field="completionMode">${EXPLORATION_COMPLETION_MODES.filter(mode=>mode.id!=='assessment').map(mode=>`<option value="${mode.id}" ${explorationCompletionMode(d)===mode.id?'selected':''}>${mode.label}</option>`).join('')}</select><span class="field-hint">${e(EXPLORATION_COMPLETION_MODES.find(mode=>mode.id===explorationCompletionMode(d)).description)}</span></label>`:''}` : ''}
    ${exploration ? '' : `<label class="form-field"><span class="field-label">发布部门 <span class="required">*</span></span><select data-field="publishingDepartment" required>${departmentOptions(d.publishingDepartment)}</select></label>
    <label class="form-field"><span class="field-label">难度 <i>*</i></span><select data-field="difficulty">${DIFFICULTY_PRESETS.map(({name})=>`<option ${name===d.difficulty?'selected':''} ${store.capabilities?.allowedDifficulties.includes(name)?'':'disabled'}>${name}</option>`).join('')}</select>${store.capabilities?.isSuperAdmin?'':`<span class="field-hint">当前认证：${e(store.capabilities?.level||'初级')}，可发布${e((store.capabilities?.allowedDifficulties||[]).join('、'))}任务</span>`}</label>`}

  </div></section>
  ${exploration ? '' : `<section class="card" id="task-badges" tabindex="-1" aria-label="奖励点数类型">${cardHeader('奖励点数类型',`<span class="subtle-label">已选 ${d.badges.length}/2</span>`)}<div class="card-body"><div class="badge-selector">${badgeList().map(b=>{const chosen=d.badges.some(x=>x.id===b.id);return `<button class="badge-option ${chosen?'selected':''}" data-badge="${b.id}" aria-pressed="${chosen}" ${!chosen&&d.badges.length>=2?'disabled':''}>${icon('award',16)}<span>${e(badgeName(b.id))}</span>${chosen?icon('check',14):''}</button>`}).join('')}</div>${renderRatio()}</div></section>`}`;
}
function renderRatio() {
  const d=store.data.draft;
  if (!d.badges.length) return `<div class="notice reward-selection-notice">请选择至少一类奖励点数。</div>`;
  return `<div class="ratio-section"><div class="ratio-heading"><span>徽章点占比</span><span class="muted">每档 20% · 合计 100%</span></div><div class="ratio-labels">${d.badges.map((b,i)=>`<div><i class="color-dot color-${i}"></i><span>${e(badgeName(b.id))}</span><strong id="ratio-weight-${i}">${b.weight}%</strong></div>`).join('')}</div>${d.badges.length===2?`<div class="ratio-control" data-ratio="${d.badges[0].weight}"><input class="ratio-slider" aria-label="${e(badgeName(d.badges[0].id))}占比" id="ratio-slider" type="range" min="20" max="80" step="20" value="${d.badges[0].weight}" aria-valuetext="${d.badges[0].weight}%"></div>`:'<div class="single-ratio"><span></span></div>'}</div>`;
}

function renderMaterialRows(materials, collection='materials') {
  return materials.map((m,i)=>{
    const preview=materialImagePreviewUrl(m);
    return `<div class="material-row"><div class="file-icon ${m.type==='link'?'purple':''} ${preview?'material-thumbnail':''}">${preview?`<img src="${e(preview)}" alt="" loading="lazy" data-material-thumbnail>`:icon(m.type==='link'?'link':'file',20)}</div><div class="material-info"><strong>${e(m.name)}</strong><span>${m.type==='link'?e(m.url):`${preview?'图片':String(m.mime||'').startsWith('video/')?'视频':'附件'} · ${m.size?materialSizeLabel(m.size):'文本内容'}`}</span></div><button class="icon-btn" data-view-material="${i}" data-material-collection="${collection}" aria-label="查看${e(m.name)}">${icon('external',17)}</button><button class="icon-btn" data-edit-material="${i}" data-material-collection="${collection}" aria-label="编辑${e(m.name)}">${icon('edit',17)}</button><button class="icon-btn" data-remove-material="${i}" data-material-collection="${collection}" aria-label="移除${e(m.name)}">${icon('trash',17)}</button></div>`;
  }).join('');
}
function renderMaterials() {
  const d=store.data.draft;
  const rows=renderMaterialRows(d.materials);
  return `<section class="card" id="task-materials" tabindex="-1" aria-label="学习材料">${cardHeader('学习材料',`<span class="subtle-label">已添加 ${d.materials.length} 份</span>`)}<div class="card-body"><div class="material-actions"><button class="btn btn-secondary" id="add-link">${icon('link',16)} 添加链接</button><label class="btn btn-secondary upload-label">${icon('upload',16)} 上传文件<input id="material-upload" type="file" multiple hidden></label></div><div class="material-dropzone" id="material-dropzone" role="group" tabindex="0" aria-label="学习材料上传区：拖入文件，按 Ctrl+V 粘贴图片和文件，或按 Enter 选择文件" aria-describedby="material-dropzone-hint"><span class="material-dropzone-icon">${icon('upload',25)}</span><strong>把文档、图片或视频拖到这里，也可以点击后粘贴</strong><span id="material-dropzone-hint">点击此区域后按 <kbd>Ctrl</kbd> + <kbd>V</kbd>，直接粘贴截图或复制的文件</span><small>按 Enter 可选择文件；支持多文件，暂不支持文件夹</small></div><div class="material-list">${rows||'<div class="upload-empty">添加多份文档链接、文件或图片，帮助学员理解任务背景。</div>'}</div><p class="field-hint">支持添加多份学习材料，可连续添加链接或一次选择多个文件。${getReviewCamp({},d)==='exploration'?'每个任务最多 20 份材料；':''}单文件不超过 ${getReviewCamp({},d)==='exploration'?'100':'2'} MB，文件随任务保存并发布。</p><p id="material-upload-status" role="status" aria-live="polite" class="field-hint"></p></div></section>`;
}
function renderTaskFiles() {
  const d=store.data.draft;
  if(d.camp!=='exploration'||!requiresTaskAssessment(d))return '';
  const files=explorationTaskFiles(d);
  return `<section class="card" id="task-files" tabindex="-1" aria-label="任务文件">${cardHeader('任务文件',`<span class="subtle-label">已添加 ${files.length} 份</span>`)}<div class="card-body"><p class="exploration-task-file-intro">上传包含选择题、解答题等内容的任务文档。学员阅读学习材料后，打开任务文件做题并提交成果。</p><div class="material-actions"><label class="btn btn-primary upload-label">${icon('upload',16)} 上传任务文件<input id="task-file-upload" type="file" multiple hidden></label><button class="btn btn-secondary" id="add-task-link">${icon('link',16)} 添加任务链接</button></div><div class="material-dropzone" id="task-file-dropzone" role="group" tabindex="0" aria-label="任务文件上传区：拖入任务文档或按 Enter 选择文件"><span class="material-dropzone-icon">${icon('file',25)}</span><strong>将任务文档拖到这里，或点击后粘贴文件</strong><small>支持多文件；每个任务最多 20 份任务文件，单文件不超过 100 MB</small></div><div class="material-list">${renderMaterialRows(files,'taskFiles')||'<div class="upload-empty">尚未添加任务文件，请上传题目文档或添加任务链接。</div>'}</div><p id="task-file-upload-status" role="status" aria-live="polite" class="field-hint"></p><label class="form-field exploration-assessment-link"><span class="field-label">已有培训测试链接（选填）</span><input data-field="assessmentUrl" type="url" maxlength="2048" value="${e(d.assessmentUrl||'')}" placeholder="https://"><span class="field-hint">已有外部测试页面时可填写此项。上传任务文件、添加任务链接或填写测试链接，至少选择一种。</span></label></div></section>`;
}
function renderScoring() {
  if(!requiresTaskAssessment(store.data.draft))return '';
  const d=store.data.draft; const total=d.rubric.reduce((sum,r)=>sum+Number(r.points||0),0);
  const ai=d.reviewMode==='ai';
  return `<section class="card" id="task-review" tabindex="-1" aria-label="审核方式">${cardHeader('审核方式')}<div class="card-body"><div class="review-options">${[['ai','sparkles','AI 自测','有固定答案，按评分标准自动判定。'],['manual','user','人工审核','无固定答案，由 NPC 或导师直接审核。']].map(([value,ic,title,desc])=>`<label class="review-option ${d.reviewMode===value?'selected':''}"><input type="radio" name="review-mode" value="${value}" ${d.reviewMode===value?'checked':''}><div class="review-option-icon">${icon(ic,20)}</div><div><strong>${title}</strong><p>${desc}</p></div><span class="radio-circle"></span></label>`).join('')}</div>${ai?`<label class="form-field pass-score-field"><span class="field-label">通过分数</span><div class="input-suffix"><input data-field="passScore" type="number" min="0" max="100" value="${d.passScore}"><span>/ 100</span></div><span class="field-hint">${getReviewCamp({},d)==='exploration'?'达到通过分数后完成任务。':'通过后全额发放奖励，每位学员每个任务仅领取一次。'}</span></label>`:''}</div></section>
  ${ai?`<section class="card" id="task-rubric" tabindex="-1" aria-label="AI 评分标准">${cardHeader('AI 评分标准',`<span id="rubric-total" class="tag ${total===100?'tag-green':'tag-red'}">合计 ${total}/100</span>`)}<div class="card-body rubric-list">${d.rubric.map((r,i)=>`<div class="rubric-row"><div class="rubric-index">${String(i+1).padStart(2,'0')}</div><div class="rubric-fields"><div class="rubric-top"><label class="form-field"><span class="field-label">评分维度</span><input data-rubric="${i}" data-key="name" value="${e(r.name)}" placeholder="例如：分析完整性"></label><label class="form-field rubric-score"><span class="field-label">分值</span><div class="input-suffix"><input type="number" min="1" max="100" data-rubric="${i}" data-key="points" value="${r.points}"><span>分</span></div></label><button class="icon-btn" data-remove-rubric="${i}" aria-label="删除评分维度">${icon('trash',17)}</button></div><textarea rows="2" data-rubric="${i}" data-key="description" placeholder="描述获得该分数需要满足的条件">${e(r.description)}</textarea></div></div>`).join('')}<div class="rubric-actions"><button class="btn btn-secondary" id="add-rubric">${icon('plus',16)} 添加维度</button><label class="btn btn-plain upload-label">${icon('upload',16)} 附加评分文档<input id="rubric-upload" type="file" accept=".pdf,.doc,.docx,.txt,.md" hidden></label></div>${(d.rubricAttachments||[]).map((a,i)=>`<div class="attachment-line">${icon('file',16)} ${e(a.name)} <button class="text-btn" data-remove-rubric-file="${i}">移除</button></div>`).join('')}</div></section>`:''}`;
}
function getReadiness() {
  const d=store.data.draft;
  const assessment=requiresTaskAssessment(d);
  const filled=value=>typeof value==='string'&&!!value.trim();
  const badges=d.badges||[], materials=d.materials||[], rubric=d.rubric||[], taskFiles=explorationTaskFiles(d);
  const validMaterial=m=>{
    if(!filled(m.name)||m.name.trim().length>(d.camp==='exploration'&&m.type!=='link'?240:160)||!['link','file','image'].includes(m.type))return false;
    if(m.type!=='link')return true;
    return isMaterialLink(m.url);
  };
  return [
    {id:'task-basics',title:'基础信息',ready:filled(d.title)&&d.title.trim().length>=3&&!validateTaskFieldLimits(d).length&&filled(d.summary)&&d.summary.trim().length>=10&&(getReviewCamp({},d)==='exploration'?(d.order==null||(Number.isInteger(d.order)&&d.order>=1&&d.order<=9999)):(isPublishingDepartment(d.publishingDepartment)&&DIFFICULTY_PRESETS.some(p=>p.name===d.difficulty)))},
    ...(getReviewCamp({},d)==='exploration'?[]:[{id:'task-badges',title:'奖励点数',ready:badges.length>=1&&badges.length<=2&&new Set(badges.map(b=>b.id)).size===badges.length&&badges.every(b=>badgeList().some(x=>x.id===b.id)&&Number.isFinite(Number(b.weight))&&Number.isInteger(b.weight)&&b.weight%20===0&&b.weight>=10&&b.weight<=100)&&Math.abs(badges.reduce((sum,b)=>sum+Number(b.weight),0)-100)<0.000001}]),
    ...(getReviewCamp({},d)==='exploration'?[{id:'task-basics',title:'是否需要做任务',ready:d.completionMode==null||EXPLORATION_COMPLETION_MODES.some(mode=>mode.id===d.completionMode)}]:[]),
    {id:'task-materials',title:assessment?'学习材料':'学习材料（选填）',ready:(!assessment||materials.length>0)&&materials.every(validMaterial)},
    ...(getReviewCamp({},d)==='exploration'&&assessment?[{id:'task-files',title:'任务文件',ready:explorationTaskResourceErrors(d).length===0}]:[]),
    ...(assessment?[{id:'task-review',title:'审核方式',ready:['manual','ai'].includes(d.reviewMode)&&(d.reviewMode!=='ai'||(d.passScore!==null&&d.passScore!==undefined&&String(d.passScore).trim()!==''&&Number.isFinite(Number(d.passScore))&&Number(d.passScore)>=0&&Number(d.passScore)<=100))}]:[]),
    ...(assessment&&d.reviewMode==='ai'?[{id:'task-rubric',title:'评分标准',ready:rubric.length>0&&rubric.every(r=>filled(r.name)&&filled(r.description)&&Number.isFinite(Number(r.points))&&Number(r.points)>0)&&Math.abs(rubric.reduce((sum,r)=>sum+Number(r.points),0)-100)<0.000001}]:[]),
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
  const exploration=getReviewCamp({},d)==='exploration';
  const reward=rewardBreakdown(d);
  const checks=getReadiness();
  return `<section class="card overview-card compact-task-preview">
    <div class="overview-body"><div class="preview-meta-line"><span class="category-label">${exploration?`探索营 · ${isPinnedExplorationTask(d)?'固定在毕业码前':`第 ${explorationDisplayOrder(d,store.data.tasks)??'—'} 个展示`}`:`${e(d.publishingDepartment ? departmentLabel(d.publishingDepartment) : '待选择部门')} <span>·</span> ${e(d.difficulty)}`}</span><span class="tag tag-neutral">实时预览</span></div><h3>${e(d.title||'等待你的第一个任务')}</h3>
      <div class="overview-time">${exploration?`${icon('file',14)} ${d.materials.length} 份学习材料${requiresTaskAssessment(d)?` · ${explorationTaskFiles(d).length} 份任务文件`:''}`:`${icon('clock',14)} 预计 ${d.minutes||0} 分钟`} <span>${e(taskCompletionLabel(d))}</span></div>
      ${exploration?'':`<div class="overview-rewards"><div><span class="metric-symbol">XP</span><strong>${format(reward.xp)}</strong><small>经验值</small></div><div>${icon('award',18)}<strong>${format(reward.totalPoints)}</strong><small>徽章点</small></div></div>`}
      <div class="preview-task-access"><span>领取方式</span><strong>直接领取</strong></div>
      ${exploration?'':`<div class="aside-distribution"><h4>徽章点分配</h4><div class="distribution-track">${d.badges.map((b,i)=>`<span class="bg-${i}" data-weight="${b.weight}"></span>`).join('')}</div>${reward.allocations.map((b,i)=>`<div class="distribution-row"><i class="color-dot color-${i}"></i><span>${e(badgeName(b.id))}</span><strong>${format(b.points)}<small> 点</small></strong></div>`).join('')}</div>`}
    </div></section><section class="card checklist-card"><div class="checklist-heading"><h3>发布准备</h3><span>${checks.filter(x=>x.ready).length}/${checks.length}</span></div>${checks.map(({id,title,ready})=>`<button type="button" class="checklist-row ${ready?'complete':'incomplete'}" data-jump-section="${id}" aria-label="定位到${title}，${ready?'已完成':'待完成'}">${icon(ready?'checkCircle':'alert',16)}<span>${title}</span><small>${ready?'已完成':'待完成'}</small>${icon('chevronRight',13)}</button>`).join('')}</section>`;
}
function updateAside() { const aside=$('#editor-aside'); if(aside) aside.innerHTML=renderAside(); }

function bindEditor() {
  const d=store.data.draft;
  $('#save-draft').onclick=async()=>{if(materialUploadsPending){toast('文件正在上传，请完成后再保存。','error');return;}const errors=validateTaskFieldLimits(d);if(errors.length){toast(errors[0],'error');focusSection('task-basics');return;}if(!saveDraft())return;try{await store.saveTask(structuredClone(d));render();toast(isTaskUpdate(d)?'修改已保存为草稿，已发布版本保持不变':'草稿已保存，可在任务库中继续编辑');}catch(error){toast(error.message,'error');}};
  $('#publish-task').onclick=publish;
  $('#sandbox-test')?.addEventListener('click',()=>sandbox.open());
  $('#editor-aside').onclick=event=>{
    const button=event.target.closest('[data-jump-section]');
    if(button)focusSection(button.dataset.jumpSection);
  };
  $('#new-task').onclick=()=>taskWorkflow.start();
  const unavailableCamp = $('[data-camp-unavailable]');
  if (unavailableCamp) unavailableCamp.onclick=()=>toast('暂未开放');
  document.querySelectorAll('[data-requires-task]').forEach(input=>input.onchange=()=>{
    if(materialUploadsPending)return;
    if(explorationCompletionMode(d)!=='assessment')readingCompletionModes.set(d,explorationCompletionMode(d));
    d.completionMode=input.dataset.requiresTask==='true'?'assessment':readingCompletionModes.get(d)||'learning';
    // Keep both resource lists in the browser while the administrator compares modes.
    // Saving a No-task mode removes inactive task resources through taskWrite/backend.
    saveDraft();render();
  });
  function bindFields(root=document) { root.querySelectorAll('[data-field]').forEach(el=>el.addEventListener('input',()=>{
    const key=el.dataset.field;
    if(key==='camp'&&!canConfigureTask({camp:el.value},ui.isSuperAdmin)){toast(EXPLORATION_CONFIGURATION_NOTICE,'error');render();return;}
    d[key]=el.type==='number'?(el.value===''?'':Number(el.value)):el.value;
    if(key==='camp'&&el.value==='novice'){d.difficulty ||= '入门';if(!d.badges?.length)d.badges=[{id:'product',weight:100}];}
    if(key==='camp'&&el.value==='exploration'&&d.order==null)d.order=nextExplorationOrder(store.data.tasks);
    if(key==='camp'&&el.value==='exploration'&&d.completionMode==null)d.completionMode='learning';
    if((key==='title'||key==='summary')&&$(`#${key}-counter`))$(`#${key}-counter`).textContent=`${taskFieldLength(el.value)}/${TASK_FIELD_LIMITS[key]}`;
    saveDraft();
    if (key === 'camp'||key==='completionMode') render();
  }));} bindFields();
  document.querySelectorAll('[data-badge]').forEach(btn=>btn.onclick=()=>{const id=btn.dataset.badge;const index=d.badges.findIndex(b=>b.id===id);if(index>=0)d.badges.splice(index,1);else if(d.badges.length<2)d.badges.push({id,weight:50});if(d.badges.length===1)d.badges[0].weight=100;if(d.badges.length===2)d.badges.forEach((b,i)=>b.weight=i?40:60);saveDraft();render();});
  $('#ratio-slider')?.addEventListener('input',event=>{const value=Math.max(20,Math.min(80,Math.round(Number(event.target.value)/20)*20));event.target.value=String(value);d.badges[0].weight=value;d.badges[1].weight=100-value;event.target.parentElement.dataset.ratio=String(value);event.target.setAttribute('aria-valuetext',`${value}%`);d.badges.forEach((b,i)=>$(`#ratio-weight-${i}`).textContent=`${b.weight}%`);saveDraft();});
  $('#add-link')?.addEventListener('click',()=>{if(d.camp==='exploration'&&d.materials.length>=20){toast('每个任务最多添加 20 份材料','error');return;}editMaterial();});
  $('#add-task-link')?.addEventListener('click',()=>{if(explorationTaskFiles(d).length>=20){toast('每个任务最多添加 20 份任务文件','error');return;}editMaterial(null,{collection:'taskFiles'});});
  $('#material-upload')?.addEventListener('change',event=>{const files=Array.from(event.target.files||[]);event.target.value='';void addMaterialFiles(files);});
  $('#task-file-upload')?.addEventListener('change',event=>{const files=Array.from(event.target.files||[]);event.target.value='';void addMaterialFiles(files,{target:'taskFiles'});});
  $('#rubric-upload')?.addEventListener('change',async event=>{await uploadFiles(event.target.files,'rubricAttachments');render();});
  const editor=$('#editor-primary');
  for(const [zoneId,inputId,target] of [['material-dropzone','material-upload','materials'],['task-file-dropzone','task-file-upload','taskFiles']]){
    const dropzone=$(`#${zoneId}`);
    dropzone?.addEventListener('click',()=>{if(materialUploadsPending){toast('文件正在上传，请稍候再添加。','error');return;}dropzone.focus({preventScroll:true});});
    dropzone?.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();if(!materialUploadsPending)$(`#${inputId}`)?.click();}});
    dropzone?.addEventListener('dragover',event=>{if(!hasTransferredFiles(event.dataTransfer))return;event.preventDefault();event.dataTransfer.dropEffect=materialUploadsPending?'none':'copy';dropzone.classList.toggle('is-dragover',!materialUploadsPending);});
    dropzone?.addEventListener('dragleave',event=>{if(!(event.relatedTarget instanceof Node&&dropzone.contains(event.relatedTarget)))dropzone.classList.remove('is-dragover');});
    dropzone?.addEventListener('drop',event=>{
      dropzone.classList.remove('is-dragover');
      const selection=transferredFiles(event.dataTransfer);if(!selection.hasFiles)return;
      event.preventDefault();event.stopPropagation();void addMaterialFiles(selection.files,{source:'drop',target,errors:selection.errors});
    });
  }
  // This listener belongs to the rendered editor node, so rerendering cannot
  // accumulate document listeners or retain a previous task's draft.
  editor?.addEventListener('paste',event=>{
    if(document.querySelector('.modal')||!isMaterialPasteTarget(event.target))return;
    const selection=transferredFiles(event.clipboardData);if(!selection.hasFiles)return;
    const target=event.target.closest('#task-files')?'taskFiles':'materials';
    event.preventDefault();event.stopPropagation();void addMaterialFiles(selection.files,{source:'paste',target,errors:selection.errors});
  });
  document.querySelectorAll('[data-material-thumbnail]').forEach(image=>image.addEventListener('error',()=>{const holder=image.parentElement;holder.classList.remove('material-thumbnail');holder.innerHTML=icon('file',20);}));
  document.querySelectorAll('[data-view-material]').forEach(b=>b.onclick=()=>viewMaterial(d[b.dataset.materialCollection||'materials'][Number(b.dataset.viewMaterial)]));
  document.querySelectorAll('[data-edit-material]').forEach(b=>b.onclick=()=>editMaterial(Number(b.dataset.editMaterial),{collection:b.dataset.materialCollection||'materials'}));
  document.querySelectorAll('[data-remove-material]').forEach(b=>b.onclick=()=>{d[b.dataset.materialCollection||'materials'].splice(Number(b.dataset.removeMaterial),1);saveDraft();render();});
  $('#add-rubric')?.addEventListener('click',()=>{d.rubric.push({id:crypto.randomUUID(),name:'',points:0,description:''});saveDraft();render();});
  document.querySelectorAll('[data-rubric]').forEach(el=>el.addEventListener('input',()=>{d.rubric[Number(el.dataset.rubric)][el.dataset.key]=el.type==='number'?Number(el.value):el.value;saveDraft();if(el.dataset.key==='points'){const total=d.rubric.reduce((s,r)=>s+Number(r.points||0),0);const tag=$('#rubric-total');if(tag){tag.textContent=`合计 ${total}/100`;tag.className=`tag ${total===100?'tag-green':'tag-red'}`;}}}));
  document.querySelectorAll('[data-remove-rubric]').forEach(b=>b.onclick=()=>{d.rubric.splice(Number(b.dataset.removeRubric),1);saveDraft();render();});
  document.querySelectorAll('[data-remove-rubric-file]').forEach(b=>b.onclick=()=>{d.rubricAttachments.splice(Number(b.dataset.removeRubricFile),1);saveDraft();render();});
  document.querySelectorAll('[name="review-mode"]').forEach(el=>el.onchange=()=>{d.reviewMode=el.value;saveDraft();render();});

}
async function addMaterialFiles(files,options={}) {
  const target=options.target||'materials';
  if(await uploadFiles(files,target,options)){
    render();
    if(options.source==='paste'||options.source==='drop')$(target==='taskFiles'?'#task-file-dropzone':'#material-dropzone')?.focus({preventScroll:true});
  }
}
async function uploadFiles(files,target,{source='select',errors=[]}={}) {
  if(materialUploadsPending){toast('文件正在上传，本次文件尚未添加，请完成后重试。','error');return false;}
  const d=store.data.draft; if(!d[target])d[target]=[];
  const selected=Array.from(files||[]);
  if(!selected.length){errors.forEach(message=>toast(message,'error'));return false;}
  const exploration=['materials','taskFiles'].includes(target)&&getReviewCamp({},d)==='exploration';
  const label=target==='taskFiles'?'任务文件':'材料', statusId=target==='taskFiles'?'#task-file-upload-status':'#material-upload-status';
  const names=new Set(d[target].map(material=>material.name));
  const controls=[...document.querySelectorAll('#editor-primary button,#editor-primary input,#editor-primary select,#editor-primary textarea,#save-draft,#publish-task')].map(element=>({element,disabled:element.disabled}));
  const zone=$(target==='taskFiles'?'#task-file-dropzone':'#material-dropzone');zone?.setAttribute('aria-busy','true');zone?.setAttribute('aria-disabled','true');
  materialUploadsPending=true;
  controls.forEach(({element})=>element.disabled=true);
  let added=0; const failures=[...errors];
  try {
    errors.forEach(message=>toast(message,'error'));
    for(const [index,original] of selected.entries()){
      if(exploration&&d[target].length>=20){const message=`每个任务最多添加 20 份${label}，剩余 ${selected.length-index} 份文件未上传。`;failures.push(message);toast(message,'error');break;}
      try {
        const file=['materials','taskFiles'].includes(target)?normalizeLearningMaterialFile(original,{source,names}):original;
        const status=$(statusId);
        if(status)status.textContent=`正在上传 ${file.name}（${index+1}/${selected.length}），请稍候…`;
        if(exploration){
          d[target].push(await uploadExplorationMaterial(file,{label:target==='taskFiles'?'任务':'学习材料'}));
        }else{
          if(file.size>2*1024*1024)throw new Error(`${file.name} 超过 2 MB，请改用文档链接`);
          const url=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});
          d[target].push({id:crypto.randomUUID(),name:file.name,type:file.type.startsWith('image/')?'image':'file',url,size:file.size,mime:file.type});
        }
        added++;
        saveDraft();
      }catch(error){const message=error.message||`${original?.name||'文件'} 上传失败，请重试`;failures.push(message);toast(message,'error');}
    }
    if(added&&saveDraft())toast(failures.length?`已添加 ${added} 份文件；另有未添加的文件或文件夹：${failures[0]}`:`已添加 ${added} 份文件到当前草稿`,failures.length?'error':'success');
    return added>0;
  }finally{
    materialUploadsPending=false;
    controls.forEach(({element,disabled})=>element.disabled=disabled);
    zone?.removeAttribute('aria-busy');zone?.removeAttribute('aria-disabled');
    const status=$(statusId);if(status)status.textContent='';
  }
}
function viewMaterial(m) {
  const preview=materialImagePreviewUrl(m);
  if(preview){openModal(`<div class="modal-heading"><h2>${e(m.name)}</h2></div><img src="${e(preview)}" alt="${e(m.name)}" class="material-image">`);return;}
  const local=localMaterialUrl(m.url);
  if(local){const a=document.createElement('a');a.href=local;a.download=m.name;a.click();return;}
  if(/^https?:\/\//i.test(m.url||'')){window.open(m.url,'_blank','noopener,noreferrer');return;}
  if(m.url?.startsWith('data:')){const a=document.createElement('a');a.href=m.url;a.download=m.name;a.click();return;}
  openModal(`<div class="modal-heading"><h2>${e(m.name)}</h2><p>这是演示材料。你可以在“学习材料”中上传真实文件或添加文档链接。</p></div>`);
}

function openSubmitPublication(task) {
  const links=taskResourceLinks(task);
  openModal(`<div class="native-publish-confirm"><div class="modal-heading"><h2>提交发布审核</h2><p>${e(task.title)}</p></div>${renderPublishMaterials(task.materials,task)}<div class="notice">提交后由超级管理员审核，通过后才发布给学员。更新已有任务时，原已发布版本继续可用。</div><p id="submit-publication-error" role="alert" class="inline-error" hidden></p><div class="modal-actions"><button class="btn btn-secondary" data-submit-cancel>取消</button><button class="btn btn-primary" data-submit-publication>确认提交审核</button></div></div>`,modal=>{
    const confirm=modal.querySelector('[data-submit-publication]');
    const selected=()=>[...modal.querySelectorAll('[data-verified-link]:checked')].map(el=>links[Number(el.dataset.verifiedLink)]);
    const ready=()=>{confirm.disabled=selected().length!==links.length;};
    modal.querySelectorAll('[data-verified-link]').forEach(el=>el.onchange=ready);ready();
    modal.querySelector('[data-submit-cancel]').onclick=closeModal;
    confirm.onclick=async()=>{
      if(confirm.disabled)return;
      modal.dataset.operationPending='true';modal.querySelectorAll('button,input').forEach(el=>el.disabled=true);
      confirm.textContent='正在提交…';
      try {await service.tasks.submitPublication(task,selected());modal.dataset.operationPending='false';closeModal();render();toast('已提交，等待超级管理员审核');}
      catch(error){modal.dataset.operationPending='false';modal.querySelectorAll('button,input').forEach(el=>el.disabled=false);confirm.textContent='确认提交审核';ready();const msg=modal.querySelector('#submit-publication-error');msg.hidden=false;msg.textContent=error.message;}
    };
  });
}

async function publish() {
  if (!canConfigureTask(store.data.draft,ui.isSuperAdmin)) { toast(EXPLORATION_CONFIGURATION_NOTICE,'error'); return; }
  if(materialUploadsPending){toast('文件正在上传，请完成后再发布。','error');return;}
  if(draftPublication()?.status==='pending'){toast('任务正在等待审核');return;}
  const errors=validateTask(store.data.draft);
  if(errors.length){render();toast(errors[0],'error');const missing=getReadiness().find(x=>!x.ready);if(missing)focusSection(missing.id);return;}
  const launch = $('#publish-task');
  if (launch.disabled) return;
  launch.disabled = true;
  try {
    const savedTask = await store.saveTask(normalizeBadgeWeights(store.data.draft));
    const publishingUpdate = isTaskUpdate(savedTask);
    if(!ui.isSuperAdmin){openSubmitPublication(savedTask);return;}
    const links = taskResourceLinks(savedTask);
    const exploration = savedTask.camp === 'exploration';
    const reviewers = store.members.filter(m=>m.roles.includes('REVIEWER'));
    let key = crypto.randomUUID(), keySelection;
    openModal(`<div class="native-publish-confirm"><div class="modal-heading"><h2>${publishingUpdate?'确认发布更新':'确认发布任务'}</h2><p>${e(savedTask.title)}</p></div>${exploration ? '<div class="notice">探索营任务由超级管理员确认后直接发布，无需另行审核。</div>' : `<label class="form-field"><span class="field-label">内容复核人</span><select id="publish-reviewer"><option value="">请选择审核人</option>${reviewers.map(m=>`<option value="${e(m.id)}">${e(m.name)}</option>`).join('')}</select></label>`}${renderPublishMaterials(savedTask.materials,savedTask)}<div class="notice">${publishingUpdate?'本次更新现有任务，不会新增任务卡。已领取的学员保留原版本，未领取的学员将看到更新后的版本。':'本次发布将新增一张任务卡，学员可查看并领取。'}</div><p class="inline-error" id="publish-error" role="alert" hidden></p><div class="modal-actions"><button class="btn btn-secondary" id="cancel-publish">取消</button><button class="btn btn-primary" id="confirm-publish" disabled>${publishingUpdate?'确认更新':'确认发布'}</button></div></div>`, modal => {
      const reviewer = $('#publish-reviewer',modal), confirm = $('#confirm-publish',modal);
      const selected = () => [...modal.querySelectorAll('[data-verified-link]:checked')].map(el=>links[Number(el.dataset.verifiedLink)]);
      const ready = () => { confirm.disabled = (!exploration && !reviewer?.value) || selected().length !== links.length; };
      if(reviewer) reviewer.onchange = ready;
      modal.querySelectorAll('[data-verified-link]').forEach(el=>el.onchange=ready);
      ready();
      $('#cancel-publish',modal).onclick = closeModal;
      confirm.onclick = async () => {
        if (confirm.disabled) return;
        const selection = JSON.stringify([reviewer?.value,selected()]);
        if (keySelection && keySelection !== selection) key = crypto.randomUUID();
        keySelection = selection;
        modal.dataset.operationPending = 'true';
        modal.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);
        confirm.textContent = '正在发布…';
        const error = $('#publish-error',modal); error.hidden = true;
        try {
          const published = await service.tasks.publish(savedTask,reviewer?.value,selected(),key);
          modal.dataset.operationPending = 'false';
          sandbox.retainForPublishedTask(savedTask,published);
          let draftSaveWarning='';
          try { await taskWorkflow.resetAfterPublish(); }
          catch { draftSaveWarning='任务已成功发布。新建表单的本机草稿暂存未完成，可继续填写，刷新前请先保存草稿。'; }
          render(); toast(publishingUpdate?'任务更新成功':'任务发布成功，已加入任务库');
          openModal(`<div class="publication-result"><div class="publication-check">${icon('check',30)}</div><span class="eyebrow">READY FOR THE JOURNEY</span><h2>${publishingUpdate?'任务更新成功':'任务发布成功'}</h2><p>${e(published.title)}</p><div class="notice">${publishingUpdate?'现有任务已更新，已领取的学员保留原版本。':'新任务已发布，学员可在对应营地查看。'}</div>${draftSaveWarning?`<p class="notice" role="status">${e(draftSaveWarning)}</p>`:''}<div class="modal-actions"><button class="btn btn-secondary" id="view-published-task">查看任务</button><button class="btn btn-primary" id="new-next-task">新建下一个任务</button></div></div>`,result=>{
            $('#view-published-task',result).onclick=()=>openTask(published,store,ui);
            $('#new-next-task',result).onclick=()=>taskWorkflow.start();
          });
        } catch (err) {
          modal.dataset.operationPending = 'false';
          modal.querySelectorAll('button,input,select').forEach(el=>el.disabled=false);
          confirm.textContent = publishingUpdate?'确认更新':'确认发布'; ready(); error.textContent=err.message; error.hidden=false;
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
  if (refreshing || document.hidden) return;
  refreshing = true;
  try { await store.refresh(); if(page==='academy'&&academy.canRefresh()&&!document.querySelector('.modal')&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))await academy.activate(); if (!document.querySelector('.modal') && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName) && (page === 'review' || page === 'library' || page === 'publications' || (page==='publish'&&draftPublication()))) render(); }
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
