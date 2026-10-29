import { escapeHtml as e, rewardBreakdown, BADGES, getReviewCamp } from './core.js?v=20261029-reward-types';

const labels = { pending: '待审核', approved: '已通过', rejected: '已退回' };
const text = value => String(value ?? '');
const date = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—';
const count = value => Math.max(0, Math.round(Number(value) || 0)).toLocaleString('zh-CN');
const safeUrl = value => { try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : ''; } catch { return ''; } };
const downloadable = value => /^data:[a-z0-9.+\-/]+(?:;charset=[a-z0-9-]+)?;base64,[A-Za-z0-9+/]*={0,2}$/i.test(value || '');
const statusTag = status => `<span class="pub-status pub-status-${e(status)}">${e(labels[status] || status)}</span>`;
const campName = task => getReviewCamp({}, task) === 'exploration' ? '探索营' : '新手村';

export function visiblePublications(rows, userId, isSuperAdmin) {
  if (isSuperAdmin) return rows;
  const latest = new Map();
  for (const row of rows.filter(row => row.submittedBy?.id === userId)
    .slice().sort((a,b) => text(b.submittedAt).localeCompare(text(a.submittedAt)))) {
    if (!latest.has(row.taskId)) latest.set(row.taskId, row);
  }
  return [...latest.values()];
}

export function createPublicationReviewController({ store, service, ui }) {
  const state = { status: 'pending', query: '', saving: false };
  const requests = () => visiblePublications(Array.isArray(store.data.publicationRequests) ? store.data.publicationRequests : [], ui.currentUser?.id, ui.isSuperAdmin);
  const find = id => requests().find(request => request.id === id);
  const guard = () => { if (ui.isSuperAdmin) return true; ui.toast('仅超级管理员可审核任务发布', 'error'); return false; };
  const canRevise = request => !ui.isSuperAdmin && request?.status === 'rejected'
    && request.submittedBy?.id === ui.currentUser?.id
    && store.getTask(request.taskId)?.authorId === ui.currentUser?.id
    && store.getTask(request.taskId)?.publication?.id === request.id
    && store.getTask(request.taskId)?.publication?.status === 'rejected'
    && store.getTask(request.taskId)?.status !== 'archived';
  async function revise(id) {
    try {
      await store.refresh();
      const request = find(id);
      if (!canRevise(request)) { ui.closeModal(); ui.refresh(); ui.toast('任务状态已变化，请查看最新提交结果。'); return; }
      ui.closeModal();
      ui.editTask(store.getTask(request.taskId));
    } catch (error) { ui.toast(error.message || '读取任务失败，请重试', 'error'); }
  }
  function filtered() {
    const query = state.query.trim().toLocaleLowerCase();
    return requests().filter(request => request.status === state.status && (!query || `${request.task?.title || ''} ${request.submittedBy?.name || ''} ${request.task?.domain || ''}`.toLocaleLowerCase().includes(query)))
      .slice().sort((left, right) => text(right.submittedAt).localeCompare(text(left.submittedAt)));
  }
  function table() {
    const rows = filtered();
    if (!rows.length) return `<div class="pub-empty">${state.query ? '没有找到匹配的任务' : { pending: '暂无待审核的任务', approved: '暂无已通过的任务', rejected: '暂无已退回的任务' }[state.status]}</div>`;
    return `<div class="pub-table-scroll"><table class="pub-table"><thead><tr><th>任务</th><th>提交人</th><th>提交时间</th><th>状态</th>${state.status === 'rejected' ? '<th>退回原因</th>' : ''}<th>操作</th></tr></thead><tbody>${rows.map(request => {
      const task = request.task || {};
      return `<tr><td><button type="button" class="pub-task-title" data-pub-open="${e(request.id)}">${e(task.title || '未命名任务')}</button>${request.isDemo ? '<span class="pub-demo">演示</span>' : ''}<small>${e(campName(task))} · ${e(task.domain || '未设置方向')} · ${e(task.difficulty || '未设置难度')}</small></td><td><strong>${e(request.submittedBy?.name || '未记录')}</strong><small>普通管理员</small></td><td class="pub-date">${e(date(request.submittedAt))}</td><td>${statusTag(request.status)}</td>${state.status === 'rejected' ? `<td class="pub-reason-cell">${e(request.comment || '未填写退回原因')}</td>` : ''}<td><div class="pub-row-actions"><button type="button" class="text-btn" data-pub-open="${e(request.id)}">${request.status === 'pending' && ui.isSuperAdmin ? '审核任务' : '查看详情'} ${ui.icon('arrowRight', 14)}</button>${canRevise(request) ? `<button type="button" class="text-btn" data-pub-revise="${e(request.id)}">修改并重新提交</button>` : ''}</div></td></tr>`;
    }).join('')}</tbody></table></div><div class="pub-table-footer">共 ${rows.length} 条记录</div>`;
  }
  function materialRows(files, offset = 0) {
    return files.length ? files.map((file, index) => {
      const url = safeUrl(file.url);
      return `<div class="pub-material"><span>${ui.icon(file.type === 'image' ? 'image' : 'file', 16)}<span>${e(file.name || '未命名材料')}</span></span>${url ? `<a class="text-btn" href="${e(url)}" target="_blank" rel="noopener noreferrer">查看链接 ${ui.icon('external', 14)}</a>` : downloadable(file.url) ? `<button class="text-btn" type="button" data-pub-download="${offset + index}">下载文件</button>` : '<small>演示附件</small>'}</div>`;
    }).join('') : '<p class="pub-muted">未添加材料</p>';
  }
  function taskContent(task) {
    let rewards;
    try { rewards = rewardBreakdown(task); } catch { rewards = { xp: task.xp, totalPoints: 0, allocations: [] }; }
    const materials = Array.isArray(task.materials) ? task.materials : [];
    const rubricFiles = Array.isArray(task.rubricAttachments) ? task.rubricAttachments : [];
    const dimensions = Array.isArray(task.rubric) ? task.rubric : [];
    return `<div class="pub-task-meta"><span>所属营地<strong>${e(campName(task))}</strong></span><span>任务方向<strong>${e(task.domain || '—')}</strong></span><span>任务难度<strong>${e(task.difficulty || '—')}</strong></span><span>预计耗时<strong>${count(task.minutes)} 分钟</strong></span></div>
      <section class="pub-detail-section"><h3>任务简述</h3><p class="pub-summary">${e(task.summary || '未填写任务简述')}</p></section>
      <section class="pub-detail-section"><h3>学习材料 <small>${materials.length}</small></h3>${materialRows(materials)}</section>
      <section class="pub-detail-section"><h3>任务奖励</h3><div class="pub-reward-summary"><span><strong>${count(rewards.xp)}</strong> 经验值</span><span><strong>${count(rewards.totalPoints)}</strong> 徽章点</span><span>发布后可直接领取</span></div><div class="pub-reward-list">${(rewards.allocations || []).map(item => `<div><span>${e(BADGES.find(badge => badge.id === item.id)?.category || item.name || item.id)}徽章点 <small>${count(item.weight)}%</small></span><strong>${count(item.points)} 点</strong></div>`).join('')}</div></section>
      <section class="pub-detail-section"><h3>学员答案审核方式</h3><p class="pub-summary">${task.reviewMode === 'ai' ? 'AI 自测' : '人工审核'}</p></section>
      ${task.reviewMode === 'ai' ? `<section class="pub-detail-section"><h3>AI 评分标准 <small>通过分数 ${count(task.passScore)} 分</small></h3><div class="pub-rubric">${dimensions.map(dimension => `<article><header><strong>${e(dimension.name || '未命名维度')}</strong><span>${count(dimension.points)} 分</span></header><p>${e(dimension.description || '未填写评分描述')}</p></article>`).join('') || '<p class="pub-muted">未配置评分标准</p>'}</div>${rubricFiles.length ? `<div class="pub-rubric-files">${materialRows(rubricFiles, materials.length)}</div>` : ''}</section>` : ''}`;
  }
  function open(id) {
    const request = find(id);
    if (!request) { ui.toast('未找到该发布申请', 'error'); return; }
    const task = request.task || {};
    const pending = request.status === 'pending' && ui.isSuperAdmin;
    ui.openModal(`<div class="modal-header pub-modal-header"><div class="pub-request-status">${statusTag(request.status)}${request.isDemo ? '<span class="pub-demo">演示任务</span>' : ''}</div><h2>${e(task.title || '任务发布审核')}</h2><p>${e(request.submittedBy?.name || '未记录')} 提交 · ${e(date(request.submittedAt))}</p></div><div class="pub-detail-body">${taskContent(task)}${request.status === 'pending' && !ui.isSuperAdmin ? '<section class="pub-decision-section"><h3>发布审核</h3><p class="pub-muted">等待超级管理员审核，审核期间暂不能修改。</p></section>' : pending ? `<section class="pub-decision-section"><h3>发布审核</h3><div class="pub-decision-options" role="radiogroup" aria-label="审核决定"><button type="button" role="radio" aria-checked="true" class="active" data-pub-decision="approved">${ui.icon('checkCircle', 16)} 通过发布</button><button type="button" role="radio" aria-checked="false" data-pub-decision="rejected">${ui.icon('arrowLeft', 16)} 退回修改</button></div><label class="pub-return-field" data-pub-return-field hidden><span>退回原因 <i>*</i></span><textarea data-pub-comment rows="3" maxlength="1000" placeholder="写明需要修改的内容，便于提交人调整后重新提交"></textarea></label><p class="pub-decision-hint" data-pub-decision-hint>通过后任务立即发布，学员可直接领取。</p><p class="pub-error" role="alert" data-pub-error></p></section>` : `<section class="pub-decision-section"><h3>审核记录</h3><div class="pub-reviewed-meta"><span>审核人：${e(request.reviewedBy?.name || '未记录')}</span><span>${e(date(request.reviewedAt))}</span></div>${request.status === 'rejected' ? `<p class="pub-return-reason">${e(request.comment || '未填写退回原因')}</p>` : `<p class="pub-muted">任务已审核通过并发布。</p>${request.comment ? `<p class="pub-summary">${e(request.comment)}</p>` : ''}`}</section>`}</div><div class="modal-footer pub-modal-footer"><button class="btn btn-secondary" type="button" data-pub-close>${pending ? '取消' : '关闭'}</button>${pending ? '<button class="btn btn-primary" type="button" data-pub-submit>审核通过并发布</button>' : canRevise(request) ? `<button class="btn btn-primary" type="button" data-pub-revise="${e(request.id)}">修改并重新提交</button>` : ''}</div>`, modal => {
      modal.classList.add('pub-review-modal');
      modal.querySelector('[data-pub-close]').onclick = ui.closeModal;
      modal.querySelector('[data-pub-revise]')?.addEventListener('click', () => revise(id));
      const files = [...(task.materials || []), ...(task.rubricAttachments || [])];
      modal.querySelectorAll('[data-pub-download]').forEach(button => button.onclick = () => {
        const file = files[Number(button.dataset.pubDownload)];
        if (!file || !downloadable(file.url)) return;
        const link = document.createElement('a'); link.href = file.url; link.download = file.name || '任务材料'; link.click();
      });
      if (!pending) return;
      let decision = 'approved';
      const submit = modal.querySelector('[data-pub-submit]');
      const comment = modal.querySelector('[data-pub-comment]');
      const error = modal.querySelector('[data-pub-error]');
      modal.querySelectorAll('[data-pub-decision]').forEach(button => button.onclick = () => {
        if (state.saving) return;
        decision = button.dataset.pubDecision;
        modal.querySelectorAll('[data-pub-decision]').forEach(option => { const selected = option === button; option.classList.toggle('active', selected); option.setAttribute('aria-checked', String(selected)); });
        modal.querySelector('[data-pub-return-field]').hidden = decision !== 'rejected';
        modal.querySelector('[data-pub-decision-hint]').textContent = decision === 'approved' ? '通过后任务立即发布，学员可直接领取。' : '退回后本次内容不会发布，提交人可修改后重新提交；已有线上版本保持不变。';
        submit.textContent = decision === 'approved' ? '审核通过并发布' : '确认退回';
        submit.className = `btn ${decision === 'approved' ? 'btn-primary' : 'btn-danger'}`;
        if (decision === 'approved') comment.value = '';
        error.textContent = '';
      });
      comment.oninput = () => { error.textContent = ''; };
      submit.onclick = async () => {
        if (!guard() || state.saving) return;
        const reason = decision === 'rejected' ? comment.value.trim() : '';
        if (decision === 'rejected' && !reason) { error.textContent = '请填写退回原因'; comment.focus(); return; }
        if (find(id)?.status !== 'pending') { error.textContent = '该申请已被处理，请关闭后查看最新状态'; return; }
        state.saving = true;
        const actorId = ui.currentUser?.id;
        modal.dataset.operationPending='true';
        modal.querySelectorAll('button,input,textarea').forEach(control => { control.disabled = true; });
        submit.textContent = '正在提交…';
        try {
          await service.tasks.reviewPublication(id, { decision, comment: reason });
          modal.dataset.operationPending='false';
          if (modal.isConnected) ui.closeModal();
          if (ui.currentUser?.id === actorId) { ui.refresh(); ui.toast(decision === 'approved' ? '审核通过，任务已发布' : '任务已退回修改'); }
        } catch (err) { if (modal.isConnected) error.textContent = err.message || '审核提交失败，请重试'; }
        finally {
          state.saving = false;modal.dataset.operationPending='false';
          modal.querySelectorAll('button,input,textarea').forEach(control=>control.disabled=false);
          if (modal.isConnected) { modal.querySelectorAll('[data-pub-decision], [data-pub-submit], [data-pub-comment]').forEach(control => { control.disabled = false; }); submit.textContent = decision === 'approved' ? '审核通过并发布' : '确认退回'; }
        }
      };
    });
  }
  return {
    render() {
      return `<section class="publication-review-page"><header class="pub-page-heading"><h1>${ui.isSuperAdmin ? '审核待发布的任务' : '我的发布'}</h1></header><div class="pub-toolbar"><div class="pub-tabs" role="tablist" aria-label="发布审核状态">${Object.entries(labels).map(([status, label]) => `<button type="button" role="tab" aria-selected="${state.status === status}" class="${state.status === status ? 'active' : ''}" data-pub-status="${status}">${label}<span>${requests().filter(request => request.status === status).length}</span></button>`).join('')}</div><label class="pub-search">${ui.icon('search', 16)}<input type="search" data-pub-search value="${e(state.query)}" placeholder="${ui.isSuperAdmin ? '搜索任务或提交人' : '搜索我的任务'}" aria-label="${ui.isSuperAdmin ? '搜索任务或提交人' : '搜索我的任务'}"></label></div><div data-pub-results>${table()}</div></section>`;
    },
    bind(root) {
      const page = root.querySelector('.publication-review-page');
      if (!page) return;
      page.onclick = event => { const button = event.target.closest('button'); if (!button || !page.contains(button)) return; if (button.dataset.pubStatus) { state.status = button.dataset.pubStatus; state.query = ''; ui.refresh(); } else if (button.dataset.pubOpen) open(button.dataset.pubOpen); else if (button.dataset.pubRevise) void revise(button.dataset.pubRevise); };
      page.querySelector('[data-pub-search]').oninput = event => { state.query = event.target.value; page.querySelector('[data-pub-results]').innerHTML = table(); };
    },
    badgeCount() { return requests().filter(row => row.status === (ui.isSuperAdmin ? 'pending' : 'rejected')).length; },
    reset() { state.status = 'pending'; state.query = ''; state.saving = false; },
  };
}
