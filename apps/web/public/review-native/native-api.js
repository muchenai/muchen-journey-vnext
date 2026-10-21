import { taskView, taskWrite, reviewView, detailView, reasonNames, reviewFeedbackError } from './native-model.js';
import { applyDifficultyPreset } from './core.js?v=20261021-review-decision';
let activeStore;
export async function request(body, reviewId) {
  const response = await fetch('/api/review-native' + (reviewId ? `?review=${encodeURIComponent(reviewId)}` : ''), {
    method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : { Accept: 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  let result;
  try { result = await response.json(); } catch { throw new Error('登录或连接已失效，请刷新页面重新登录。'); }
  if (response.status === 401 || result.status === 401) {
    location.assign('/review/login?auth_error=SESSION_EXPIRED');
    throw new Error('登录已失效，请重新使用飞书登录。');
  }
  if (!response.ok || !result.ok) throw new Error(result.error || '操作未完成，请稍后重试。');
  return result.data;
}
export const getCurrentInviteUser = () => activeStore ? { id: activeStore.actor.id, name: activeStore.actor.name, accessRole: activeStore.operatorId ? 'super_admin' : 'reviewer' } : null;
export const isInviteLoggedIn = () => !!getCurrentInviteUser();
export const onInviteSessionChange = () => {};
export const renderInviteLogin = () => '';
export const bindInviteLogin = () => {};
export async function clearInviteSession() { await request({ command: 'logout' }); location.assign('/review/login'); }
export function newDraft() {
  return applyDifficultyPreset({ id: crypto.randomUUID(), revision: 0, title: '', summary: '', camp: 'novice', domain: '产品开发', difficulty: '入门', badges: [{ id: 'product', weight: 100 }], materials: [], questions: [], rubric: [], rubricAttachments: [], reviewMode: 'manual', passScore: 60, status: 'draft', author: activeStore?.actor.name || '', participants: 0, completions: 0 });
}
export class ApiStore {
  static async create() {
    const store = new ApiStore();
    store.data = { tasks: [], submissions: [], learners: [], claims: {}, certifications: [] };
    await store.refresh(); activeStore = store;
    store.storageKey = `journey-review-native-draft:${store.actor.id}:${store.operatorId || 'reviewer'}`;
    let draft;
    try { draft = JSON.parse(localStorage.getItem(store.storageKey)); } catch { /* No actor draft. */ }
    store.data.draft = draft && typeof draft.id === 'string' && Array.isArray(draft.badges) && Array.isArray(draft.materials) ? draft : newDraft();
    return store;
  }
  async refresh() {
    const snapshot = await request();
    if (this.actor && this.actor.id !== snapshot.actor.id) { location.reload(); throw new Error('登录身份已变更，请刷新。'); }
    this.actor = snapshot.actor; this.operatorId = snapshot.operatorId; this.members = snapshot.members;
    this.data.tasks = snapshot.tasks.map(taskView);
    const tasksById = new Map(this.data.tasks.map(task => [task.id, task]));
    this.data.submissions = snapshot.reviews.map(item => reviewView(item, tasksById.get(item.task_id)));
    this.data.certifications = snapshot.members.filter(m => m.certification).map(m => ({ id: m.id, name: m.name,
      role: m.roles.includes('OPERATOR') ? '管理系统的管理员' : 'NPC', domain: m.certification.domain,
      level: ({ 初级: 1, 中级: 2, 高级: 3 })[m.certification.level] || 1, levelName: m.certification.level, method: 'admin', status: 'verified' }));
  }
  getTask(id) { return this.data.tasks.find(t => t.id === id); }
  save() { localStorage.setItem(this.storageKey, JSON.stringify(this.data.draft)); }
  async saveTask(task) {
    if (!this.operatorId) throw new Error('当前账号没有任务配置权限。');
    const saved = taskView(await request({ command: 'saveTask', task: taskWrite(task) }));
    this.data.draft = structuredClone(saved);
    this.data.tasks = [saved, ...this.data.tasks.filter(t => t.id !== saved.id)];
    try { this.save(); } catch { /* Server save succeeded; local draft storage is optional. */ }
    try { await this.refresh(); } catch { /* Keep the acknowledged saved task; poll retries. */ }
    return saved;
  }
  async archiveTask(task) { await request({ command: 'archiveTask', task: taskWrite(task) }); await this.refresh(); }
  async loadSubmission(id) {
    const base = this.data.submissions.find(s => s.id === id);
    if (!base) throw new Error('未找到该提交，请刷新列表。');
    if (base.historical) {
      if (base.realReviewId) {
        const historyDetail = await request(null, base.realReviewId);
        Object.assign(base, detailView(base, historyDetail, this.getTask(base.taskId), location.origin), { canReview: false });
      }
      return base;
    }
    const detail = await request(null, id);
    const value = detailView(base, detail, this.getTask(base.taskId), location.origin);
    this.data.submissions = this.data.submissions.filter(s => !s.historical || s.currentReviewId !== id);
    const older = (detail.submission_history || []).filter(h => h.id !== detail.submission_version_id).sort((a, b) => a.version_no - b.version_no);
    let previous;
    for (const h of older) {
      const historyId = `history:${id}:${h.id}`;
      this.data.submissions.push({ ...value, id: historyId, currentReviewId: id, historical: true, canReview: false,
        realReviewId: h.review_id, status: h.decision === 'PASS' ? 'passed' : h.decision === 'REVISION_REQUIRED' ? 'returned' : 'historical',
        reviewComment: h.feedback || '历史提交，仅供查看。', finalScore: null, answer: h.body, hasAi: false, ai: null,
        attachments: (h.attachments || []).map(a => ({ name: a.original_filename, url: h.review_id && a.status === 'READY' && a.scan_status === 'CLEAN' ? `${location.origin}/review/${h.review_id}/attachments/${a.id}` : '' })),
        attempt: h.version_no, submittedAt: h.created_at, supersededBy: id, previousSubmissionId: previous });
      previous = historyId;
    }
    value.previousSubmissionId = previous;
    Object.assign(base, value); return base;
  }
}
export function createJourneyService({ store }) {
  const decisionKeys = new Map();
  return {
    tasks: { publish: async (task, reviewerId, verified, key) => {
      if (!store.members.some(m => m.id === reviewerId && m.roles.includes('REVIEWER'))) throw new Error('请选择内容复核人。');
      const links = [...new Set(task.materials.filter(m => m.type === 'link').map(m => m.url))];
      if (links.some(url => !verified.includes(url))) throw new Error('请确认全部学习材料链接可供学员访问。');
      const saved = taskView(await request({ command: 'publishTask', task: taskWrite(task), payload: { reviewerId, verified: links }, key }));
      store.data.draft = structuredClone(saved);
      store.data.tasks = [saved, ...store.data.tasks.filter(t => t.id !== saved.id)];
      try { store.save(); } catch { /* Published record is durable on server. */ }
      try { await store.refresh(); } catch { /* Background refresh retries. */ }
      return saved;
    } },
    submissions: { review: async (id, input) => {
      const submission = store.data.submissions.find(s => s.id === id);
      if (!submission?.canReview || submission.historical) throw new Error('这份记录当前不可审核，请刷新。');
      const hasReturnReason = Array.isArray(input.reasonCodes) ? input.reasonCodes.some(code => String(code ?? '').trim()) : String(input.reasonCodes ?? '').trim();
      if (input.decision === 'passed' && hasReturnReason) throw new Error('已选择退回原因，请取消勾选后再确认通过。');
      const feedbackError = reviewFeedbackError(input.decision, input.comment);
      if (feedbackError) throw new Error(feedbackError);
      if (submission.detail?.rubric?.dimensions?.some(d => d.max_points)) throw new Error('这份历史任务要求逐项评分，资源包目前没有对应输入项，暂不能在此完成审核。');
      const payload = { expected_revision: submission.revision, decision: input.decision === 'passed' ? 'APPROVE' : 'REQUEST_REVISION', feedback: input.comment,
        score: input.score, reasons: (input.reasonCodes || []).map(key => reasonNames[key]).filter(Boolean) };
      const signature = JSON.stringify({ id, payload });
      if (!decisionKeys.has(signature)) decisionKeys.set(signature, crypto.randomUUID());
      const result = await request({ command: 'decide', id, payload, key: decisionKeys.get(signature) });
      // A read failure after a committed decision must not invite duplicate writes.
      submission.status = input.decision === 'passed' ? 'passed' : 'returned'; submission.canReview = false;
      submission.reviewComment = input.comment; submission.finalScore = input.score;
      submission.failureReasons = input.reasonCodes || [];
      try { await store.refresh(); } catch { /* Polling will retry the read. */ }
      return result;
    } },
    certifications: { grant: async input => {
      const matches = store.members.filter(m => input.id ? m.id === input.id : m.name === input.name);
      if (matches.length !== 1) throw new Error('请填写已有成员的准确姓名；此处不能创建新账号。');
      const member = matches[0];
      if (!member.roles.includes(input.role === 'NPC' ? 'REVIEWER' : 'OPERATOR')) throw new Error('所选身份与该成员现有权限不一致，认证不能更改账号权限。');
      const result = await request({ command: 'certify', payload: { member, domain: input.domain, level: ({ 1: '初级', 2: '中级', 3: '高级' })[input.level] } });
      await store.refresh(); return result;
    } },
    evaluations: { run: async (task, answer) => {
      const result = await request({ command: 'sandbox', task: taskWrite(task), payload: { answer } });
      return { advisory: true, score: null, dimensions: [], comment: result.result, source: result.model };
    } },
  };
}
export function createAcademyStore() {
  const unavailable = () => { throw new Error('AI学院尚未接入本地后端，当前不能保存或发布课程。'); };
  return { isAdmin: () => !!activeStore?.operatorId, user: getCurrentInviteUser,
    listManagedCourses: () => [], getManagedCourse: () => null, listShares: () => [],
    getAdminStats: () => ({ total: 0, published: 0, unpublished: 0, pending: 0 }),
    addCourse: unavailable, updateCourse: unavailable, setCourseVisibility: unavailable, reviewShare: unavailable, getVideoUrl: unavailable };
}
