import {effectiveRubric, usesAnswerDocumentRubric} from './rubric-policy.js?v=20261118-document-rubric';
import {renderRubricAttachments} from './rubric-link-editor.js?v=20261118-answer-link';
import {canConfigureTask, EXPLORATION_CONFIGURATION_NOTICE} from './task-publication-access.js';
import { BADGES, CERTIFICATION_LEVELS, normalizeCertificationRole, getCertificationLevel, escapeHtml as e, icon, rewardBreakdown, getReviewCamp } from './core.js?v=20261030-member-action-spacing';
import { localMaterialUrl } from './exploration-material-files.js';
import { EXPLORATION_COMPLETION_MODES, explorationCompletionMode, requiresTaskAssessment, taskCompletionLabel, validAssessmentUrl, explorationTaskFiles } from './exploration-completion.js';
import { isPinnedExplorationTask } from './exploration-order.js';

import {PUBLISHING_DEPARTMENTS, departmentLabel} from './publishing-departments.js';
const state = { tab: 'tasks', search: '', domain: 'all', status: 'all', camp: typeof location !== 'undefined' && new URLSearchParams(location.search || '').get('camp') === 'exploration' ? 'exploration' : 'all' };
const badgeList = () => Array.isArray(BADGES) ? BADGES : Object.values(BADGES);
const badgeName = id => badgeList().find(b => b.id === id)?.name || id;
const badgeColor = id => badgeList().find(b => b.id === id)?.color || '#7771dd';
const domains = ['数据交付', '产品开发', '技术开发', 'PMO', 'AI评测', '质量检测', '项目管理', 'AI 能力'];
const statusText = status => ({ published: '已发布', draft: '草稿', archived: '已归档' }[status] || status);
const publicationLabel = task => task.publication?.status==='pending'?'待发布审核':task.publication?.status==='rejected'?'发布已退回':statusText(task.status);
const fmt = n => Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
const pointValue = value => Number(typeof value === 'object' && value !== null ? value.points : value) || 0;
const badgePoints = (learner, badgeId) => pointValue(learner.badges?.[badgeId]);
const badgeLevel = points => Math.min(3, Math.floor(points / 100));
const safeUrl = value => { try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : ''; } catch { return ''; } };
const modalRoot = root => root?.querySelector ? root : document.querySelector('.modal') || document;
const taskAuthor = task => typeof task.author === 'object' ? task.author?.name || '未指定' : task.author || '未指定';
const taskOrder = task => task.publishedOrder ?? task.order;
const chip = (badge, showWeight = true) => `<span class="badge-chip"><span class="badge-dot" data-badge="${e(badge.id)}" aria-hidden="true"></span>${e(badgeName(badge.id))}${showWeight ? `<span class="muted">${fmt(badge.weight)}%</span>` : ''}</span>`;

function filteredTasks(store) {
  const matching = (store.data.tasks || []).filter(task => {
    const haystack = `${task.title || ''} ${task.id || ''} ${taskAuthor(task)} ${task.summary || ''}`.toLowerCase();
    return (!state.search || haystack.includes(state.search.toLowerCase())) && (state.camp === 'exploration' || state.domain === 'all' || task.publishingDepartment === state.domain) && (state.status === 'all' || task.status === state.status) && (state.camp === 'all' || getReviewCamp({}, task) === state.camp);
  });
  return state.camp === 'exploration' ? matching.sort((a,b) => Number(isPinnedExplorationTask(a)) - Number(isPinnedExplorationTask(b)) || (Number(taskOrder(a)) || 9999) - (Number(taskOrder(b)) || 9999)) : matching;
}

function stats(store) {
  const tasks = store.data.tasks || [];
  const submissions = store.data.submissions || [];
  const totalParticipants = tasks.reduce((sum, task) => sum + Number(task.participants || 0), 0);
  const completions = tasks.reduce((sum, task) => sum + Number(task.completions || 0), 0);
  return `<div class="stats-grid">
    <div class="card stat-card"><span class="stat-label">任务总数</span><strong class="stat-value">${fmt(tasks.length)}</strong><span class="stat-note">覆盖全部导师与 NPC</span></div>
    <div class="card stat-card"><span class="stat-label">已发布任务</span><strong class="stat-value">${fmt(tasks.filter(t => t.status === 'published').length)}</strong><span class="stat-note">${fmt(tasks.filter(t => t.status === 'draft').length)} 个草稿待完善</span></div>
    <div class="card stat-card"><span class="stat-label">累计参与人次</span><strong class="stat-value">${fmt(totalParticipants)}</strong><span class="stat-note">${fmt(submissions.length)} 份学员提交</span></div>
    <div class="card stat-card"><span class="stat-label">任务完成人次</span><strong class="stat-value">${fmt(completions)}</strong><span class="stat-note">${state.camp==='exploration'?'审核通过后计为完成':'通过后发放任务奖励'}</span></div>
  </div>`;
}

function tasksTable(store, ui) {
  const tasks = filteredTasks(store);
  const showOrder = state.camp !== 'novice';
  if (!tasks.length) return `<div class="empty-state"><strong>没有找到相关任务</strong><p>试试调整筛选条件，或创建一个新任务。</p><button class="btn btn-secondary" data-library-action="reset">重置筛选</button></div>`;
  return `<div class="table-wrap"><table class="data-table library-table"><thead><tr>${showOrder?`<th>${state.camp==='exploration'?'排序':'探索营排序'}</th>`:''}<th>任务名称</th><th>发布者</th><th>${state.camp==='exploration'?'学习材料':state.camp==='novice'?'关联徽章':'材料 / 徽章'}</th><th>${state.camp==='novice'?'审核方式':'完成方式 / 审核'}</th><th>完成 / 参与</th><th>状态</th><th class="text-right">操作</th></tr></thead><tbody>${tasks.map(task => `<tr>
    ${showOrder?`<td>${getReviewCamp({},task)==='exploration'?isPinnedExplorationTask(task)?'<strong>固定在毕业码前</strong>':`<strong>${Number.isInteger(taskOrder(task))&&taskOrder(task)>0?taskOrder(task):'—'}</strong>${task.publishedOrder!=null&&task.order!==task.publishedOrder?`<div class="table-subtitle">草稿：${e(task.order)}</div>`:''}`:'<span class="muted">—</span>'}</td>`:''}
    <td><button class="table-title" data-task-view="${e(task.id)}">${e(task.title || '未命名任务')}</button><div class="table-subtitle">${getReviewCamp({},task)==='exploration'?'探索营':'新手村'} · ${e(task.id)}${getReviewCamp({},task)==='exploration'?'':` · ${e(departmentLabel(task.publishingDepartment))}`}</div></td>
    <td>${e(taskAuthor(task))}</td>
    <td><div class="badge-cell">${getReviewCamp({},task)==='exploration'?`${(task.materials||[]).length} 份学习材料${requiresTaskAssessment(task)?` · ${explorationTaskFiles(task).length} 份任务文件`:''}`:(task.badges || []).map(b => chip(b, false)).join('') || '<span class="muted">尚未设置</span>'}</div></td>
    <td><span class="tag ${requiresTaskAssessment(task)&&task.reviewMode === 'ai' ? 'tag-purple' : 'tag-neutral'}">${e(taskCompletionLabel(task))}</span></td>
    <td><strong>${fmt(task.completions)}</strong><span class="muted"> / ${fmt(task.participants)}</span></td>
    <td><span class="tag ${task.status === 'published' ? 'tag-success' : task.status === 'archived' ? 'tag-neutral' : 'tag-warning'}">${e(publicationLabel(task))}</span></td>
    <td><div class="table-actions"><button class="text-btn" data-task-view="${e(task.id)}">查看</button>${canConfigureTask(task,ui?.isSuperAdmin)?`<button class="text-btn" data-task-edit="${e(task.id)}">编辑</button><button class="text-btn" data-task-copy="${e(task.id)}">复制为新任务</button><button class="text-btn muted" data-task-archive="${e(task.id)}">${task.status === 'archived' ? '恢复' : '归档'}</button>${getReviewCamp({},task)==='exploration'?`<button class="text-btn task-delete-action" data-task-delete="${e(task.id)}">删除</button>`:''}`:''}</div></td>
  </tr>`).join('')}</tbody></table></div><div class="table-footer">共 ${fmt(tasks.length)} 个任务<span>展示所有 NPC 与导师发布的任务</span></div>`;
}

function taskTab(store, ui) {
  const availableDomains = PUBLISHING_DEPARTMENTS;
  return `${stats(store)}<section class="card library-main-card"><div class="card-heading"><div><h2>全部任务</h2></div><button class="btn btn-secondary" data-library-action="export">${icon('download')} 导出数据</button></div>
    <div class="filter-bar"><label class="search-field">${icon('search')}<input id="library-search" type="search" placeholder="搜索任务名称、编号或发布者" value="${e(state.search)}" aria-label="搜索任务"></label><select id="library-camp" aria-label="按所属营地筛选"><option value="all">全部营地</option>${[['exploration','探索营'],['novice','新手村']].map(([value,label])=>`<option value="${value}" ${state.camp===value?'selected':''}>${label}</option>`).join('')}</select><select id="library-domain" aria-label="按发布部门筛选"><option value="all">全部部门</option>${availableDomains.map(domain => `<option value="${e(domain)}" ${state.domain === domain ? 'selected' : ''}>${e(domain)}</option>`).join('')}</select><select id="library-status" aria-label="按任务状态筛选"><option value="all">全部状态</option>${['published', 'draft', 'archived'].map(status => `<option value="${status}" ${state.status === status ? 'selected' : ''}>${statusText(status)}</option>`).join('')}</select></div>
    <div id="library-task-results">${tasksTable(store, ui)}</div>
  </section>`.replace(/<select id="library-domain"[\s\S]*?<\/select>/, value => state.camp === 'exploration' ? '' : value);
}

function badgeTab(store) {
  const tasks = store.data.tasks || [];
  const learners = store.data.learners || [];
  return `<div class="card badge-rules"><div><span class="eyebrow">成长体系</span><h2>每一份投入，都有积累</h2><p>任务经验值按 10 : 1 换算为徽章点，再按任务配置的占比分配。</p></div><div class="badge-level-steps"><span><strong>100</strong>点亮 1 级</span><i></i><span><strong>200</strong>达到 2 级</span><i></i><span><strong>300</strong>达到 3 级</span></div></div>
    <div class="section-heading"><h2>标签与徽章 <span class="count-pill">8</span></h2><span class="muted">固定八种徽章 · 每个任务关联 1～2 种</span></div>
    <div class="badge-grid">${badgeList().map(badge => {
      const points = learners.reduce((sum, learner) => sum + badgePoints(learner, badge.id), 0);
      const holders = learners.filter(learner => badgePoints(learner, badge.id) >= 100).length;
      const bound = tasks.filter(task => (task.badges || []).some(b => b.id === badge.id)).length;
      return `<button class="card badge-summary-card" data-badge-view="${e(badge.id)}"><div class="badge-card-heading"><span class="badge-emblem" style="--badge-color:${e(badge.color || '#7771dd')}">${icon('award')}</span><span class="tag tag-neutral">最高 3 级</span></div><h3>${e(badge.name)}</h3><p>完成关联任务，积累专属徽章点</p><div class="badge-card-stats"><span><strong>${fmt(bound)}</strong>关联任务</span><span><strong>—</strong>已发徽章点</span><span><strong>—</strong>已点亮人数</span></div><div class="badge-card-footer">查看收集情况 <span>→</span></div></button>`;
    }).join('')}</div><div class="inline-note">徽章点累计保留，达到 100 / 200 / 300 点分别获得 1 / 2 / 3 级。奖励通过后全额发放，每名学员每个任务只领取一次。</div>`;
}

export function renderLibrary(store, ui) {
  return `<div class="content-actions">${state.camp==='exploration'&&!ui.isSuperAdmin?`<span class="muted">${EXPLORATION_CONFIGURATION_NOTICE}</span>`:`<button class="btn btn-primary" data-library-action="new">${icon('plus')} 发布新任务</button>`}</div>
    <div class="tabs" role="tablist"><button class="tab ${state.tab === 'tasks' ? 'active' : ''}" role="tab" aria-selected="${state.tab === 'tasks'}" data-library-tab="tasks">任务总览</button><button class="tab ${state.tab === 'badges' ? 'active' : ''}" role="tab" aria-selected="${state.tab === 'badges'}" data-library-tab="badges">标签与徽章</button></div>
    ${state.tab === 'tasks' ? taskTab(store, ui) : badgeTab(store)}`;
}

function attachTaskActions(root, store, ui) {
  root.querySelectorAll('[data-task-view]').forEach(button => button.addEventListener('click', () => openTask(store.getTask(button.dataset.taskView), store, ui)));
  root.querySelectorAll('[data-task-edit]').forEach(button => button.addEventListener('click', () => ui.editTask(store.getTask(button.dataset.taskEdit))));
  root.querySelectorAll('[data-task-copy]').forEach(button => button.addEventListener('click', () => ui.copyTask(store.getTask(button.dataset.taskCopy))));
  root.querySelectorAll('[data-task-delete]').forEach(button => button.addEventListener('click', () => openDeleteTask(store.getTask(button.dataset.taskDelete), store, ui)));
  root.querySelectorAll('[data-task-archive]').forEach(button => button.addEventListener('click', async () => {
    const task = store.getTask(button.dataset.taskArchive);
    if (!task || button.disabled) return;
    if (!canConfigureTask(task,ui.isSuperAdmin)) { ui.toast(EXPLORATION_CONFIGURATION_NOTICE,'error'); return; }
    button.disabled = true;
    try { await store.archiveTask(task); ui.toast(task.status === 'archived' ? '任务已恢复' : '任务已归档'); ui.refresh(); }
    catch (error) { ui.toast(error.message, 'error'); button.disabled = false; }
  }));
}

function openDeleteTask(task, store, ui) {
  if (!canConfigureTask(task,ui.isSuperAdmin)) { ui.toast(EXPLORATION_CONFIGURATION_NOTICE,'error'); return; }
  if (!task) { ui.toast('任务不存在，请刷新任务库。', 'error'); return; }
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">任务库</div><h2>删除任务</h2></div></div><div class="modal-body"><p>确认删除「${e(task.title || '未命名任务')}」？</p><div class="notice">删除后，任务会从任务库及学员任务列表移除。已经保存的学习成果、审核记录和已获得的宝藏会保留。</div><p class="inline-error" data-delete-error role="alert" hidden></p></div><div class="modal-footer"><button type="button" class="btn btn-secondary" data-delete-cancel>取消</button><button type="button" class="btn btn-danger" data-delete-confirm>确认删除</button></div>`, modal => {
    const root = modalRoot(modal);
    const confirm = root.querySelector('[data-delete-confirm]');
    const error = root.querySelector('[data-delete-error]');
    let deleting = false;
    root.querySelector('[data-delete-cancel]').addEventListener('click', () => { if (!deleting) ui.closeModal(); });
    confirm.addEventListener('click', async () => {
      if (deleting) return;
      deleting = true;
      root.dataset.operationPending = 'true';
      root.querySelectorAll('button').forEach(button => { button.disabled = true; });
      confirm.textContent = '正在删除…';
      error.hidden = true;
      try {
        if (typeof store.deleteTask !== 'function') throw new Error('当前任务暂不支持删除。');
        await store.deleteTask(task);
        deleting = false; root.dataset.operationPending = 'false';
        ui.closeModal(); ui.toast('任务已删除'); ui.refresh();
      } catch (failure) {
        deleting = false; root.dataset.operationPending = 'false';
        root.querySelectorAll('button').forEach(button => { button.disabled = false; });
        confirm.textContent = '确认删除';
        error.textContent = failure.message || '任务删除失败，请重试。'; error.hidden = false;
      }
    });
  });
}

export function bindLibrary(root, store, ui) {
  root.querySelectorAll('[data-library-tab]').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.libraryTab; ui.refresh(); }));
  root.querySelector('[data-library-action="new"]')?.addEventListener('click', () => { if (typeof ui.newTask === 'function') ui.newTask(); else ui.navigate('publish'); });
  root.querySelector('[data-library-action="export"]')?.addEventListener('click', () => {
    const exportData = { exportedAt: new Date().toISOString(), system: 'JOURNEY 管理系统', tasks: filteredTasks(store), rewardRules: { xpPerBadgePoint: 10, badgeThresholds: [100, 200, 300], maxTaskBadges: 2 }, learners: store.data.learners || [] };
    const url = URL.createObjectURL(new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = `JOURNEY-任务库-${new Date().toISOString().slice(0, 10)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    ui.toast('任务库数据已导出');
  });
  root.querySelector('[data-library-action="reset"]')?.addEventListener('click', () => { state.search = ''; state.domain = 'all'; state.status = 'all'; state.camp = 'all'; ui.refresh(); });
  const refreshResults = () => {
    const target = root.querySelector('#library-task-results');
    if (!target) return;
    target.innerHTML = tasksTable(store, ui); attachTaskActions(target, store, ui);
    target.querySelector('[data-library-action="reset"]')?.addEventListener('click', () => { state.search = ''; state.domain = 'all'; state.status = 'all'; state.camp = 'all'; ui.refresh(); });
  };
  root.querySelector('#library-search')?.addEventListener('input', event => { state.search = event.target.value; refreshResults(); });
  root.querySelector('#library-camp')?.addEventListener('change', event => { state.camp = event.target.value; if(state.camp==='exploration')state.domain='all'; refreshResults(); ui.refresh(); });
  root.querySelector('#library-domain')?.addEventListener('change', event => { state.domain = event.target.value; refreshResults(); });
  root.querySelector('#library-status')?.addEventListener('change', event => { state.status = event.target.value; refreshResults(); });
  attachTaskActions(root, store, ui);
  root.querySelectorAll('[data-badge-view]').forEach(button => button.addEventListener('click', () => openBadge(button.dataset.badgeView, store, ui)));
}

export function openTask(task, store, ui) {
  if (!task) { ui.toast('任务不存在', 'error'); return; }
  const exploration = getReviewCamp({},task)==='exploration';
  const assessment=requiresTaskAssessment(task);
  const scoringRubric=effectiveRubric(task);
  const documentScoring=usesAnswerDocumentRubric(task);
  const completion=exploration?EXPLORATION_COMPLETION_MODES.find(mode=>mode.id===explorationCompletionMode(task)):null;
  const assessmentUrl=exploration&&assessment&&validAssessmentUrl(task.assessmentUrl)?safeUrl(task.assessmentUrl):'';
  let rewards;
  try { rewards = rewardBreakdown(task); } catch { rewards = null; }
  const badgeRewards = rewards?.allocations || (task.badges || []).map(badge => ({ ...badge, points: Number(task.xp || 0) / 10 * Number(badge.weight || 0) / 100 }));
  const materialHtml = (files, kind='material') => files.map((material, index) => {
    const url = safeUrl(material.url);
    const uploaded = Boolean(localMaterialUrl(material.url)) || /^data:[^,]*;base64,/i.test(material.url || '');
    return `<div class="detail-material"><span>${icon(material.type === 'image' ? 'image' : 'file')} ${e(material.name || '未命名材料')}</span>${url ? `<a class="text-btn" href="${e(url)}" target="_blank" rel="noopener noreferrer">打开${kind==='task-file'?'任务文件':'材料'} ↗</a>` : uploaded ? `<button class="text-btn" data-${kind}-download="${index}">下载${kind==='task-file'?'任务文件':'材料'}</button>` : '<span class="muted">示例附件</span>'}</div>`;
  }).join('');
  const taskSubmissions = (store.data.submissions || []).filter(submission => submission.taskId === task.id);
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">${e(task.id)} · ${e(publicationLabel(task))}</div><h2>${e(task.title || '未命名任务')}</h2></div></div><div class="modal-body task-detail-body">${task.publication?.status==='rejected'?`<div class="notice">发布退回原因：${e(task.publication.comment)}</div>`:""}<p class="detail-summary">${e(task.summary || '暂无任务简述')}</p><div class="detail-meta"><span>发布者 <strong>${e(taskAuthor(task))}</strong></span>${exploration?`<span>任务排序 <strong>${isPinnedExplorationTask(task)?'固定在毕业码前':`第 ${Number.isInteger(taskOrder(task))&&taskOrder(task)>0?taskOrder(task):'—'} 个`}</strong></span><span>完成方式 <strong>${e(taskCompletionLabel(task))}</strong></span>`:`<span>发布部门 <strong>${e(departmentLabel(task.publishingDepartment))}</strong></span><span>难度 <strong>${e(task.difficulty || '未设置')}</strong></span><span>预计耗时 <strong>${fmt(task.minutes)} 分钟</strong></span>`}${assessment?`<span>审核 <strong>${task.reviewMode === 'ai' ? 'AI 自测' : '人工审核'}</strong></span>`:''}${assessment&&task.reviewMode === 'ai' ? `<span>通过分数 <strong>${fmt(task.passScore)} 分</strong></span>` : ''}</div>
    ${completion?`<section class="detail-section"><h3>完成方式</h3><p>${e(completion.description)}</p>${assessmentUrl?`<a class="text-btn" href="${e(assessmentUrl)}" target="_blank" rel="noopener noreferrer">打开培训测试链接 ↗</a>`:''}</section>`:''}
    ${exploration?'':`<section class="detail-section"><h3>奖励与徽章</h3><div class="reward-summary"><span><strong>${fmt(task.xp)}</strong> 经验值</span><span>直接领取</span><span><strong>${fmt(Number(task.xp || 0) / 10)}</strong> 总徽章点</span></div><div class="badge-cell">${badgeRewards.map(badge => `${chip(badge)}<span class="muted">+${fmt(badge.points)} 点</span>`).join('')}</div></section>`}
    <section class="detail-section"><h3>学习材料 <span class="count-pill">${(task.materials || []).length}</span></h3>${materialHtml(task.materials||[]) || '<p class="muted">尚未添加学习材料</p>'}</section>
    ${exploration&&assessment?`<section class="detail-section"><h3>任务文件 <span class="count-pill">${explorationTaskFiles(task).length}</span></h3>${materialHtml(explorationTaskFiles(task),'task-file')||'<p class="muted">使用已有培训测试链接完成任务</p>'}</section>`:''}
    ${assessment?`<section class="detail-section"><h3>任务要求</h3>${(task.questions || []).map((question, index) => `<article class="question-preview"><h4>${index + 1}. ${e(question.title || '任务要求')}</h4><p class="preserve-lines">${e(question.description || '')}</p><small class="muted">提交形式：${e(({text:'文字回答', file:'文件提交', both:'文字与文件'}[question.submission]) || question.submission || '文本')} · ${question.required === false ? '选答' : '必答'}</small></article>`).join('') || (task.requirements||[]).map(item=>`<p>${e(item)}</p>`).join('') || '<p class="muted">尚未添加任务要求</p>'}</section>`:''}
    ${assessment&&task.reviewMode === 'ai' ? `<section class="detail-section"><h3>AI 评分标准 <span class="tag tag-purple">共 ${fmt(scoringRubric.reduce((sum, item) => sum + Number(item.points || 0), 0))} 分</span></h3>${documentScoring?'<p class="notice">已按标准答案文档评分，满分 100 分。</p>':''}${scoringRubric.map(item => `<div class="rubric-preview"><div><strong>${e(item.name)}</strong><span>${fmt(item.points)} 分</span></div><p class="preserve-lines">${e(item.description || '')}</p></div>`).join('') || '<p class="muted">尚未配置评分标准</p>'}${renderRubricAttachments(task.rubricAttachments || [])}</section>` : ''}
    <section class="detail-section"><h3>参与情况</h3><p class="muted">${fmt(task.participants)} 人次参与，${fmt(task.completions)} 人次完成，${fmt(taskSubmissions.length)} 份答案已提交。</p>${taskSubmissions.length ? '<button class="btn btn-secondary" data-task-review>前往审核任务</button>' : ''}</section></div><div class="modal-footer"><button class="btn btn-secondary" data-close-modal>关闭</button>${canConfigureTask(task,ui.isSuperAdmin)?'<button class="btn btn-primary" data-detail-edit>编辑任务</button>':''}</div>`, modal => {
    const root = modalRoot(modal);
    root.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', ui.closeModal));
    root.querySelector('[data-detail-edit]')?.addEventListener('click', () => { ui.closeModal(); ui.editTask(task); });
    root.querySelector('[data-task-review]')?.addEventListener('click', () => { ui.closeModal(); ui.navigate('review'); });
    const download = material => { const local=localMaterialUrl(material?.url); if (!material?.url || (!local&&!/^data:[^,]*;base64,/i.test(material.url))) return; const a = document.createElement('a'); a.href = local||material.url; a.download = material.name || '任务材料'; a.click(); ui.toast('材料下载已开始'); };
    root.querySelectorAll('[data-material-download]').forEach(button => button.addEventListener('click', () => download(task.materials[Number(button.dataset.materialDownload)])));
    root.querySelectorAll('[data-task-file-download]').forEach(button => button.addEventListener('click', () => download(explorationTaskFiles(task)[Number(button.dataset.taskFileDownload)])));
    root.querySelectorAll('[data-rubric-download]').forEach(button => button.addEventListener('click', () => download(task.rubricAttachments[Number(button.dataset.rubricDownload)])));
  });
}

function openBadge(id, store, ui) {
  const badge = badgeList().find(item => item.id === id);
  if (!badge) return;
  const learners = (store.data.learners || []).filter(learner => badgePoints(learner, id) > 0).sort((a, b) => badgePoints(b, id) - badgePoints(a, id));
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">标签与徽章</div><h2>${e(badge.name)}</h2></div></div><div class="modal-body"><p class="muted">100 / 200 / 300 徽章点分别达到 1 / 2 / 3 级。未满 100 点时仍会保留学习积累。</p>${learners.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>学员</th><th>累计徽章点</th><th>当前等级</th><th>升级进度</th></tr></thead><tbody>${learners.map(learner => { const points = badgePoints(learner, id), level = badgeLevel(points), target = (level + 1) * 100, progress = level === 3 ? 100 : points % 100; return `<tr><td><strong>${e(learner.name)}</strong><div class="table-subtitle">${e(learner.id)}</div></td><td>${fmt(points)}</td><td><span class="tag ${level ? 'tag-purple' : 'tag-neutral'}">${level ? `${level} 级` : '待点亮'}</span></td><td><div class="mini-progress"><span style="width:${progress}%"></span></div><small class="muted">${level === 3 ? '已达最高等级' : `还需 ${fmt(target - points)} 点达到 ${level + 1} 级`}</small></td></tr>`; }).join('')}</tbody></table></div>` : '<div class="empty-state"><strong>奖励记录尚未接入</strong><p>当前页面只能查看徽章规则和关联任务。</p></div>'}</div><div class="modal-footer"><button class="btn btn-primary" data-close-modal>完成</button></div>`, modal => { modalRoot(modal).querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', ui.closeModal)); });
}

const certificationLevelOptions = value => CERTIFICATION_LEVELS.map(level => `<option value="${e(level.value)}" ${getCertificationLevel(value).value === level.value ? 'selected' : ''}>${e(level.name)}</option>`).join('');
const certificationLevelHint = () => `<span class="field-hint">${CERTIFICATION_LEVELS.map(level => `${e(level.name)}对应${e(level.difficulty)}任务`).join('，')}</span>`;

function requireCertificationAdmin(ui) {
  if (ui.isSuperAdmin === true) return true;
  ui.toast('无权限，仅超级管理员可管理认证', 'error');
  return false;
}

async function grantCertification(ui, payload) {
  if (!requireCertificationAdmin(ui)) throw new Error('无权限，仅超级管理员可管理认证');
  if (typeof ui.service?.certifications?.grant !== 'function') throw new Error('认证服务暂不可用，请重试');
  const result = await ui.service.certifications.grant(payload);
  if (result === false || result?.ok === false || result?.error) throw new Error(result?.error || result?.message || '认证信息未保存，请重试');
  return result;
}

function certificationForm() {
  return `<form id="certification-form" class="certification-form"><div class="form-grid"><label class="form-field"><span class="field-label">成员姓名 <span class="required">*</span></span><input name="name" maxlength="30" required placeholder="请输入姓名"></label><label class="form-field"><span class="field-label">身份类型</span><select name="role"><option value="NPC" selected>NPC</option><option value="管理系统的管理员">管理系统的管理员</option></select></label><label class="form-field"><span class="field-label">专业方向</span><select name="domain">${domains.map(domain => `<option value="${e(domain)}">${e(domain)}</option>`).join('')}</select></label><label class="form-field"><span class="field-label">认证等级</span><select name="level">${certificationLevelOptions(1)}</select>${certificationLevelHint()}</label></div><div class="cert-form-footer"><span class="muted">保存后立即生效</span><button class="btn btn-primary" type="submit">添加成员</button></div><div id="cert-form-error" class="field-error" role="alert"></div></form>`;
}

function certificationRows(store) {
  const certifications = store.data.certifications || [];
  if (!certifications.length) return '<div class="empty-state"><strong>暂无认证记录</strong><p>使用上方表单添加已完成线下认定的成员。</p></div>';
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>成员</th><th>方向</th><th>等级</th><th>状态</th><th>操作</th></tr></thead><tbody>${certifications.map(cert => { const level = getCertificationLevel(cert.level ?? cert.levelName); return `<tr><td><strong>${e(cert.name)}</strong><div class="table-subtitle">${e(normalizeCertificationRole(cert.role))} · ${cert.method === 'admin' ? '线下认定' : '历史申请'}</div></td><td>${e(cert.domain)}</td><td><span class="tag tag-purple">${e(level.name)}</span><div class="table-subtitle">对应${e(level.difficulty)}任务</div></td><td><span class="tag ${cert.status === 'verified' ? 'tag-success' : 'tag-warning'}">${cert.status === 'verified' ? '已认证' : '待确认'}</span></td><td><button class="text-btn" data-cert-edit="${e(cert.id)}">${cert.status === 'pending' ? '确认认证' : '修改等级'}</button></td></tr>`; }).join('')}</tbody></table></div>`;
}

export function openCertification(store, ui) {
  if (!requireCertificationAdmin(ui)) return;
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">MEMBER CERTIFICATION</div><h2>认证</h2></div></div><div class="modal-body"><div class="inline-note certification-note">线下认定后添加成员，认证不限制发布方向。</div><section class="certification-section"><h3>添加成员</h3>${certificationForm()}</section><section class="certification-section"><h3>认证记录 <span class="count-pill">${(store.data.certifications || []).length}</span></h3>${certificationRows(store)}</section></div><div class="modal-footer"><button class="btn btn-secondary" data-close-modal>关闭</button></div>`, modal => {
    const root = modalRoot(modal);
    root.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', ui.closeModal));
    root.querySelector('#certification-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      if (!requireCertificationAdmin(ui)) return;
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      const error = root.querySelector('#cert-form-error');
      const name = String(form.get('name') || '').trim();
      if (!name) { error.textContent = '请填写成员姓名'; return; }
      const role = normalizeCertificationRole(form.get('role') || 'NPC');
      const level = getCertificationLevel(form.get('level'));
      const existing = (store.data.certifications || []).find(cert => cert.name === name && normalizeCertificationRole(cert.role) === role);
      const payload = { ...(existing?.id ? { id: existing.id } : {}), name, role, domain: String(form.get('domain')), level: Number(level.value), levelName: level.name, taskDifficulty: level.difficulty, status: 'verified', method: 'admin', note: existing?.note || '' };
      const button = formElement.querySelector('button[type="submit"]');
      button.disabled = true;
      error.textContent = '';
      try {
        await grantCertification(ui, payload);
        ui.toast(`${name} 已完成认证`);
        openCertification(store, ui);
      } catch (err) {
        error.textContent = err.message || '认证信息未保存，请重试';
        ui.toast(error.textContent, 'error');
      } finally { button.disabled = false; }
    });
    root.querySelectorAll('[data-cert-edit]').forEach(button => button.addEventListener('click', () => openCertificationEdit(button.dataset.certEdit, store, ui)));
  });
}

function openCertificationEdit(id, store, ui) {
  if (!requireCertificationAdmin(ui)) return;
  const cert = (store.data.certifications || []).find(item => item.id === id);
  if (!cert) { ui.toast('未找到该认证记录', 'error'); return; }
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">${e(normalizeCertificationRole(cert.role))} · ${e(cert.name)}</div><h2>${cert.status === 'pending' ? '确认认证' : '修改认证'}</h2></div></div><form id="cert-edit-form"><div class="modal-body"><label class="form-field"><span class="field-label">专业方向</span><select name="domain">${[...new Set([...domains, cert.domain])].filter(Boolean).map(domain => `<option value="${e(domain)}" ${cert.domain === domain ? 'selected' : ''}>${e(domain)}</option>`).join('')}</select></label><label class="form-field"><span class="field-label">认证等级</span><select name="level">${certificationLevelOptions(cert.level ?? cert.levelName)}</select>${certificationLevelHint()}</label>${cert.note ? `<div class="inline-note preserve-lines">原记录说明：${e(cert.note)}</div>` : ''}<p class="muted">保存后立即生效，认证不会限制发布方向。</p><div class="field-error" data-cert-edit-error role="alert"></div></div><div class="modal-footer"><button class="btn btn-secondary" type="button" data-cert-back>返回</button><button class="btn btn-primary" type="submit">${cert.status === 'pending' ? '确认通过认证' : '保存修改'}</button></div></form>`, modal => {
    const root = modalRoot(modal);
    root.querySelectorAll('[data-cert-back]').forEach(button => button.addEventListener('click', () => openCertification(store, ui)));
    root.querySelector('#cert-edit-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      if (!requireCertificationAdmin(ui)) return;
      const formElement = event.currentTarget;
      const form = new FormData(formElement);
      const currentCert = (store.data.certifications || []).find(item => item.id === id);
      if (!currentCert) { ui.toast('未找到该认证记录，请返回后重试', 'error'); return; }
      const level = getCertificationLevel(form.get('level'));
      const payload = { ...currentCert, role: normalizeCertificationRole(currentCert.role), domain: String(form.get('domain')), level: Number(level.value), levelName: level.name, taskDifficulty: level.difficulty, status: 'verified', method: 'admin' };
      const button = formElement.querySelector('button[type="submit"]');
      const error = root.querySelector('[data-cert-edit-error]');
      button.disabled = true;
      error.textContent = '';
      try {
        await grantCertification(ui, payload);
        ui.toast('认证信息已保存');
        openCertification(store, ui);
      } catch (err) {
        error.textContent = err.message || '认证信息未保存，请重试';
        ui.toast(error.textContent, 'error');
      } finally { button.disabled = false; }
    });
  });
}
