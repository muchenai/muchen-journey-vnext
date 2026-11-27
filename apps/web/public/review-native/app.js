import {createKnowledgeStore} from './knowledge-store.js?v=20261103-module-publication';
import {createKnowledgeController} from './knowledge.js?v=20261103-module-publication';
import {createGuildStore} from './guild-store.js?v=20261028-server';
import {createGuildController} from './guild.js?v=20261028-server';
import {createPublicationReviewController} from './publication-review.js?v=20261127-task-management';
import { createTaskWorkflow, isTaskUpdate } from './task-workflow.js?v=20261127-member-publication';
import {createMedalsApi} from './medals-api.js?v=20261028-publication-local';
import {createMedalsController} from './medals.js?v=20261103-badge-layout-fix';
import { confirmPublicationFields, renderPublishMaterials } from './publish-materials.js';
import {isUploadVideo, uploadTaskVideo} from './course-asset-upload.js';
import { uploadExplorationMaterial, localMaterialUrl, materialSizeLabel, materialImagePreviewUrl, materialVideoPreviewUrl } from './exploration-material-files.js';
import { hasTransferredFiles, transferredFiles, normalizeLearningMaterialFile, isMaterialPasteTarget } from './material-upload-input.js';
import { normalizeRubricFile } from './rubric-materials.js?v=20261118-document-rubric';
import {ANSWER_DOCUMENT_DIMENSION, usesAnswerDocumentRubric, rubricScoreTotal, rubricDimensionErrors} from './rubric-policy.js?v=20261118-document-rubric';
import {createRubricLinkEditor, renderRubricAttachments} from './rubric-link-editor.js?v=20261118-answer-link';
import { nextExplorationOrder, isPinnedExplorationTask, explorationDisplayOrder } from './exploration-order.js';
import { EXPLORATION_COMPLETION_MODES, explorationCompletionMode, requiresTaskAssessment, taskCompletionLabel, explorationTaskFiles, explorationTaskResourceErrors, taskResourceLinks } from './exploration-completion.js';
import { BADGES, DIFFICULTY_PRESETS, REVIEW_CAMPS, getReviewCamp, getSubmissionStatus, applyDifficultyPreset, normalizeBadgeWeights, escapeHtml as e, icon, rewardBreakdown, validateBadgeWeights, validateTask } from './core.js?v=20261118-document-rubric';
import {canEditTask} from './task-publication-access.js?v=20261127-task-management';
import { ApiStore, newDraft, createJourneyService, request } from './native-api.js?v=20261127-task-management';
import { createSandboxController } from './sandbox.js?v=20261118-document-rubric';
import { renderReview, bindReview, openSubmission } from './review.js?v=20261026-passed-tab';
import { renderLibrary, bindLibrary, openTask } from './library.js?v=20261127-task-management';
import { openCertificationCenter } from './certification-center.js?v=20261127-member-publication';
import { createAcademyWorkspace } from './academy-workspace.js?v=20261127-task-management';
import { bindOfflineExperience } from './offline-experience.js?v=20261126-single';
import { renderVillagePublishType } from './publish-content-type.js?v=20261126-task-delivery';
import { isInviteLoggedIn, getCurrentInviteUser, clearInviteSession, renderInviteLogin, bindInviteLogin, onInviteSessionChange } from './native-api.js?v=20261127-task-management';
import { createAcademyStore } from './native-api.js?v=20261127-task-management';
import { createAcademyController } from './academy.js?v=20261105-sources';

import {taskCategoryOptions, departmentLabel, isTaskCategory} from './publishing-departments.js';
import { createMaterialEditor } from './material-editor.js';
import { isMaterialLink } from './material-validation.js';
import { TASK_FIELD_LIMITS, taskFieldLength, taskIssue, validateTaskFieldLimits } from './task-field-limits.js';
import { bindFieldFeedback, clearFieldError, showFieldError } from './field-feedback.js';
import { showTaskIssues } from './task-form-feedback.js';


const store = await ApiStore.create().catch(error => { document.querySelector('#app').innerHTML = `<div class="card empty-state"><strong>${e(error.message)}</strong><a href="/review/login">重新登录</a></div>`; throw error; });
const service = createJourneyService({ store, getCurrentUser: getCurrentInviteUser });
const editMaterial = createMaterialEditor({store,openModal,closeModal,saveDraft,refresh:render,toast});
const editRubricLink = createRubricLinkEditor({store,request,openModal,closeModal,saveDraft,refresh:render,toast});
let materialUploadsPending = false;
const readingCompletionModes = new WeakMap();
const villagePublishPage = 'publish/village-courses';
const legacyTaskPage = 'publish/saved-task';
function initialPage() {
  const hash = location.hash.slice(1);
  if (hash === 'experience' && store.capabilities?.canGrantExperience !== true) {
    const url = new URL(location.href);
    url.hash = 'review';
    url.searchParams.delete('demo');
    history.replaceState(null, '', url);
    return 'review';
  }
  if (hash.startsWith('medals')) return 'medals';
  if (hash === legacyTaskPage) return 'publish';
  if (['village-courses',villagePublishPage,villagePublishPage+'/list'].includes(hash)) return villagePublishPage;
  const pages = ['publish','review','publications','library','knowledge','guild','academy','experience'];
  const target = pages.includes(hash) ? hash : 'publish';
  const draft = store.data.draft;
  if (target === 'publish' && (draft.title || draft.summary || store.getTask(draft.id))) return 'publish';
  return target === 'publish' && getReviewCamp({},store.data.draft)==='novice' ? villagePublishPage : target;
}
let page = initialPage();
let publishCamp = page === villagePublishPage ? 'novice' : getReviewCamp({},store.data.draft);
let reviewCamp = 'novice';
try { const savedCamp = localStorage.getItem('journey_admin_review_camp'); if (REVIEW_CAMPS.some(camp => camp.id === savedCamp)) reviewCamp = savedCamp; } catch {}
const $ = (s, root = document) => root.querySelector(s);
const taskWorkflow = createTaskWorkflow({store,newDraft,openModal,closeModal,showEditor:isCopy=>{const switching=page===villagePublishPage && store.data.draft.camp==='exploration'; if(switching)shareCampFields(villageCourses.publicationCourse(),store.data.draft,false); publishCamp=getReviewCamp({},store.data.draft);navigate('publish',isCopy || publishCamp==='novice'?'saved-task':undefined,switching || page===villagePublishPage);},toast});
const ui = { denyExperience, get canConfigureExperience() { return store.capabilities?.canConfigureExperience === true; }, toast, refresh: render, openModal, closeModal, navigate, editTask, icon, service, get currentUser() { return getCurrentInviteUser(); }, get reviewCamp() { return reviewCamp; }, get isSuperAdmin() { return getCurrentInviteUser()?.accessRole === 'super_admin'; }, get canGrantSuperAdmins() { return store.capabilities?.canGrantSuperAdmins === true; }, newTask: () => taskWorkflow.start(), copyTask: task => taskWorkflow.start(task) };
const knowledgeStore=createKnowledgeStore({getCurrentUser:getCurrentInviteUser});
const knowledge=createKnowledgeController({knowledge:knowledgeStore,ui});
const guildStore=createGuildStore({getCurrentUser:getCurrentInviteUser});
const guild=createGuildController({guild:guildStore,ui});
let guildError='',guildLoading=false,guildLoaded=false;
async function loadGuild(){guildLoading=true;guildError='';try{await guildStore.ready();guildLoaded=true;}catch(error){guildError=error.message;}finally{guildLoading=false;if(page==='guild')render();}}
const academyStore = createAcademyStore({ getCurrentUser: getCurrentInviteUser });
const legacyAcademy = createAcademyController({ academy: academyStore, ui });
const academy = createAcademyWorkspace({ ui, legacy:legacyAcademy });
const villageCourses = createAcademyWorkspace({ ui:Object.assign(Object.create(ui),{refresh:()=>{if(page===villagePublishPage)render();}}), legacy:legacyAcademy, scope:'village', onNewPublication:openVillagePublicationChooser });
function courseWorkspace(tab) { return tab === 'academy' ? academy : tab === villagePublishPage ? villageCourses : null; }
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
const sandbox = createSandboxController({ store, service, openModal, toast, onChange: () => updateAside(),
  onConfigurationError: issues => {
    closeModal();
    showTaskIssues($('#editor-primary'), issues, $('#sandbox-test'));
  },
});

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
  const previousModal = $('.modal');
  if (previousModal) previousModal.dispatchEvent(new Event('review-close'));
  else returnFocus = document.activeElement;
  $('#modal-root').innerHTML = `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-label="详情"><button class="modal-close icon-btn" aria-label="关闭">${icon('close')}</button><div class="modal-content">${html}</div></section></div>`;
  document.body.classList.add('modal-open');
  $('.modal-close').onclick = closeModal;
  $('.modal-backdrop').onclick = event => { if (event.target.classList.contains('modal-backdrop')) closeModal(); };
  onReady?.($('.modal'));
  $('.modal').querySelector('input,button,textarea,select')?.focus();
}
function closeModal() {
  if ($('.modal[data-operation-pending="true"], .cert-center [role="tabpanel"][data-operation-pending="true"]')) return;
  $('.modal')?.dispatchEvent(new Event('review-close'));
  $('#modal-root').innerHTML = '';
  document.body.classList.remove('modal-open');
  if (returnFocus?.isConnected) returnFocus.focus?.();
  else if (returnFocus?.id === 'cert-btn') $('#cert-btn')?.focus();
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
function navigate(next, courseAction, keepPosition = false) {
  if(next==='experience' && store.capabilities?.canGrantExperience!==true)next='review';
  if(next==='publish' && courseAction===undefined && location.hash==='#'+legacyTaskPage) courseAction='saved-task';
  if(next==='publish' && courseAction!=='saved-task' && publishCamp==='novice') next=villagePublishPage;
  if (courseWorkspace(page)?.isBusy?.()) { toast('课程操作正在进行，请稍候。'); return; }
  if (materialUploadsPending) { toast('学习材料正在上传，请稍候。'); return; }
  if (page === 'knowledge') knowledge.reset();
  if (page === 'guild') guild.deactivate();
  if (page !== next) courseWorkspace(page)?.deactivate();
  const url = new URL(location.href);
  if(next!=='experience' && (page==='experience' || url.hash==='#experience'))url.searchParams.delete('demo');
  page = next;
  if(next===villagePublishPage) publishCamp='novice';
  if(next==='publish') publishCamp=getReviewCamp({},store.data.draft);
  url.hash = next===villagePublishPage && courseAction==='list' ? next+'/list' :
    next==='publish' && courseAction==='saved-task' && publishCamp==='novice' ? legacyTaskPage : next;
  history.replaceState(null, '', url);
  if (next === villagePublishPage && (courseAction === 'required' || courseAction === 'elective')) void villageCourses.startPublishing(courseAction === 'required');
  else if (next === villagePublishPage && courseAction === 'list') void villageCourses.showCourseList();
  else if (next === villagePublishPage) void villageCourses.resumePublishing();
  else void courseWorkspace(next)?.activate();
  if (next === 'guild') void loadGuild();
  if (next === 'medals') {
    medals.reset();
    void economy.refresh().catch(error => toast(error.message,'error')).finally(() => { if (page === 'medals') render(); });
  }
  render();
  if (!keepPosition) window.scrollTo({ top: 0, behavior: 'smooth' });
}
function editTask(task) {
  if (!store.operatorId) { toast('当前账号没有任务配置权限。','error'); return; }
  if (!canEditTask(task, store)) { toast('当前账号没有编辑此任务的权限。','error'); return; }
  store.data.draft = normalizeBadgeWeights(task); store.save(); navigate('publish','saved-task');
}
function saveDraft() {
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

const experienceNavItem = {id:'experience',symbol:'users',label:'经验管理'};
function navButton(item,active,count=0) {
  return `<div class="nav-group"><button type="button" class="nav-item ${item.camp ? 'review-camp-primary ' : ''}${active ? 'active' : ''}" aria-label="${item.label}" title="${item.title || item.label}" ${item.camp ? `data-review-camp="${item.camp}"` : `data-page="${item.id}"`} ${active ? 'aria-current="page"' : ''}>${icon(item.symbol,19)}<span>${item.label}</span>${count ? `<span class="nav-count">${count}</span>` : ''}</button></div>`;
}

function denyExperience() {
  store.capabilities.canGrantExperience = false;
  syncExperienceAccess();
}

function syncExperienceAccess() {
  const nav = $('.sidebar nav');
  const button = nav?.querySelector('[data-page="experience"]');
  if (store.capabilities?.canGrantExperience !== true) {
    button?.closest('.nav-group')?.remove();
    if (page === 'experience') navigate('review');
  } else if (nav && !button) {
    nav.insertAdjacentHTML('beforeend', navButton(experienceNavItem,false));
    nav.querySelector('[data-page="experience"]').onclick = () => navigate('experience');
  }
  if (!ui.canConfigureExperience && $('#cert-tab-experience')) closeModal();
}

function shell(content) {
  const currentUser = getCurrentInviteUser();
  const pendingInCamp = camp => store.data.submissions.filter(s => { const task=store.getTask(s.taskId)||{}; return !s.supersededBy&&getReviewCamp(s,task)===camp&&getSubmissionStatus(s,task)==='pending'; }).length;
  const pending = REVIEW_CAMPS.reduce((sum,camp)=>sum+pendingInCamp(camp.id),0);
  const labels = {experience:'经验管理',knowledge:'知识库管理',guild:'交付线公会',publish:'发布任务配置',review:`${REVIEW_CAMPS.find(camp=>camp.id===reviewCamp).label}审核`,library:'任务库',academy:'AI学院',medals:'徽章系统',publications:ui.isSuperAdmin?'发布审核':'我的发布'};
  const navPage = page === villagePublishPage ? 'publish' : page;
  const navigation = [
    { id: 'publish', symbol: 'grid', label: '发布任务配置' },
    {id:'publications',symbol:'checkCircle',label:ui.isSuperAdmin?'发布审核':'我的发布',title:ui.isSuperAdmin?'审核管理员提交发布的任务':'我的发布'},
    ...REVIEW_CAMPS.map(camp => ({ id: 'review', camp: camp.id, symbol: 'checkCircle', label: `${camp.label}审核` })),
    { id: 'academy', symbol: 'book', label: 'AI学院' },
    {id:'guild',symbol:'users',label:'交付线公会'},
    { id: 'library', symbol: 'library', label: '任务库' },
    { id: 'medals', symbol: 'award', label: '徽章系统' },
    {id:'knowledge',symbol:'library',label:'知识库管理'},
    ...(store.capabilities?.canGrantExperience === true ? [experienceNavItem] : []),
  ].map(item => {
    const active = navPage === item.id && (!item.camp || reviewCamp === item.camp);
    const count = item.camp ? pendingInCamp(item.camp) : item.id==='publications' ? publicationReview.badgeCount() : 0;
    return navButton(item,active,count);
  }).join('');
  return `<header class="topbar"><a href="#" class="brand" aria-label="JOURNEY首页"><img src="./journey-logo-119.svg" alt="" width="34" height="34"><span class="brand-wordmark">JOURNEY <span class="brand-sub">管理系统</span></span></a><div class="topbar-right"><a class="btn btn-secondary btn-sm" href="/app?view=village" target="_blank" rel="noopener">学员端 ${icon('external',14)}</a><button id="theme-toggle" class="theme-toggle" type="button" aria-label="${document.documentElement.dataset.theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'}" title="${document.documentElement.dataset.theme === 'dark' ? '切换为浅色模式' : '切换为深色模式'}">${themeToggleContent()}</button>${ui.isSuperAdmin || ui.canConfigureExperience ? `<button id="cert-btn" class="cert-btn">${icon('shield',16)} 认证</button>` : ''}<button id="notification-btn" class="icon-btn notification-btn" aria-label="审核通知">${icon('bell',19)}${pending?'<i></i>':''}</button><div class="header-user"><div class="avatar avatar-small">${e((currentUser?.name || '成').slice(0,1))}</div><span>${e(currentUser?.name || '学院成员')}</span><small class="muted">${ui.isSuperAdmin?'超级管理员':store.operatorId?'普通管理员':'审核员'}</small></div><button id="logout-btn" class="logout-btn" type="button">退出登录</button></div></header>
  <aside class="sidebar"><nav aria-label="主导航">${navigation}</nav><div class="sidebar-bottom"><button class="guide-entry" id="guide-btn" type="button">${icon('book',20)}<span>使用指南</span></button></div></aside>
  <div class="app-main"><main class="main-content" aria-label="${labels[navPage]}">${content}</main></div>`;
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
  try { content = page===villagePublishPage ? renderVillageCoursePublication() : page==='experience' ? '<p role="status">正在读取经验管理数据…</p>' : page==='knowledge' ? knowledge.render() : page==='guild' ? (guildError ? `<div class="gd-empty" role="alert">${e(guildError)}<button class="btn" data-page="guild">重新加载</button></div>` : !guildLoaded || guildLoading ? '<div class="gd-empty">正在加载公会…</div>' : guild.render()) : page === 'publications' ? publicationReview.render() : page === 'medals' ? (economy.loading ? '<div class="md-empty">正在读取徽章…</div>' : economy.error ? `<div class="md-empty" role="alert">${e(economy.error)}<button class="btn btn-secondary" data-page="medals">重新加载</button></div>` : medals.render()) : page === 'academy' ? academy.render() : page === 'review' ? renderReview(store,ui) : page === 'library' ? renderLibrary(store,ui) : renderEditor(); }
  catch (err) { console.error(err); content = `<div class="card empty-state">页面暂时无法显示，请刷新重试。</div>`; }
  $('#app').innerHTML = shell(content);
  document.documentElement.style.setProperty('--editor-header-height','0px');
  document.querySelectorAll('[data-page]').forEach(btn => btn.onclick = () => navigate(btn.dataset.page));
  document.querySelectorAll('[data-review-camp]').forEach(btn => btn.onclick = () => { reviewCamp=btn.dataset.reviewCamp; try { localStorage.setItem('journey_admin_review_camp',reviewCamp); } catch {} navigate('review'); });
  $('.brand').onclick = event => { event.preventDefault(); navigate('publish'); };
  $('#cert-btn')?.addEventListener('click', () => {
    const preferred = page === 'experience' ? 'experience' : 'members';
    openCertificationCenter(store,ui,{preferred,onPermissionsChanged:refreshPermissionViews});
  });
  $('#theme-toggle').onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true);
  $('#notification-btn').onclick = () => { const submission=store.data.submissions.find(s=>!s.supersededBy&&getSubmissionStatus(s,store.getTask(s.taskId)||{})==='pending'); if(submission)reviewCamp=getReviewCamp(submission,store.getTask(submission.taskId)||{}); navigate('review'); };
  $('#logout-btn').onclick = async () => { try { await clearInviteSession(); academy.reset(); villageCourses.reset(); } catch (error) { toast(error.message,'error'); } };
  $('#guide-btn').onclick = () => openModal(`<div class="modal-heading"><h2>使用指南</h2></div><div class="guide-list">${[['填写基础信息','填写任务标题与简述。新手村普通任务可选择多类徽章点，按整数百分比分配，合计为 100%。'],['添加学习材料','添加文档链接、图片或文件。'],['选择审核方式与评分标准','有固定答案选择 AI 自测并填写评分标准；无固定答案选择人工审核。'],['查看右侧预览','AI 自测任务可选用沙盒试测，普通管理员提交后由超级管理员审核，超级管理员可直接发布。']].map(([title,description])=>`<div><section><strong>${title}</strong><p>${description}</p></section></div>`).join('')}</div><div class="notice">任务、提交和审核记录来自本地服务。编辑中的草稿保存在当前账号的浏览器中。探索营 AI 自测达到配置的通过分数后自动完成；人工审核任务由审核人确认，新手村沿用原有任务流程。</div>`);
  if (page === 'publish') {bindEditor();bindVillagePublishType();if(draftPublication()?.status==='pending'){$('.main-content').querySelectorAll('input,textarea,select,button').forEach(el=>el.disabled=true);$('#new-task').disabled=false;$('#publish-task').textContent='待审核';}}
  else if(page==='experience')void bindOfflineExperience($('.main-content'),ui);
  else if(page===villagePublishPage){bindVillagePublishType();villageCourses.bind($('.main-content'));}
  else if(page==='knowledge')knowledge.bind($('.main-content'));
  else if(page==='guild'){if(guildLoaded&&!guildLoading&&!guildError)guild.bind($('.main-content'));else if(!guildLoading&&!guildError)void loadGuild();}
  else if (page === 'publications') publicationReview.bind($('.main-content'));
  else if (page === 'medals') medals.bind($('.main-content'));
  else if (page === 'academy') academy.bind($('.main-content'));
  else if (page === 'review') bindReview($('.main-content'),store,ui);
  else bindLibrary($('.main-content'),store,ui);
}

function refreshPermissionViews(change) {
  if (Array.isArray(change?.issuers)) {
    store.capabilities.canGrantExperience = change.issuers.includes(store.actor.id);
    syncExperienceAccess();
  }
  void academy.refreshPermissions?.();
  void villageCourses?.refreshPermissions();
  void refreshRecords(true);
}

function openVillagePublicationChooser() {
  const fields = renderCampField('novice','data-course-camp') + renderVillagePublishType(null);
  openModal(`<div class="modal-heading"><h2 id="village-create-title">新建发布</h2></div><div class="modal-body form-grid">${fields}</div>`, modal => {
    modal.setAttribute('aria-labelledby','village-create-title');
    modal.querySelectorAll('[data-publish-kind]').forEach(input => {
      input.onchange = () => {
        if (!input.checked) return;
        closeModal();
        if (input.value === 'required') navigate(villagePublishPage,'required');
        else void taskWorkflow.start(null,'novice');
      };
    });
    const exploration = modal.querySelector('[data-course-camp][value="exploration"]');
    if (!exploration.disabled) exploration.onchange = () => {
      closeModal();
      void taskWorkflow.start(null,'exploration');
    };
  });
}

function renderVillageCoursePublication() {
  const course = villageCourses.publicationCourse();
  if (!course) return villageCourses.render();
  const kind = villageCourses.currentCourseKind();
  const busy = villageCourses.isBusy();
  const camps = renderCampField('novice','data-course-camp',busy);
  const config = `<section class="card" aria-label="基础信息">${cardHeader('基础信息',`<div class="basics-header-actions"><span class="required-note"><i>*</i> 为必填项</span><button type="button" class="btn btn-secondary btn-sm" data-village-course-list ${busy?'disabled':''}>管理课程</button></div>`)}<fieldset class="card-body form-grid course-basic-fields" ${busy?'disabled':''}>${renderPublicationFields(course,true)}${camps}${kind==='elective' && course.id ? '<span class="field-label">历史选学课程</span>' : renderVillagePublishType(kind,busy)}</fieldset></section>`;
  return `<div class="editor-layout village-course-publication"><form class="editor-primary" id="village-publication-form" data-aw-editor novalidate><div class="notice" role="status">发布后，学员可在新手村查看学习材料，完成对应任务。</div>${config}${villageCourses.render({externalControls:true})}</form>
    <aside class="editor-aside" data-village-course-preview aria-label="课程发布预览">${villageCourses.renderPublishPreview()}</aside></div>${villageCourses.renderPublishActions()}`;
}
// Share the common fields of a new publication while keeping existing records separate.
let linkedCourse, linkedTaskId;
function shareCampFields(course,task,toVillage) {
  if (!course || course.id || store.getTask(task.id) || isTaskUpdate(task)) return;
  const target = toVillage ? course : task, source = toVillage ? task : course;
  if ((course!==linkedCourse || task.id!==linkedTaskId) && (target.title || target.summary)) return;
  Object.assign(target,{title:source.title,summary:source.summary});
  linkedCourse=course; linkedTaskId=task.id;
}
async function switchToVillage(radio,task) {
  if(materialUploadsPending){radio.checked=false;radio.closest('fieldset').querySelector('[value="exploration"]').checked=true;toast('学习材料正在上传，请稍候。');return;}
  await villageCourses.resumePublishing();
  if (!radio.isConnected || !radio.checked || page!=='publish') return;
  shareCampFields(villageCourses.publicationCourse(),task,true);
  navigate(villagePublishPage,undefined,true);
  document.querySelector('[data-course-camp]:checked')?.focus({preventScroll:true});
}
function bindVillagePublishType() {
  document.querySelectorAll('[data-publish-kind]').forEach(input => {
    input.onchange=()=>{
      if(!input.checked) return;
      if(input.value==='required') {
        if(materialUploadsPending){render();toast('学习材料正在上传，请稍候。');return;}
        navigate(villagePublishPage,'required',true);
      } else {
        const task=store.data.draft;
        if(task.camp==='novice' && !task.required && !isTaskUpdate(task)){
          const course=villageCourses.publicationCourse();
          if(course && !course.id && !store.getTask(task.id) && !task.title && !task.summary && course.title.length<=60 && course.summary.length<=400){
            Object.assign(task,{title:course.title,summary:course.summary});
            store.save();
          }
          navigate('publish','saved-task',true);
        } else {
          const selected=document.querySelector('[data-publish-kind="required"]');
          if(selected) selected.checked=true;
          void taskWorkflow.start(null,'novice');
        }
      }
    };
  });
  const list = $('[data-village-course-list]');
  if(list) list.onclick = ()=>navigate(villagePublishPage,'list');
  const exploration = $('[data-course-camp][value="exploration"]');
  if(exploration) exploration.onchange = () => {
    $('[data-course-camp][value="novice"]').checked = true;
    if(getReviewCamp({},store.data.draft)==='exploration') {shareCampFields(villageCourses.publicationCourse(),store.data.draft,false); navigate('publish','saved-task',true); document.querySelector('[data-field="camp"]:checked')?.focus({preventScroll:true});}
    else void taskWorkflow.start(null,'exploration');
  };
}
function draftPublication() {return store.getTask(store.data.draft.id)?.publication || store.data.draft.publication;}
function renderEditor() {
  const publication=draftPublication();
  const publicationNote=publication?.status==='pending'?'任务已提交，等待超级管理员审核。审核期间暂不能编辑；已发布版本保持不变。':publication?.status==='rejected'?`发布申请已退回：${e(publication.comment)}。修改后可重新提交。`:!ui.isSuperAdmin?'普通管理员提交后，由超级管理员审核通过再发布。':'';
  return `${publicationNote?`<div class="notice publication-editor-note" role="status">${publicationNote}</div>`:""}<div class="editor-layout"><div class="editor-primary" id="editor-primary"><div class="notice" role="status">${isTaskUpdate(store.data.draft) ? (store.data.draft.status==='archived' ? '正在编辑已下架任务。发布更新后将重新开放领取。' : '正在编辑已发布任务。发布更新会更新现有任务，不会新增任务卡；保存草稿不影响当前已发布版本。') : publication?.status==='rejected' ? '正在修改退回的任务。重新提交仍使用原任务，不会创建重复任务。' : '正在创建新任务。发布后将在学员端新增一张任务卡。'}</div>${renderBasics()}${renderMaterials()}${renderTaskFiles()}${renderScoring()}</div><aside class="editor-aside" id="editor-aside">${renderAside()}</aside></div>
    <div class="editor-actionbar"><div id="saved-status">${icon('checkCircle',14)} 草稿已保存 <span class="muted">· 仅当前浏览器</span></div><div class="action-buttons"><button class="btn btn-plain" id="save-draft">保存草稿</button>${requiresTaskAssessment(store.data.draft)&&store.data.draft.reviewMode==='ai'?`<button class="btn btn-secondary" id="sandbox-test">${icon('sparkles',16)} 沙盒试测</button>`:''}<button class="btn btn-primary" id="publish-task">${icon('send',16)} ${ui.isSuperAdmin?(isTaskUpdate(store.data.draft)?'发布更新':'发布新建任务'):'提交审核'}</button></div></div>`;
}
function cardHeader(title,right='') {
  return `<div class="card-header"><div class="section-title"><h2>${title}</h2></div>${right}</div>`;
}
function renderCampField(selected,attribute,busy=false) {
  return `<fieldset class="form-field full camp-field"><legend class="field-label">所属营地</legend><div class="camp-options">${REVIEW_CAMPS.map(camp=>`<label class="camp-option"><input type="radio" name="task-camp" ${attribute} value="${camp.id}" ${selected===camp.id?'checked':''} ${busy?'disabled':''}><span>${camp.label}</span></label>`).join('')}</div></fieldset>`;
}
function renderPublicationFields(d, course = false) {
  const limit = course ? 150 : 60;
  const attrs = key => course ? `name="${key}"` : `data-field="${key}"`;
  return `<label class="form-field full"><span class="field-label">${course?'名称':'任务标题'} <i>*</i></span><div class="input-counter"><input ${attrs('title')} value="${e(d.title)}" maxlength="${limit}" placeholder="填写清晰、具体的名称"><span id="title-counter">${d.title.length}/${limit}</span></div></label>
    <label class="form-field full"><span class="field-label">${course?'简介':'任务简述 <i>*</i>'}</span><textarea ${attrs('summary')} rows="3" maxlength="${course?2000:400}" placeholder="简要介绍背景与学习目标">${e(d.summary)}</textarea><span class="field-hint">让学员快速了解：要做什么，以及为什么做。</span></label>`;
}
function renderBasics() {
  const d = store.data.draft;
  const exploration = getReviewCamp({}, d) === 'exploration';
  const pinned = isPinnedExplorationTask(d);
  return `<section class="card" id="task-basics" tabindex="-1" aria-label="基础信息">${cardHeader('基础信息',`<div class="basics-header-actions"><span class="required-note"><i>*</i> 为必填项</span><button class="btn btn-secondary btn-sm" id="new-task">${icon('plus',15)} 新建任务</button></div>`)}<div class="card-body form-grid">
    <label class="form-field full"><span class="field-label">任务标题 <i>*</i></span><div class="input-counter"><input data-field="title" value="${e(d.title)}" maxlength="${TASK_FIELD_LIMITS.title}" placeholder="给任务起一个清晰、具体的名字"><span id="title-counter">${taskFieldLength(d.title)}/${TASK_FIELD_LIMITS.title}</span></div></label>
    <label class="form-field full"><span class="field-label">任务简述 <i>*</i></span><textarea data-field="summary" rows="3" maxlength="${TASK_FIELD_LIMITS.summary}" placeholder="简要介绍任务背景与学习目标">${e(d.summary)}</textarea><span class="field-hint task-summary-hint"><span>让学员快速了解：要做什么，以及为什么做。</span><span id="summary-counter">${taskFieldLength(d.summary)}/${TASK_FIELD_LIMITS.summary}</span></span></label>
    ${renderCampField(getReviewCamp({},d),'data-field="camp"')}
    ${exploration ? `<label class="form-field full"><span class="field-label">任务排序${pinned?'':' <i>*</i>'}</span>${pinned?'<input type="text" value="固定在毕业码前" readonly aria-label="任务排序：固定在毕业码前"><span class="field-hint">培训签退固定为倒数第二项，新增普通任务自动排在它前面。</span>':`<input data-field="order" type="number" min="1" max="9999" step="1" required value="${e(d.order ?? 1)}" placeholder="例如：1"><span class="field-hint">发布后按此位置插入，后续普通任务自动顺延；培训签退固定在毕业码前，超出普通任务数量时插入培训签退前。${Number.isInteger(d.publishedOrder)?` 当前已发布排序：第 ${d.publishedOrder} 个。`:''}</span>`}</label>` : ''}
    ${exploration ? `<fieldset class="form-field full exploration-task-choice"><legend class="field-label">是否需要做任务 <i>*</i></legend><div class="review-options">${[[false,'不需要','阅读学习材料后即可完成'],[true,'需要','阅读学习材料后，还需完成题目并提交成果']].map(([required,label,description])=>`<label class="review-option ${requiresTaskAssessment(d)===required?'selected':''}"><input type="radio" name="requires-task" data-requires-task="${required}" ${requiresTaskAssessment(d)===required?'checked':''}><div><strong>${label}</strong><p>${description}</p></div><span class="radio-circle"></span></label>`).join('')}</div><span class="field-hint">任务文件可以包含选择题、解答题等；学习材料和任务文件分别添加。</span></fieldset>${!requiresTaskAssessment(d)?`<label class="form-field full"><span class="field-label">完成方式 <i>*</i></span><select data-field="completionMode">${EXPLORATION_COMPLETION_MODES.filter(mode=>mode.id!=='assessment').map(mode=>`<option value="${mode.id}" ${explorationCompletionMode(d)===mode.id?'selected':''}>${mode.label}</option>`).join('')}</select><span class="field-hint">${e(EXPLORATION_COMPLETION_MODES.find(mode=>mode.id===explorationCompletionMode(d)).description)}</span></label>`:''}` : ''}
    ${!exploration && !d.required ? renderVillagePublishType('elective') : ''}
    ${exploration ? '' : `<label class="form-field"><span class="field-label">所属部门 / 分类标签 <span class="required">*</span></span><select data-field="publishingDepartment" required>${taskCategoryOptions(d.publishingDepartment)}</select></label>
    <label class="form-field"><span class="field-label">任务奖励经验值 <i>*</i></span><input data-field="xp" type="number" min="0" max="1000000" step="1" required value="${e(d.xp ?? '')}" placeholder="填写经验值"></label>`}

  </div></section>
  ${exploration ? '' : `<section class="card" id="task-badges" tabindex="-1" aria-label="奖励点数类型">${cardHeader('奖励点数类型',`<span class="subtle-label">已选 ${d.badges.length} 类</span>`)}<div class="card-body"><div class="badge-selector">${badgeList().map(b=>{const chosen=d.badges.some(x=>x.id===b.id);return `<button class="badge-option ${chosen?'selected':''}" type="button" data-badge="${b.id}" aria-pressed="${chosen}">${icon('award',16)}<span>${e(badgeName(b.id))}</span>${chosen?icon('check',14):''}</button>`}).join('')}</div>${renderRatio()}</div></section>`}`;
}
function renderRatio() {
  const d=store.data.draft;
  if (!d.badges.length) return `<div class="notice reward-selection-notice">请选择至少一类奖励点数。</div>`;
  const total = d.badges.reduce((sum, badge) => sum + Number(badge.weight), 0);
  return `<div class="ratio-section"><div class="ratio-heading"><span>徽章点占比</span><strong id="ratio-total">合计 ${total}% / 100%</strong></div><div class="form-grid">${d.badges.map((badge,index)=>`<label class="form-field"><span class="field-label">${e(badgeName(badge.id))}</span><div class="input-suffix"><input type="number" min="1" max="100" step="1" data-badge-weight="${index}" value="${e(badge.weight)}" ${d.badges.length===1?'readonly':''}><span>%</span></div></label>`).join('')}</div></div>`;
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
  return `<section class="card" id="task-materials" tabindex="-1" aria-label="学习材料">${cardHeader(d.camp==='novice'?'学习材料（选填）':'学习材料',`<span class="subtle-label">已添加 ${d.materials.length} 份</span>`)}<div class="card-body"><div class="material-actions"><button class="btn btn-secondary" id="add-link">${icon('link',16)} 添加链接</button><label class="btn btn-secondary upload-label">${icon('upload',16)} 上传文件<input id="material-upload" type="file" multiple hidden></label><label class="btn btn-secondary upload-label">${icon('upload',16)} 上传视频<input id="material-video-upload" accept=".mp4,.m4v,.mov,.webm,.ogv,.ogg" type="file" multiple hidden></label></div><div class="material-dropzone" id="material-dropzone" role="group" tabindex="0" aria-label="学习材料上传区：拖入文件，按 Ctrl+V 粘贴图片和文件，或按 Enter 选择文件" aria-describedby="material-dropzone-hint"><span class="material-dropzone-icon">${icon('upload',25)}</span><strong>把文档、图片或视频拖到这里，也可以点击后粘贴</strong><span id="material-dropzone-hint">点击此区域后按 <kbd>Ctrl</kbd> + <kbd>V</kbd>，直接粘贴截图或复制的文件</span><small>按 Enter 可选择文件；支持多文件，暂不支持文件夹</small></div><div class="material-list">${rows||'<div class="upload-empty">添加多份文档链接、文件或图片，帮助学员理解任务背景。</div>'}</div><p class="field-hint">支持添加多份学习材料，可连续添加链接或一次选择多个文件。${getReviewCamp({},d)==='exploration'?'每个任务最多 20 份材料；':''}视频单个最多 2 GB，其他文件单个最多 ${getReviewCamp({},d)==='exploration'?'100':'2'} MB，文件随任务保存并发布。</p><p id="material-upload-status" role="status" aria-live="polite" class="field-hint"></p></div></section>`;
}
function renderTaskFiles() {
  const d=store.data.draft;
  if(d.camp!=='exploration'||!requiresTaskAssessment(d))return '';
  const files=explorationTaskFiles(d);
  return `<section class="card" id="task-files" tabindex="-1" aria-label="任务文件">${cardHeader('任务文件',`<span class="subtle-label">已添加 ${files.length} 份</span>`)}<div class="card-body"><p class="exploration-task-file-intro">上传包含选择题、解答题等内容的任务文档。学员阅读学习材料后，打开任务文件做题并提交成果。</p><div class="material-actions"><label class="btn btn-primary upload-label">${icon('upload',16)} 上传任务文件<input id="task-file-upload" type="file" multiple hidden></label><button class="btn btn-secondary" id="add-task-link">${icon('link',16)} 添加任务链接</button></div><div class="material-dropzone" id="task-file-dropzone" role="group" tabindex="0" aria-label="任务文件上传区：拖入任务文档或按 Enter 选择文件"><span class="material-dropzone-icon">${icon('file',25)}</span><strong>将任务文档拖到这里，或点击后粘贴文件</strong><small>支持多文件；每个任务最多 20 份任务文件，视频单个最多 2 GB，其他文件单个最多 100 MB</small></div><div class="material-list">${renderMaterialRows(files,'taskFiles')||'<div class="upload-empty">尚未添加任务文件，请上传题目文档或添加任务链接。</div>'}</div><p id="task-file-upload-status" role="status" aria-live="polite" class="field-hint"></p><label class="form-field exploration-assessment-link"><span class="field-label">已有培训测试链接（选填）</span><input data-field="assessmentUrl" type="url" maxlength="2048" value="${e(d.assessmentUrl||'')}" placeholder="https://"><span class="field-hint">已有外部测试页面时可填写此项。上传任务文件、添加任务链接或填写测试链接，至少选择一种。</span></label></div></section>`;
}
function renderScoring() {
  if(!requiresTaskAssessment(store.data.draft))return '';
  const d=store.data.draft; const total=rubricScoreTotal(d);
  const documentScoring=usesAnswerDocumentRubric(d);
  const ai=d.reviewMode==='ai';
  return `<section class="card" id="task-review" tabindex="-1" aria-label="审核方式">${cardHeader('审核方式')}<div class="card-body"><div class="review-options">${[['ai','sparkles','AI 自测','有固定答案，按评分标准自动判定。'],['manual','user','人工审核','无固定答案，由 NPC 或导师直接审核。']].map(([value,ic,title,desc])=>`<label class="review-option ${d.reviewMode===value?'selected':''}"><input type="radio" name="review-mode" value="${value}" ${d.reviewMode===value?'checked':''}><div class="review-option-icon">${icon(ic,20)}</div><div><strong>${title}</strong><p>${desc}</p></div><span class="radio-circle"></span></label>`).join('')}</div>${ai?`<label class="form-field pass-score-field"><span class="field-label">通过分数</span><div class="input-suffix"><input data-field="passScore" type="number" min="0" max="100" value="${d.passScore}"><span>/ 100</span></div><span class="field-hint">${getReviewCamp({},d)==='exploration'?'达到通过分数后完成任务。':'通过后全额发放奖励，每位学员每个任务仅领取一次。'}</span></label>`:''}</div></section>
  ${ai?`<section class="card" id="task-rubric" tabindex="-1" aria-label="AI 评分标准">${cardHeader('AI 评分标准',`<span id="rubric-total" class="tag ${total===100?'tag-green':'tag-red'}">合计 ${total}/100</span>`)}<div class="card-body rubric-list">${documentScoring?`<div class="notice" role="status"><strong>已按标准答案文档评分，满分 100 分</strong><p>${e(ANSWER_DOCUMENT_DIMENSION.description)}</p><p>如需自定义评分规则，仍可添加维度并配置合计 100 分。</p></div>`:''}${d.rubric.map((r,i)=>`<div class="rubric-row"><div class="rubric-index">${String(i+1).padStart(2,'0')}</div><div class="rubric-fields"><div class="rubric-top"><label class="form-field"><span class="field-label">评分维度</span><input data-rubric="${i}" data-key="name" value="${e(r.name)}" placeholder="例如：分析完整性"></label><label class="form-field rubric-score"><span class="field-label">分值</span><div class="input-suffix"><input type="number" min="1" max="100" data-rubric="${i}" data-key="points" value="${r.points}"><span>分</span></div></label><button class="icon-btn" data-remove-rubric="${i}" aria-label="删除评分维度">${icon('trash',17)}</button></div><textarea rows="2" data-rubric="${i}" data-key="description" placeholder="填写得分条件、标准答案或参考要点（仅供评测使用）">${e(r.description)}</textarea></div></div>`).join('')}<div class="rubric-actions"><button class="btn btn-secondary" id="add-rubric">${icon('plus',16)} 添加维度</button><label class="btn btn-plain upload-label">${icon('upload',16)} 附加评分文档<input id="rubric-upload" type="file" accept=".pdf,.docx,.txt,.md" hidden></label><button type="button" class="btn btn-secondary" id="add-rubric-link">${icon('link',16)} 添加答案链接</button></div><p class="field-hint">最多 4 份，每份不超过 2 MB；支持 TXT、MD、DOCX 和含文字的 PDF。保存或发布时解析正文，无法读取的文档会提示更换。评分描述与文档仅供评测和管理人员查看。答案链接读取后保留导入版本，源文档更新时需重新读取。</p><p class="field-hint">${d.camp==='exploration'?'未添加手动维度时，可直接使用标准答案文档评分，满分 100 分；仍需设置通过分数。手动添加维度后，须完善全部维度并配置合计 100 分。':'纯选择题也需要配置评分维度和通过分数，可设置“答案正确性”100 分，并填写标准答案或添加答案链接。'}</p>${renderRubricAttachments(d.rubricAttachments||[],{editable:true})}</div></section>`:''}`;
}
function getReadiness() {
  const d=store.data.draft;
  const assessment=requiresTaskAssessment(d);
  const filled=value=>typeof value==='string'&&!!value.trim();
  const badges=d.badges||[], materials=d.materials||[];
  const validMaterial=m=>{
    if(!filled(m.name)||m.name.trim().length>(d.camp==='exploration'&&m.type!=='link'?240:160)||!['link','file','image'].includes(m.type))return false;
    if(m.type!=='link')return true;
    return isMaterialLink(m.url);
  };
  return [
    {id:'task-basics',title:'基础信息',ready:filled(d.title)&&d.title.trim().length>=3&&!validateTaskFieldLimits(d).length&&filled(d.summary)&&d.summary.trim().length>=10&&(getReviewCamp({},d)==='exploration'?(d.order==null||(Number.isInteger(d.order)&&d.order>=1&&d.order<=9999)):(isTaskCategory(d.publishingDepartment)&&(d.rewardRulesVersion!==4||(Number.isInteger(d.xp)&&d.xp>=0&&d.xp<=1000000))&&DIFFICULTY_PRESETS.some(p=>p.name===d.difficulty)))},
    ...(getReviewCamp({},d)==='exploration'?[]:[{id:'task-badges',title:'奖励点数',ready:validateBadgeWeights(badges).length===0}]),
    ...(getReviewCamp({},d)==='exploration'?[{id:'task-basics',title:'是否需要做任务',ready:d.completionMode==null||EXPLORATION_COMPLETION_MODES.some(mode=>mode.id===d.completionMode)}]:[]),
    {id:'task-materials',title:assessment&&d.camp==='exploration'?'学习材料':'学习材料（选填）',ready:(!assessment||d.camp==='novice'||materials.length>0)&&materials.every(validMaterial)},
    ...(getReviewCamp({},d)==='exploration'&&assessment?[{id:'task-files',title:'任务文件',ready:explorationTaskResourceErrors(d).length===0}]:[]),
    ...(assessment?[{id:'task-review',title:'审核方式',ready:['manual','ai'].includes(d.reviewMode)&&(d.reviewMode!=='ai'||(d.passScore!==null&&d.passScore!==undefined&&String(d.passScore).trim()!==''&&Number.isFinite(Number(d.passScore))&&Number(d.passScore)>=0&&Number(d.passScore)<=100))}]:[]),
    ...(assessment&&d.reviewMode==='ai'?[{id:'task-rubric',title:'评分标准',ready:rubricDimensionErrors(d).length===0}]:[]),
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
      ${requiresTaskAssessment(d)&&d.reviewMode==='ai'?`<div class="preview-task-access"><span>评分标准</span><strong>${rubricDimensionErrors(d).length?'待完善':usesAnswerDocumentRubric(d)?'标准答案文档 · 100 分':`评分维度 · ${format(rubricScoreTotal(d))} 分`}</strong></div>`:''}
      ${exploration?'':`<div class="aside-distribution"><h4>徽章点分配</h4>${reward.allocations.map(b=>`<div class="distribution-row"><svg class="color-dot" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="4" fill="${e(badgeList().find(type=>type.id===b.id)?.color || 'currentColor')}"/></svg><span>${e(badgeName(b.id))}</span><strong>${format(b.points)}<small> 点</small></strong></div>`).join('')}</div>`}
    </div></section><section class="card checklist-card"><div class="checklist-heading"><h3>发布准备</h3><span>${checks.filter(x=>x.ready).length}/${checks.length}</span></div>${checks.map(({id,title,ready})=>`<button type="button" class="checklist-row ${ready?'complete':'incomplete'}" data-jump-section="${id}" aria-label="定位到${title}，${ready?'已完成':'待完成'}">${icon(ready?'checkCircle':'alert',16)}<span>${title}</span><small>${ready?'已完成':'待完成'}</small>${icon('chevronRight',13)}</button>`).join('')}</section>`;
}
function updateAside() { const aside=$('#editor-aside'); if(aside) aside.innerHTML=renderAside(); }

function bindEditor() {
  const d=store.data.draft;
  bindFieldFeedback($('#editor-primary'));
  $('#save-draft').onclick=async event=>{
    const button=event.currentTarget;
    clearFieldError(button);
    if(materialUploadsPending){showFieldError(button,'文件正在上传，请完成后再保存。');return;}
    const errors=validateTaskFieldLimits(d, taskIssue);
    if(errors.length){showTaskIssues($('#editor-primary'),errors,button);return;}
    if(!saveDraft())return;
    try{await store.saveTask(structuredClone(d));render();toast(isTaskUpdate(d)?'修改已保存为草稿，已发布版本保持不变':'草稿已保存，可在任务库中继续编辑');}
    catch(error){showFieldError(button,error.message);}
  };
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
    if(key==='camp' && el.value==='novice' && getReviewCamp({},d)==='exploration'){void switchToVillage(el,d);return;}
    if(key==='xp')d.rewardRulesVersion=4;
    d[key]=el.type==='number'?(el.value===''?'':Number(el.value)):el.value;
    if(key==='camp'&&el.value==='novice'){d.difficulty ||= '入门';if(!d.badges?.length)d.badges=[{id:'product',weight:100}];}
    if(key==='camp'&&el.value==='exploration'&&d.order==null)d.order=nextExplorationOrder(store.data.tasks);
    if(key==='camp'&&el.value==='exploration'&&d.completionMode==null)d.completionMode='learning';
    if((key==='title'||key==='summary')&&$(`#${key}-counter`))$(`#${key}-counter`).textContent=`${taskFieldLength(el.value)}/${TASK_FIELD_LIMITS[key]}`;
    saveDraft();
    if (key === 'camp'||key==='completionMode') render();
  }));} bindFields();
  document.querySelectorAll('.badge-option[data-badge]').forEach(button => button.onclick = () => {
    const id = button.dataset.badge;
    const index = d.badges.findIndex(badge => badge.id === id);
    if (index >= 0) d.badges.splice(index, 1);
    else d.badges.push({id, weight:0});
    if (d.badges.length) {
      const each = Math.floor(100 / d.badges.length), extra = 100 % d.badges.length;
      d.badges.forEach((badge, i) => badge.weight = each + (i < extra ? 1 : 0));
    }
    d.rewardRulesVersion = 4;
    saveDraft(); render();
  });
  document.querySelectorAll('[data-badge-weight]').forEach(input => input.oninput = () => {
    d.badges[Number(input.dataset.badgeWeight)].weight = Number(input.value);
    d.rewardRulesVersion = 4;
    $('#ratio-total').textContent = `合计 ${d.badges.reduce((sum,badge) => sum + badge.weight, 0)}% / 100%`;
    saveDraft();
  });
  $('#add-link')?.addEventListener('click',event=>{if(d.camp==='exploration'&&d.materials.length>=20){showFieldError(event.currentTarget,'每个任务最多添加 20 份材料');return;}editMaterial();});
  $('#add-task-link')?.addEventListener('click',event=>{if(explorationTaskFiles(d).length>=20){showFieldError(event.currentTarget,'每个任务最多添加 20 份任务文件');return;}editMaterial(null,{collection:'taskFiles'});});
  $('#material-upload')?.addEventListener('change',event=>{const files=Array.from(event.target.files||[]);event.target.value='';void addMaterialFiles(files);});
  $('#material-video-upload')?.addEventListener('change',event=>{
    const files=Array.from(event.target.files||[]);event.target.value='';
    const videos=files.filter(isUploadVideo);
    const errors=files.filter(file=>!isUploadVideo(file)).map(file=>`${file.name}：请选择 MP4、MOV、WebM 或 Ogg 视频。`);
    void addMaterialFiles(videos,{errors});
  });
  $('#task-file-upload')?.addEventListener('change',event=>{const files=Array.from(event.target.files||[]);event.target.value='';void addMaterialFiles(files,{target:'taskFiles'});});
  $('#rubric-upload')?.addEventListener('change',event=>{
    const files=Array.from(event.target.files||[]);
    event.target.value='';
    void addMaterialFiles(files,{target:'rubricAttachments'});
  });
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
  $('#add-rubric')?.addEventListener('click',event=>{if(d.rubric.length>=12){showFieldError(event.currentTarget,'最多配置 12 个评分维度');return;}d.rubric.push({id:crypto.randomUUID(),name:'',points:0,description:''});saveDraft();render();});
  document.querySelectorAll('[data-rubric]').forEach(el=>el.addEventListener('input',()=>{d.rubric[Number(el.dataset.rubric)][el.dataset.key]=el.type==='number'?Number(el.value):el.value;saveDraft();if(el.dataset.key==='points'){const total=rubricScoreTotal(d);const tag=$('#rubric-total');if(tag){tag.textContent=`合计 ${total}/100`;tag.className=`tag ${total===100?'tag-green':'tag-red'}`;}}}));
  document.querySelectorAll('[data-remove-rubric]').forEach(b=>b.onclick=()=>{d.rubric.splice(Number(b.dataset.removeRubric),1);saveDraft();render();});
  $('#add-rubric-link')?.addEventListener('click',()=>editRubricLink());
  document.querySelectorAll('[data-edit-rubric-link]').forEach(b=>b.onclick=()=>editRubricLink(Number(b.dataset.editRubricLink)));
  document.querySelectorAll('[data-reread-rubric-link]').forEach(b=>b.onclick=()=>editRubricLink(Number(b.dataset.rereadRubricLink),{reread:true}));
  document.querySelectorAll('[data-remove-rubric-file]').forEach(b=>b.onclick=()=>{d.rubricAttachments.splice(Number(b.dataset.removeRubricFile),1);saveDraft();render();});
  document.querySelectorAll('[name="review-mode"]').forEach(el=>el.onchange=()=>{d.reviewMode=el.value;saveDraft();render();});

}
async function addMaterialFiles(files,options={}) {
  const target=options.target||'materials';
  const zone=()=>$(target==='rubricAttachments'?'label:has(#rubric-upload)':target==='taskFiles'?'#task-file-dropzone':'#material-dropzone');
  if(materialUploadsPending){showFieldError(zone(),'文件正在上传，请完成后再添加。');return;}
  clearFieldError(zone());
  const draft=store.data.draft;
  const {added,failures}=await uploadFiles(files,target,options);
  if(store.data.draft!==draft || !zone())return;
  if(added)render();
  if(failures.length)showFieldError(zone(),failures.join('；'));
  else if(options.source==='paste'||options.source==='drop')zone()?.focus({preventScroll:true});
}
async function uploadFiles(files,target,{source='select',errors=[]}={}) {
  const d=store.data.draft; if(!d[target])d[target]=[];
  const selected=Array.from(files||[]);
  if(!selected.length)return {added:0,failures:errors};
  const exploration=['materials','taskFiles'].includes(target)&&getReviewCamp({},d)==='exploration';
  const label=target==='taskFiles'?'任务文件':'材料', statusId=target==='taskFiles'?'#task-file-upload-status':'#material-upload-status';
  const names=new Set(d[target].map(material=>material.name));
  const controls=[...document.querySelectorAll('#editor-primary button,#editor-primary input,#editor-primary select,#editor-primary textarea,#save-draft,#publish-task')].map(element=>({element,disabled:element.disabled}));
  const zone=$(target==='taskFiles'?'#task-file-dropzone':'#material-dropzone');zone?.setAttribute('aria-busy','true');zone?.setAttribute('aria-disabled','true');
  materialUploadsPending=true;
  controls.forEach(({element})=>element.disabled=true);
  let added=0; const failures=[...errors];
  try {
    for(const [index,original] of selected.entries()){
      if(exploration&&d[target].length>=20){failures.push(`每个任务最多添加 20 份${label}，剩余 ${selected.length-index} 份文件未上传。`);break;}
      try {
        const file=target==='rubricAttachments'?normalizeRubricFile(original,d[target].length):['materials','taskFiles'].includes(target)?normalizeLearningMaterialFile(original,{source,names}):original;
        const status=$(statusId);
        if(status)status.textContent=`正在上传 ${file.name}（${index+1}/${selected.length}），请稍候…`;
        if(exploration){
          d[target].push(await uploadExplorationMaterial(file,{label:target==='taskFiles'?'任务':'学习材料'}));
        }else if(target==='materials' && isUploadVideo(file)){
          d[target].push(await uploadTaskVideo(file,'novice'));
        }else{
          if(file.size>2*1024*1024)throw new Error(`${file.name} 超过 2 MB，请改用文档链接`);
          const url=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});
          d[target].push({id:crypto.randomUUID(),name:file.name,type:file.type.startsWith('image/')?'image':'file',url,size:file.size,mime:file.type});
        }
        added++;
        saveDraft();
      }catch(error){failures.push(error.message||`${original?.name||'文件'} 上传失败，请重试`);}
    }
    if(added&&saveDraft())toast(`已添加 ${added} 份文件到当前草稿`);
    return {added,failures};
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
  const video=materialVideoPreviewUrl(m);
  if(video){openModal(`<div class="modal-heading"><h2>${e(m.name)}</h2></div><video controls playsinline preload="metadata" style="width:100%;max-height:65vh" src="${e(video)}"></video>`);return;}
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
    bindFieldFeedback(modal);
    modal.querySelector('[data-submit-cancel]').onclick=closeModal;
    confirm.onclick=async()=>{
      if(confirm.disabled || !confirmPublicationFields(modal))return;
      modal.dataset.operationPending='true';modal.querySelectorAll('button,input').forEach(el=>el.disabled=true);
      confirm.textContent='正在提交…';
      try {await service.tasks.submitPublication(task,selected());modal.dataset.operationPending='false';closeModal();render();toast('已提交，等待超级管理员审核');}
      catch(error){modal.dataset.operationPending='false';modal.querySelectorAll('button,input').forEach(el=>el.disabled=false);confirm.textContent='确认提交审核';const msg=modal.querySelector('#submit-publication-error');msg.hidden=false;msg.textContent=error.message;confirm.focus();}
    };
  });
}

async function publish() {
  if(materialUploadsPending){toast('文件正在上传，请完成后再发布。','error');return;}
  if(draftPublication()?.status==='pending'){toast('任务正在等待审核');return;}
  const errors=validateTask(store.data.draft, taskIssue);
  if(errors.length){showTaskIssues($('#editor-primary'),errors,$('#publish-task'));return;}
  const launch = $('#publish-task');
  if (launch.disabled) return;
  launch.disabled = true;
  try {
    const savedTask = await store.saveTask(normalizeBadgeWeights(store.data.draft));
    const publishingUpdate = isTaskUpdate(savedTask);
    if(!ui.isSuperAdmin){openSubmitPublication(savedTask);return;}
    const links = taskResourceLinks(savedTask);
    let key = crypto.randomUUID(), keySelection;
    openModal(`<div class="native-publish-confirm"><div class="modal-heading"><h2>${publishingUpdate?'确认发布更新':'确认发布任务'}</h2><p>${e(savedTask.title)}</p></div><div class="notice">超级管理员确认后直接发布。</div>${renderPublishMaterials(savedTask.materials,savedTask)}<div class="notice">${publishingUpdate?'本次更新现有任务，不会新增任务卡。已领取的学员保留原版本，未领取的学员将看到更新后的版本。':'本次发布将新增一张任务卡，学员可查看并领取。'}</div><p class="inline-error" id="publish-error" role="alert" hidden></p><div class="modal-actions"><button class="btn btn-secondary" id="cancel-publish">取消</button><button class="btn btn-primary" id="confirm-publish" disabled>${publishingUpdate?'确认更新':'确认发布'}</button></div></div>`, modal => {
      const confirm = $('#confirm-publish',modal);
      const selected = () => [...modal.querySelectorAll('[data-verified-link]:checked')].map(el=>links[Number(el.dataset.verifiedLink)]);
      bindFieldFeedback(modal);
      confirm.disabled = false;
      $('#cancel-publish',modal).onclick = closeModal;
      confirm.onclick = async () => {
        if (confirm.disabled || !confirmPublicationFields(modal)) return;
        const selection = JSON.stringify(selected());
        if (keySelection && keySelection !== selection) key = crypto.randomUUID();
        keySelection = selection;
        modal.dataset.operationPending = 'true';
        modal.querySelectorAll('button,input,select').forEach(el=>el.disabled=true);
        confirm.textContent = '正在发布…';
        const error = $('#publish-error',modal); error.hidden = true;
        try {
          const published = await service.tasks.publish(savedTask,selected(),key);
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
          confirm.textContent = publishingUpdate?'确认更新':'确认发布'; error.textContent=err.message; error.hidden=false;confirm.focus();
        }
      };
    });
  } catch(err){launch.disabled=false;showFieldError(launch,err.message||'发布准备失败，请检查配置');}
  finally { launch.disabled=false; }
}

onInviteSessionChange(render);
if (page===villagePublishPage && !['#village-courses','#'+villagePublishPage+'/list'].includes(location.hash)) {
  void villageCourses.resumePublishing();
}
render();

let refreshing = false;
let refreshRequested = false;
async function refreshRecords(afterPermissionChange = false) {
  if (refreshing) {
    if (afterPermissionChange === true) refreshRequested = true;
    return;
  }
  if (document.hidden) return;
  refreshing = true;
  try { await store.refresh(); syncExperienceAccess(); if(courseWorkspace(page)?.canRefresh()&&!document.querySelector('.modal')&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))await courseWorkspace(page).activate(); if (!document.querySelector('.modal') && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName) && (page === 'review' || page === 'library' || page === 'publications' || (page==='publish'&&draftPublication()))) render(); }
  catch (error) { toast(error.message, 'error'); }
  finally {
    refreshing = false;
    if (refreshRequested) { refreshRequested = false; void refreshRecords(); }
  }
}
setInterval(refreshRecords, 12000);
window.addEventListener('focus', refreshRecords);
const requestedReview = new URL(location.href).searchParams.get('review');
if (requestedReview) {
  const submission = store.data.submissions.find(s => s.id === requestedReview);
  if (submission) { reviewCamp = submission.camp; navigate('review'); await openSubmission(store, ui, requestedReview); }
  else toast('当前账号未找到这条审核记录。','error');
}
