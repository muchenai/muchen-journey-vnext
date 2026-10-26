import { BADGES, FAILURE_REASONS, getSubmissionStatus, getSubmissionFailureReasons, getReviewCamp, escapeHtml as e, icon, rewardBreakdown } from './core.js?v=20261021-review-decision';
import { reviewFeedbackError } from './native-model.js';

const campStates = { exploration: { tab: 'pending', query: '' }, novice: { tab: 'pending', query: '' } };
let currentCamp = 'novice';
let state = campStates.novice;
const campFromUi = ui => ui.reviewCamp === 'exploration' ? 'exploration' : 'novice';
const campLabel = camp => camp === 'exploration' ? '探索营' : '新手村';
const campOf = (store, submission) => getReviewCamp(submission, taskOf(store, submission)) === 'exploration' ? 'exploration' : 'novice';
function selectCamp(ui) { currentCamp = campFromUi(ui); state = campStates[currentCamp]; }
const num = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const hasScore = value => value !== null && value !== undefined && String(value).trim() !== '' && Number.isFinite(Number(value));
const fmt = value => Number.isInteger(num(value)) ? String(num(value)) : num(value).toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
const iconFor = name => { try { return icon(({ 'arrow-right': 'arrowRight', 'file-text': 'file', 'external-link': 'external', 'chevron-down': 'chevronDown' })[name] || name, 16); } catch { return ''; } };

function taskOf(store, submission) {
  return submission.taskSnapshot || store.getTask(submission.taskId) || { title: '任务已归档', passScore: 60, xp: 0, taskPoints: 0, badges: [] };
}
function modeOf(store, submission) {
  return submission.reviewMode || taskOf(store, submission).reviewMode || 'manual';
}
function statusOf(store, submission) {
  if (submission.status === 'historical') return 'historical';
  return getSubmissionStatus(submission, taskOf(store, submission));
}
const failedStatus = status => status === 'returned' || status === 'ai_failed';
const failureCodes = (store, submission) => getSubmissionFailureReasons(submission, taskOf(store, submission));
const reasonLabel = id => FAILURE_REASONS.find(reason => reason.id === id)?.label || id;
const failureText = (store, submission) => { const codes = failureCodes(store, submission); return codes.length ? codes.map(reasonLabel).join('、') : '原因未记录'; };
function dateLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || '—';
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Shanghai' });
}
function dateFull(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? (value || '—') : date.toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' });
}
function statusBadge(store, submission) {
  const status = statusOf(store, submission);
  if (status === 'pending' && submission.claim) return '<span class="badge badge-purple">正在审核</span>';
  const labels = { historical: '历史提交', pending: num(submission.attempt) > 1 ? '重新提交·待审核' : '待人工审核', passed: '审核通过', returned: '审核未通过', ai_failed: '审核未通过', evaluating: '评测中' };
  return `<span class="badge ${status === 'passed' ? 'badge-success' : failedStatus(status) ? 'badge-warning' : 'badge-purple'}">${labels[status] || '待处理'}</span>`;
}
function submissionsInTab(store, tab) {
  return (store.data.submissions || []).filter(submission => {
    if (campOf(store, submission) !== currentCamp) return false;
    if (submission.supersededBy) return false;
    const status = statusOf(store, submission);
    if (tab === 'pending') return status === 'pending' && !submission.claim && modeOf(store, submission) === 'manual';
    if (tab === 'reviewing') return status === 'pending' && !!submission.claim && modeOf(store, submission) === 'manual';
    if (tab === 'ai') return submission.hasAi === true;
    if (tab === 'reviewed') return status === 'passed' || failedStatus(status);
    if (tab === 'passed') return status === 'passed';
    return tab === 'failed' && failedStatus(status);
  });
}
function filteredSubmissions(store) {
  const query = state.query.trim().toLocaleLowerCase();
  return submissionsInTab(store, state.tab).filter(submission => !query || `${submission.studentName || ''} ${taskOf(store, submission).title || ''}`.toLocaleLowerCase().includes(query)).sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt));
}
const tableColumns = {
  pending: ['学员', '任务', '提交时间', '状态', '操作'],
  reviewing: ['学员', '任务', '提交时间', '正在审核人', '开始审核时间', '操作'],
  ai: ['学员', '任务', '自测状态', '自测时间', '操作'],
  reviewed: ['学员', '任务', '评分', '提交时间', '状态', '实际审核人', '审核时间', '操作'],
  passed: ['学员', '任务', '评分', '提交时间', '实际审核人', '审核时间', '操作'],
  failed: ['学员', '任务', '提交时间', '未通过原因', '实际审核人', '审核时间', '操作'],
};
function renderRows(store) {
  const rows = filteredSubmissions(store);
  if (!rows.length) return `<tr><td colspan="${tableColumns[state.tab].length}"><div class="empty-state review-empty"><div class="empty-icon">${iconFor('inbox')}</div><strong>${campLabel(currentCamp)}${state.query ? '没有匹配的提交' : state.tab === 'pending' ? '暂无待审核答案' : '暂无相关记录'}</strong><p>学员提交后，记录将在这里展示。</p></div></td></tr>`;
  return rows.map(submission => {
    const task = taskOf(store, submission);
    const aiMode = modeOf(store, submission) === 'ai';
    const status = statusOf(store, submission);
    const action = submission.claim ? (submission.claim.mine ? '继续审核' : '他人审核中') : status === 'pending' && state.tab !== 'ai' ? '去审核' : '查看详情';
    const cells = {
      '学员': `<div class="student-cell"><span class="avatar avatar-small">${e((submission.studentName || '学员').slice(-2))}</span><div><strong>${e(submission.studentName || '未命名学员')}</strong><span class="cell-subtext">${e(submission.studentIsFeishu ? (submission.studentEmployeeNo ? `工号：${submission.studentEmployeeNo}` : '工号未填写') : (submission.studentPhone ? `手机号：${submission.studentPhone}` : '手机号未补充'))}</span></div></div>`,
      '任务': `<span class="table-task-title">${e(task.title)}</span><span class="cell-subtext">${e(task.domain || '综合能力')} · ${aiMode ? 'AI 自测' : '人工审核'}</span>${num(submission.attempt) > 1 ? `<span class="review-attempt">第 ${fmt(submission.attempt)} 次提交</span>` : ''}`,
      '评分': hasScore(submission.finalScore) ? `${fmt(submission.finalScore)} / 100` : '—',
      '提交时间': e(dateLabel(submission.submittedAt)),
      '状态': statusBadge(store, submission),
      '未通过原因': e(failureText(store, submission)),
      '实际审核人': e(submission.actualReviewer?.name || '未记录'),
      '审核时间': e(submission.reviewedAt ? dateFull(submission.reviewedAt) : '未记录'),
      '正在审核人': e(submission.claim?.owner_name || '—'),
      '开始审核时间': e(submission.claim ? dateFull(submission.claim.started_at) : '—'),
      '自测状态': e(submission.aiStatus || '暂无自查记录'),
      '自测时间': e(submission.aiCheckedAt ? dateFull(submission.aiCheckedAt) : '—'),
      '操作': `<button class="btn btn-text" type="button" data-review-open="${e(submission.id)}">${action}${iconFor('arrow-right')}</button>${state.tab === 'reviewing' && store.capabilities?.canGrantSuperAdmins ? `<button class="btn btn-text" type="button" data-review-force-release="${e(submission.id)}">释放占用</button>` : ''}`,
    };
    return `<tr>${tableColumns[state.tab].map(column => `<td>${cells[column]}</td>`).join('')}</tr>`;
  }).join('');
}

export function renderReview(store, ui) {
  selectCamp(ui);
  const pending = submissionsInTab(store, 'pending').length;
  const reviewing = submissionsInTab(store, 'reviewing').length;
  const aiResults = submissionsInTab(store, 'ai').length;
  const reviewed = submissionsInTab(store, 'reviewed').length;
  const passed = submissionsInTab(store, 'passed').length;
  const failed = submissionsInTab(store, 'failed').length;
  const tabs = [{ id: 'pending', label: '待人工审核', count: pending }, { id: 'reviewing', label: '正在审核', count: reviewing }, { id: 'ai', label: 'AI 自测结果', count: aiResults }, { id: 'reviewed', label: '已审核', count: reviewed }, { id: 'passed', label: '审核通过', count: passed }, { id: 'failed', label: '审核未通过', count: failed }];
  const notes = { pending: '查看学员答案，确认通过或退回修改。', reviewing: '已领取的提交仅允许当前审核人处理。关闭后最多 2 分钟自动释放，也可主动退出审核。', ai: '查看 AI 自测结果与评测进度。', reviewed: '查看已审核的提交，包括审核通过和审核未通过。', passed: '查看已审核通过的提交。', failed: '查看未通过原因和具体修改建议。' };
  return `<div class="page-content review-page" data-review-page>
    <div class="stats-grid">
      <div class="stat-card"><span class="stat-label">待人工审核</span><div class="stat-value">${pending}<span class="stat-unit">份</span></div><span class="stat-note">等待导师审核学员答案</span></div>
      <div class="stat-card"><span class="stat-label">AI 自测结果</span><div class="stat-value">${aiResults}<span class="stat-unit">份</span></div><span class="stat-note">自测结果与评测进度</span></div>
      <div class="stat-card"><span class="stat-label">已审核</span><div class="stat-value">${reviewed}<span class="stat-unit">份</span></div><span class="stat-note">包含审核通过与审核未通过</span></div>
      <div class="stat-card"><span class="stat-label">审核未通过</span><div class="stat-value">${failed}<span class="stat-unit">份</span></div><span class="stat-note">等待学员修改重提</span></div>
    </div>
    <section class="card review-card">
      <div class="card-header review-toolbar"><div class="tabs">${tabs.map(tab => `<button class="tab ${state.tab === tab.id ? 'active' : ''}" type="button" data-review-tab="${tab.id}">${tab.label}<span class="count-badge">${tab.count}</span></button>`).join('')}</div><div class="search-field">${iconFor('search')}<input class="search-input" type="search" aria-label="搜索任务或学员" placeholder="搜索任务或学员" value="${e(state.query)}" data-review-search></div></div>
      <div class="review-tab-note"><span class="status-dot ${state.tab === 'pending' ? 'dot-purple' : 'dot-green'}"></span>${notes[state.tab]}</div>
      <div class="table-wrap" data-review-table><table class="data-table"><thead><tr>${tableColumns[state.tab].map(label => `<th>${label}</th>`).join('')}</tr></thead><tbody data-review-rows>${renderRows(store)}</tbody></table></div>
      <div class="table-footer"><span data-review-count>共 ${filteredSubmissions(store).length} 条记录</span><span class="muted">学员提交后自动更新审核记录</span></div>
    </section>
  </div>`;
}

function safeUrl(value) {
  try { const url = new URL(String(value)); return ['https:', 'http:'].includes(url.protocol) ? url.href : ''; } catch { return ''; }
}
function renderFiles(files, emptyText) {
  if (!Array.isArray(files) || !files.length) return `<p class="muted">${e(emptyText)}</p>`;
  return `<div class="file-list">${files.map((file, index) => {
    const item = typeof file === 'string' ? { name: file, url: file } : file;
    const source = item.url || item.link || '';
    const href = safeUrl(source);
    const download = typeof source === 'string' && /^data:[^;,]+;base64,[A-Za-z0-9+/=\r\n]+$/.test(source);
    const name = item.name || item.title || `附件 ${index + 1}`;
    if (item.type === 'text' && item.text) return `<div><strong>${e(name)}</strong><p class="answer-text">${e(item.text)}</p></div>`;
    const content = `${iconFor('file-text')}<span>${e(name)}</span>${href ? iconFor('external-link') : '<span class="muted file-meta">附件</span>'}`;
    return href ? `<a class="file-chip" href="${e(href)}" target="_blank" rel="noopener noreferrer">${content}</a>` : download ? `<a class="file-chip" href="${e(source)}" download="${e(name)}">${iconFor('download')}<span>${e(name)}</span><span class="muted file-meta">下载</span></a>` : `<span class="file-chip">${content}</span>`;
  }).join('')}</div>`;
}
function renderRubric(task) {
  const rubric = task.rubric || task.rubrics || [];
  const dimensions = Array.isArray(rubric) ? rubric : rubric.dimensions || [];
  return `${typeof rubric === 'string' ? `<p class="answer-text">${e(rubric)}</p>` : rubric.description ? `<p class="answer-text">${e(rubric.description)}</p>` : ''}${dimensions.length ? `<div class="rubric-list">${dimensions.map(item => `<div class="rubric-item"><div><strong>${e(item.name || item.title || '评分维度')}</strong><span class="badge badge-neutral">${fmt(item.max ?? item.maxScore ?? item.score ?? item.points ?? 0)} 分</span></div><p>${e(item.description || item.criteria || '')}</p></div>`).join('')}</div>` : '<p class="muted">暂无在线评分维度。</p>'}${renderFiles(task.rubricAttachments || task.rubricFiles || [], '未附加评分文档')}`;
}
function badgeName(id) {
  if (Array.isArray(BADGES)) return BADGES.find(badge => badge.id === id)?.name || id;
  return BADGES?.[id]?.name || BADGES?.[id] || id;
}
function rewardsFor(task) {
  try {
    const result = rewardBreakdown(task);
    if (Array.isArray(result)) return result;
    if (Array.isArray(result?.allocations)) return result.allocations;
    if (Array.isArray(result?.badges)) return result.badges;
    if (Array.isArray(result?.items)) return result.items;
  } catch { /* Fall back to task fields for incomplete drafts. */ }
  return (task.badges || []).map(badge => ({ ...badge, name: badgeName(badge.id), points: num(task.xp) / 10 * num(badge.weight) / 100 }));
}
function submissionRewards(store, submission, task) {
  const claim = store.data.claims?.[`${submission.studentId}:${submission.taskId}`];
  const claimed = Boolean(submission.rewarded || claim);
  const hasSnapshot = Boolean(claim && Number.isFinite(Number(claim.xp)) && Number.isFinite(Number(claim.taskPoints)) && Array.isArray(claim.allocations));
  return {
    claimed,
    missingSnapshot: claimed && !hasSnapshot,
    xp: hasSnapshot ? claim.xp : task.xp,
    taskPoints: hasSnapshot ? claim.taskPoints : task.taskPoints,
    allocations: hasSnapshot ? claim.allocations : rewardsFor(task),
  };
}
function renderDetail(store, submission) {
  const task = taskOf(store, submission);
  const camp = campOf(store, submission);
  const previousSubmission = (store.data.submissions || []).find(item => item.id === submission.previousSubmissionId && campOf(store, item) === camp);
  const nextSubmission = (store.data.submissions || []).find(item => item.id === submission.supersededBy && campOf(store, item) === camp);
  const manual = modeOf(store, submission) === 'manual';
  const status = statusOf(store, submission);
  const editable = manual && status === 'pending' && submission.canReview && !submission.supersededBy && state.tab !== 'ai';
  const ai = submission.ai || { score: 0, comment: '暂无 AI 评测结果。', dimensions: [] };
  const dimensions = Array.isArray(ai.dimensions) ? ai.dimensions : [];
  const rewards = submissionRewards(store, submission, task);
  const badges = rewards.allocations;
  const answer = typeof submission.answer === 'string' ? submission.answer : JSON.stringify(submission.answer || '', null, 2);
  const feedback = manual ? submission.reviewComment || submission.comment : ai.comment || submission.reviewComment || submission.comment;
  return `<div class="review-detail">
    <div class="review-detail-heading"><div><div class="eyebrow">${manual ? 'MANUAL REVIEW' : 'AI SELF-ASSESSMENT'}</div><h2>${editable ? '审核学员答案' : '提交详情'}</h2><p class="muted">${e(submission.studentName || '学员')} · ${e(dateFull(submission.submittedAt))}</p></div></div>
    <div class="review-detail-meta"><strong>${e(task.title)}</strong>${statusBadge(store, submission)}<span class="badge badge-neutral">${manual ? '人工审核' : 'AI 自测'}</span><span class="badge badge-neutral">${campLabel(camp)}</span></div>
    ${num(submission.attempt) > 1 || previousSubmission || nextSubmission ? `<div class="review-attempt">${num(submission.attempt) > 1 ? `第 ${fmt(submission.attempt)} 次提交` : '提交历史'}${previousSubmission ? `<button class="btn btn-text" type="button" data-review-history="${e(previousSubmission.id)}">查看上次提交</button>` : ''}${nextSubmission ? `<button class="btn btn-text" type="button" data-review-history="${e(nextSubmission.id)}">已有新提交，查看详情</button>` : ''}</div>` : ''}
    ${failedStatus(status) ? `<section class="rejection-feedback"><h3>${status === 'returned' ? '退回原因' : '未通过原因'}</h3><div class="rejection-reasons">${e(failureText(store, submission))}</div><h4>具体修改建议</h4><p class="answer-text">${e(feedback || '暂无具体建议，请联系导师补充。')}</p><p class="small muted">${rewards.claimed ? '修改后重新提交；本任务已有奖励发放记录，不会重复发放。' : '修改后重新提交，当前未发放奖励。'}</p></section>` : ''}
    <div class="review-detail-grid">
      <div class="review-answer-column">
        <section class="detail-section"><h3>学员提交答案</h3><div class="answer-text answer-box">${textLinks(answer || '学员未填写文字答案。')}</div>${renderFiles(submission.attachments || [], '本次提交无附件')}</section>
        <details class="review-reference"><summary>任务要求与学习材料${iconFor('chevron-down')}</summary><div class="review-reference-content"><h4>任务要求</h4>${Array.isArray(task.questions) && task.questions.length ? task.questions.map((question, index) => `<div class="review-task-question"><strong>${index + 1}. ${e(question.title)}</strong><p class="answer-text">${e(question.description || '')}</p></div>`).join('') : `<p class="answer-text">${e(task.instructions || task.requirements || task.question || task.description || task.summary || '暂无补充说明')}</p>`}<h4>学习材料</h4>${renderFiles(task.materials || [], '暂无学习材料')}</div></details>
        ${manual ? '' : `<details class="review-reference"><summary>AI 评分标准（Rubric）${iconFor('chevron-down')}</summary><div class="review-reference-content">${renderRubric(task)}</div></details>`}
      </div>
      <div class="review-evaluation-column">
        ${!submission.hasAi ? '' : `<section class="detail-section ai-result"><div class="section-title-row"><h3>${iconFor('sparkles')} AI 评测</h3><span class="badge badge-neutral">不计分 · 仅供参考</span></div><div class="ai-comment"><strong>AI 评语与历史记录</strong><p class="answer-text ai-answer-scroll" tabindex="0" role="region" aria-label="AI 评语与历史记录，可滚动查看">${e(ai.comment || '暂无评语')}</p></div></section>`}
        <section class="detail-section review-rewards"><h3>任务奖励配置</h3><div class="reward-inline"><span><strong>+${fmt(rewards.xp)}</strong> 经验值</span><span><strong>+${fmt(rewards.taskPoints)}</strong> 任务点</span></div><div class="review-badge-rewards">${badges.map(badge => `<div><span>${e(badge.name || badgeName(badge.id))}</span><strong>+${fmt(badge.points ?? badge.value)} 徽章点</strong></div>`).join('')}</div><p class="small muted">以上为任务配置，实际奖励发放记录尚未接入此页面。</p></section>
      </div>
    </div>
    ${editable ? `<section class="review-final-section"><div class="section-title-row"><h3>最终审核</h3><span class="muted">审核结果将同步到学员端</span></div><div class="review-final-grid"><label class="form-field"><span>审核得分 <span class="muted">选填</span></span><div class="input-suffix"><input class="form-input" data-review-score type="number" min="0" max="100" step="1" value="" placeholder="可不填写" aria-label="审核得分（选填）"><span>/ 100</span></div><small>由导师直接决定是否通过，不设通过分数线。</small></label><label class="form-field"><span>审核评语 <span class="muted">通过时选填，退回时至少 5 个字</span></span><textarea class="form-textarea" data-review-comment rows="3" maxlength="2000" placeholder="通过时可不填写；退回时请填写至少 5 个字的修改建议，空格和换行不计入">${e(submission.reviewComment || '')}</textarea></label></div><fieldset class="return-reason-options"><legend>退回原因 <span class="muted">退回时至少选择一项</span></legend>${FAILURE_REASONS.map(reason => `<label><input type="checkbox" value="${e(reason.id)}" data-review-reason-code><span>${e(reason.label)}</span></label>`).join('')}</fieldset><p class="inline-error" data-review-error role="alert" hidden></p></section><div class="modal-footer"><button class="btn btn-secondary" type="button" data-review-exit>退出审核</button><div class="button-group"><button class="btn btn-danger" type="button" data-review-decision="returned">退回修改</button><button class="btn btn-primary" type="button" data-review-decision="passed">${iconFor('check')}确认通过</button></div></div>` : status === 'pending' ? '<section class="review-final-section"><h3>尚未完成人工审核</h3><p>AI 自测仅供参考，请从审核列表领取后进行人工审核。</p></section><div class="modal-footer"><button class="btn btn-secondary" data-review-close>关闭</button></div>' : `<section class="review-final-section"><h3>${manual ? '最终审核结果' : '自动评测结果'}</h3>${manual ? `<p class="review-attribution">实际审核人：<strong>${e(submission.actualReviewer?.name || '未记录')}</strong><br>审核时间：${e(submission.reviewedAt ? dateFull(submission.reviewedAt) : '未记录')}</p>` : ''}<div class="review-result-line">${statusBadge(store, submission)}<span>${manual ? `导师评分 <strong>${hasScore(submission.finalScore) ? `${fmt(submission.finalScore)} / 100` : '—'}</strong>` : `最终得分 <strong>${fmt(submission.finalScore ?? ai.score)}</strong> / 100`}</span></div><p class="answer-text">${e(manual ? (submission.reviewComment || '审核人未补充评语。') : (ai.comment || 'AI 已根据评分标准完成自测。'))}</p><p class="small muted">${manual ? '该记录由导师完成审核，仅供查看。' : 'AI 自测由系统自动判定，无需人工审核。本原型使用模拟 AI 数据。'}</p></section><div class="modal-footer"><span></span><button class="btn btn-secondary" type="button" data-review-close>关闭</button></div>`}
  </div>`;
}

export async function openSubmission(store, ui, id) {
  selectCamp(ui);
  const initial = store.data.submissions.find(s => s.id === id);
  const wantsClaim = initial && !initial.historical && initial.status === 'pending' && state.tab !== 'ai';
  try {
    if (wantsClaim && store.updateReviewClaim) await store.updateReviewClaim(id, 'acquire');
    await store.loadSubmission(id);
  } catch (error) { ui.toast(error.message,'error'); try { await store.refresh?.(); ui.refresh?.(); } catch { /* Retry by polling. */ } return; }
  selectCamp(ui);
  const submission = (store.data.submissions || []).find(item => item.id === id);
  if (!submission) { ui.toast('未找到这条提交记录', 'error'); return; }
  if (campOf(store, submission) !== campFromUi(ui)) { ui.toast('该记录不属于当前营地', 'error'); return; }
  if (wantsClaim && store.updateReviewClaim) ui.refresh?.();
  ui.openModal(renderDetail(store, submission), modal => {
    modal.classList.add('review-modal');
    modal.querySelectorAll('[data-review-close]').forEach(button => { button.onclick = () => ui.closeModal(); });
    modal.querySelectorAll('[data-review-history]').forEach(button => { button.onclick = () => openSubmission(store, ui, button.dataset.reviewHistory); });
    const reasonInputs = [...modal.querySelectorAll('[data-review-reason-code]')];
    const decisionButtons = [...modal.querySelectorAll('[data-review-decision]')];
    const passButton = modal.querySelector('[data-review-decision="passed"]');
    let saving = false;
    let leaseLost = false;
    let leaseTimer;
    let stopped = false;
    let renewing = false;
    const stopLease = () => { stopped = true; clearInterval(leaseTimer); };
    const release = async () => {
      stopLease();
      if (store.reviewLeases?.has(id)) await store.updateReviewClaim(id, 'release');
    };
    const updateList = async () => { try { await store.refresh?.(); ui.refresh?.(); } catch { /* Poll retries. */ } };
    modal.addEventListener?.('review-close', () => {
      release().catch(() => ui.toast('连接中断，占用将在最后一次续期后 2 分钟内释放。', 'error')).finally(updateList);
    }, { once: true });
    modal.querySelector('[data-review-exit]')?.addEventListener('click', async () => {
      if (saving) return;
      try { await release(); ui.closeModal(); await updateList(); }
      catch (error) { ui.toast(error.message, 'error'); }
    });
    let reasonHint;
    if (passButton) {
      reasonHint = document.createElement('p');
      reasonHint.id = 'review-decision-hint';
      reasonHint.className = 'field-hint';
      reasonHint.setAttribute('role', 'status');
      reasonHint.textContent = '已选择退回原因，请退回修改，或取消勾选后确认通过。';
      modal.querySelector('.return-reason-options')?.insertAdjacentElement('afterend', reasonHint);
      passButton.setAttribute('aria-describedby', reasonHint.id);
    }
    const updateDecisionState = () => {
      const hasReasons = reasonInputs.some(input => input.checked);
      decisionButtons.forEach(button => { button.disabled = saving || leaseLost || (button.dataset.reviewDecision === 'passed' && hasReasons); });
      reasonInputs.forEach(input => { input.disabled = saving; });
      if (reasonHint) reasonHint.hidden = !hasReasons;
    };
    reasonInputs.forEach(input => input.addEventListener('change', updateDecisionState));
    updateDecisionState();
    if (wantsClaim && store.reviewLeases?.has(id)) {
      leaseTimer = setInterval(async () => {
        if (stopped || renewing || saving) return;
        renewing = true;
        try { await store.updateReviewClaim(id, 'renew'); }
        catch (error) {
          stopLease(); leaseLost = true; updateDecisionState();
          const errorBox = modal.querySelector('[data-review-error]');
          if (errorBox) { errorBox.textContent = `${error.message} 请退出后重新进入审核。`; errorBox.hidden = false; }
        } finally { renewing = false; }
      }, 30000);
    }
    modal.querySelectorAll('[data-review-decision]').forEach(button => {
      button.onclick = async () => {
        if (saving || leaseLost) return;
        const decision = button.dataset.reviewDecision;
        const scoreInput = modal.querySelector('[data-review-score]');
        const rawScore = scoreInput?.value ?? '';
        const score = rawScore.trim() === '' ? null : Number(rawScore);
        const comment = modal.querySelector('[data-review-comment]')?.value.trim() || '';
        const reasonCodes = [...modal.querySelectorAll('[data-review-reason-code]:checked')].map(input => input.value);
        const error = modal.querySelector('[data-review-error]');
        const fail = message => { error.textContent = message; error.hidden = false; };
        if (campOf(store, submission) !== campFromUi(ui)) { fail('当前营地已切换，请返回对应营地审核。'); return; }
        if (statusOf(store, submission) !== 'pending' || modeOf(store, submission) !== 'manual' || submission.supersededBy) { fail('该提交已完成处理，请刷新后查看。'); return; }
        if (decision === 'passed' && reasonCodes.length) { fail('已选择退回原因，请取消勾选后再确认通过。'); updateDecisionState(); return; }
        if (score !== null && (!Number.isFinite(score) || score < 0 || score > 100)) { fail('选填得分需在 0～100 之间。'); scoreInput?.focus(); return; }
        if (decision === 'returned' && !reasonCodes.length) { fail('请至少选择一项退回原因。'); modal.querySelector('[data-review-reason-code]')?.focus(); return; }
        const feedbackError = reviewFeedbackError(decision, comment);
        if (feedbackError) { fail(feedbackError); modal.querySelector('[data-review-comment]')?.focus(); return; }
        error.hidden = true;
        modal.dataset.operationPending = 'true';
        saving = true;
        updateDecisionState();
        try {
          const payload = { decision, score, comment, reasonCodes };
          const result = ui.service ? await ui.service.submissions.review(id, payload) : await store.reviewSubmission(id, payload);
          if (result === false || result?.ok === false || result?.error) throw new Error(result?.error || result?.message || '审核未能保存，请重试。');
          modal.dataset.operationPending = 'false';
          stopLease();
          ui.closeModal();
          ui.refresh();
          ui.toast(decision === 'passed' ? '审核已保存，学员端状态已更新' : '已退回修改，审核意见已保存', 'success');
        } catch (err) {
          fail(err.message || '保存失败，请重试。');
          modal.dataset.operationPending = 'false';
          saving = false;
          updateDecisionState();
        }
      };
    });
  });
}

export function bindReview(root, store, ui) {
  selectCamp(ui);
  const page = root.querySelector('[data-review-page]');
  if (!page) return;
  page.onclick = async event => {
    selectCamp(ui);
    const tab = event.target.closest('[data-review-tab]');
    if (tab) { state.tab = tab.dataset.reviewTab; ui.refresh(); return; }
    const release = event.target.closest('[data-review-force-release]');
    if (release) {
      const id = release.dataset.reviewForceRelease;
      const item = store.data.submissions.find(s => s.id === id);
      if (!item?.claim) return;
      ui.openModal(`<div class="modal-heading"><h2>释放审核占用</h2></div><p>正在审核人：${e(item.claim.owner_name)}。释放后，原审核窗口将不能提交结果，其他审核员可以重新领取。</p><div class="modal-footer"><button class="btn btn-secondary" data-release-cancel>取消</button><button class="btn btn-danger" data-release-confirm>确认释放</button></div>`, modal => {
        modal.querySelector('[data-release-cancel]').onclick = () => ui.closeModal();
        modal.querySelector('[data-release-confirm]').onclick = async () => {
          try { await store.updateReviewClaim(id, 'force_release', item.claim.version); ui.closeModal(); await store.refresh(); ui.refresh(); ui.toast('已释放审核占用', 'success'); }
          catch (error) { ui.toast(error.message, 'error'); }
        };
      });
      return;
    }
    const history = event.target.closest('[data-review-history]');
    if (history) { openSubmission(store, ui, history.dataset.reviewHistory); return; }
    const button = event.target.closest('[data-review-open]');
    if (button) openSubmission(store, ui, button.dataset.reviewOpen);
  };
  const search = page.querySelector('[data-review-search]');
  const updateRows = () => {
    selectCamp(ui);
    page.querySelector('[data-review-rows]').innerHTML = renderRows(store);
    page.querySelector('[data-review-count]').textContent = `共 ${filteredSubmissions(store).length} 条记录`;
  };
  if (search) search.oninput = () => {
    selectCamp(ui);
    state.query = search.value;
    updateRows();
  };
}

function textLinks(text) {
  return String(text).split(/(https?:\/\/[^\s<>"']+)/g).map(part => {
    const href = /^https?:\/\//.test(part) ? safeUrl(part) : '';
    return href ? `<a href="${e(href)}" target="_blank" rel="noopener noreferrer">${e(part)}</a>` : e(part);
  }).join('');
}
