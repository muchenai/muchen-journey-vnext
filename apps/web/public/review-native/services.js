/**
 * Replaceable JOURNEY service boundary. The prototype currently uses mode: 'mock'.
 * Switching to 'api' requires a real server implementing the REST routes below;
 * it never falls back to mock data after a failed API request.
 */
import { BADGES, DIFFICULTY_PRESETS, FAILURE_REASONS, gradeAnswer, getSubmissionStatus, getReviewCamp, normalizeCertificationRole, getCertificationLevel } from './core.js?v=20261029-reward-types';

const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));
const text = value => String(value ?? '').trim();
const numeric = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const encoded = value => encodeURIComponent(text(value));
const requestId = () => globalThis.crypto?.randomUUID?.() || `journey-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

function certificationView(record) {
  if (!record || typeof record !== 'object') return record;
  const level = getCertificationLevel(record.level ?? record.levelName);
  return {
    ...record,
    role: normalizeCertificationRole(record.role),
    ...(level ? { level: level.value, levelName: level.name, taskDifficulty: level.difficulty } : {}),
  };
}

// Difficulty rules belong to the server in API mode; these are read-only outputs.
function taskWritePayload(task, publishing = false) {
  const payload = { ...task, camp: getReviewCamp({}, task) };
  for (const field of ['xp', 'minutes', 'taskPoints', 'rulesVersion']) delete payload[field];
  if ((publishing || payload.status === 'published') && payload.reviewMode === 'manual') {
    payload.rubric = [];
    payload.rubricAttachments = [];
    payload.passScore = null;
  }
  return payload;
}

function queryString(filters = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters || {})) {
    if (value !== undefined && value !== null && value !== '') query.set(key, Array.isArray(value) ? value.join(',') : String(value));
  }
  return query.size ? `?${query}` : '';
}

function filterList(items, filters = {}, searchFields = []) {
  const query = text(filters.q || filters.search).toLocaleLowerCase();
  const fields = ['status', 'domain', 'author', 'taskId', 'studentId', 'reviewMode', 'role', 'method'];
  return items.filter(item => fields.every(field => !filters[field] || item[field] === filters[field]) && (!query || searchFields.some(field => text(item[field]).toLocaleLowerCase().includes(query))));
}

export function createJourneyService({ store, getCurrentUser, baseUrl = '', mode = 'mock' } = {}) {
  if (!['mock', 'api'].includes(mode)) throw new Error('不支持的服务模式');
  if (mode === 'mock' && (!store?.data || typeof store.save !== 'function')) throw new Error('演示服务需要有效的数据存储');
  const api = mode === 'api';
  const root = String(baseUrl || '').replace(/\/+$/, '');

  function requireCertificationAdmin() {
    // The real server must enforce this same authorization on certification routes.
    if (typeof getCurrentUser !== 'function' || getCurrentUser()?.accessRole !== 'super_admin') throw new Error('仅超级管理员可管理认证');
  }

  async function request(path, { method = 'GET', body, idempotencyKey } = {}) {
    const headers = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET' && method !== 'HEAD') headers['Idempotency-Key'] = idempotencyKey || requestId();
    let response;
    try {
      response = await fetch(`${root}/api${path}`, {
        method,
        credentials: 'same-origin',
        headers,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch {
      throw new Error('暂时无法连接服务，请稍后重试');
    }
    // Do not expose server bodies, credentials, submitted answers, or PII in errors.
    if (!response.ok) throw new Error(`服务请求失败（HTTP ${response.status}）`);
    if (response.status === 204) return null;
    try { return await response.json(); }
    catch { throw new Error('服务响应格式无效，请稍后重试'); }
  }

  async function resolveTask(taskOrId) {
    if (taskOrId && typeof taskOrId === 'object') return taskOrId;
    if (taskOrId !== undefined && taskOrId !== null) {
      const task = store?.getTask?.(taskOrId);
      if (!task && api) return request(`/tasks/${encoded(taskOrId)}`);
      if (!task) throw new Error('未找到对应任务');
      return task;
    }
    if (!store?.data?.draft) throw new Error('请提供要发布或评测的任务');
    return store.data.draft;
  }

  async function saveCertification(payload = {}) {
    requireCertificationAdmin();
    if (!payload || typeof payload !== 'object') throw new Error('认证数据无效');
    const name = text(payload.name);
    const role = normalizeCertificationRole(payload.role || 'NPC');
    const domain = text(payload.domain);
    const level = getCertificationLevel(payload.level ?? payload.levelName);
    if (!name || name.length > 30) throw new Error('成员姓名需为 1～30 个字符');
    if (!['NPC', '管理系统的管理员'].includes(role)) throw new Error('请选择 NPC 或管理系统的管理员身份');
    if (!domain || domain.length > 60) throw new Error('请填写有效的专业方向');
    if (!level) throw new Error('请选择初级、中级或高级认证等级');
    if (text(payload.note).length > 500) throw new Error('备注不能超过 500 个字符');
    const current = store?.data?.certifications || [];
    const existing = (payload.id ? current.find(item => item.id === payload.id) : null) || current.find(item => item.name === name && normalizeCertificationRole(item.role) === role);
    const normalized = {
      ...payload, name, role, domain,
      domains: Array.isArray(payload.domains) && payload.domains.length ? payload.domains.map(text).filter(Boolean) : [domain],
      level: level.value, levelName: level.name, taskDifficulty: level.difficulty, note: text(payload.note),
      method: 'admin', status: 'verified',
      ...(existing?.id ? { id: existing.id } : {}),
    };
    if (api) return certificationView(await request('/certifications/grant', { method: 'POST', body: normalized }));
    const now = new Date().toISOString();
    const certification = {
      ...(existing || {}),
      id: existing?.id || `CERT-${requestId()}`,
      name, role, domain, domains: normalized.domains,
      level: level.value, levelName: level.name, taskDifficulty: level.difficulty,
      note: normalized.note,
      method: 'admin',
      status: 'verified',
      updatedAt: now,
      certifiedAt: now,
    };
    const snapshot = clone(current);
    store.data.certifications = existing ? current.map(item => item.id === existing.id ? certification : item) : [certification, ...current];
    try { store.save(); }
    catch (error) { store.data.certifications = snapshot; throw error; }
    return clone(certification);
  }

  return {
    rules: {
      async difficultyPresets() {
        return api ? request('/rules/difficulty') : clone(DIFFICULTY_PRESETS);
      },
    },
    tasks: {
      async list(filters = {}) {
        if (api) return request(`/tasks${queryString(filters.camp ? { ...filters, camp: getReviewCamp({ camp: filters.camp }) } : filters)}`);
        const rows = filterList(store.data.tasks || [], filters, ['title', 'summary', 'author', 'domain']);
        return clone(rows.filter(task => !filters.camp || getReviewCamp({}, task) === getReviewCamp({ camp: filters.camp })));
      },
      async get(id) {
        if (api) return request(`/tasks/${encoded(id)}`);
        const task = store.getTask(id);
        if (!task) throw new Error('未找到对应任务');
        return clone(task);
      },
      async save(task) {
        if (!task || typeof task !== 'object') throw new Error('任务数据无效');
        if (api) return request(task.id ? `/tasks/${encoded(task.id)}` : '/tasks', { method: task.id ? 'PUT' : 'POST', body: taskWritePayload(task) });
        return clone(store.saveTask(task));
      },
      async publish(taskOrId) {
        const task = await resolveTask(taskOrId);
        if (api) return request(task.id ? `/tasks/${encoded(task.id)}/publish` : '/tasks/publish', { method: 'POST', body: taskWritePayload(task, true) });
        if (taskOrId === undefined || taskOrId === null) return clone(store.publishDraft());
        const snapshot = clone(store.data);
        store.data.draft = clone(task);
        try { return clone(store.publishDraft()); }
        catch (error) { store.data = snapshot; throw error; }
      },
    },
    evaluations: {
      async run(taskOrId, answer = '') {
        const task = await resolveTask(taskOrId);
        if (task.reviewMode !== 'ai') throw new Error('无固定答案的任务采用人工审核，不进行 AI 评测');
        return api ? request('/evaluations', { method: 'POST', body: { task, answer: String(answer ?? '') } }) : clone(gradeAnswer(task, answer));
      },
    },
    submissions: {
      async list(filters = {}) {
        if (api) return request(`/submissions${queryString(filters.camp ? { ...filters, camp: getReviewCamp({ camp: filters.camp }) } : filters)}`);
        const rows = filterList(store.data.submissions || [], { ...filters, status: undefined }, ['studentName', 'taskId']);
        return clone(rows.filter(submission => {
          const task = store.getTask(submission.taskId) || {};
          return (!filters.status || getSubmissionStatus(submission, task) === filters.status) && (!filters.camp || getReviewCamp(submission, task) === getReviewCamp({ camp: filters.camp }));
        }));
      },
      async review(id, review = {}) {
        const comment = text(review.comment);
        if (!['passed', 'returned'].includes(review.decision)) throw new Error('请选择通过或退回');
        const hasReturnReason = Array.isArray(review.reasonCodes) ? review.reasonCodes.some(code => text(code) !== '') : text(review.reasonCodes) !== '';
        if (review.decision === 'passed' && hasReturnReason) throw new Error('已选择退回原因，请取消勾选后再确认通过');
        if (review.decision === 'returned' && !comment) throw new Error('退回任务时请填写修改建议');
        const reasonCodes = Array.isArray(review.reasonCodes) ? [...new Set(review.reasonCodes)] : [];
        if (review.decision === 'returned' && (!reasonCodes.length || reasonCodes.some(code => !FAILURE_REASONS.some(reason => reason.id === code)))) throw new Error('请至少选择一个有效的不通过原因');
        const hasScore = review.score !== null && review.score !== undefined && text(review.score) !== '';
        const score = hasScore ? Number(review.score) : null;
        if (hasScore && (!Number.isFinite(score) || score < 0 || score > 100)) throw new Error('最终评分需在 0～100 分之间');
        const payload = { ...review, score, comment, reasonCodes: review.decision === 'returned' ? reasonCodes : [] };
        if (!api) return clone(store.reviewSubmission(id, payload));
        const submission = store?.data?.submissions?.find(item => item.id === id) || await request(`/submissions/${encoded(id)}`);
        if (!submission?.studentId || !submission?.taskId) throw new Error('未找到有效的学员提交记录');
        if (submission.reviewMode !== 'manual') throw new Error('AI 自测记录不能进行人工审核');
        // The server must enforce this same student/task claim key transactionally.
        const idempotencyKey = review.decision === 'passed' ? `${submission.studentId}:${submission.taskId}` : `review:${id}:returned`;
        return request(`/submissions/${encoded(id)}/review`, { method: 'POST', body: payload, idempotencyKey });
      },
      async resubmit(id, { answer = '', attachments = [] } = {}) {
        if (!Array.isArray(attachments)) throw new Error('提交附件格式无效');
        if (!text(answer) && !attachments.length) throw new Error('请填写修改后的答案或上传附件');
        const payload = { answer: String(answer ?? ''), attachments: clone(attachments) };
        if (!api) return clone(store.resubmitSubmission(id, payload));
        const previous = store?.data?.submissions?.find(item => item.id === id) || await request(`/submissions/${encoded(id)}`);
        if (!previous?.taskId) throw new Error('未找到有效的原提交记录');
        const task = previous.camp ? {} : await resolveTask(previous.taskId);
        payload.camp = getReviewCamp(previous, task);
        return request(`/submissions/${encoded(id)}/resubmit`, { method: 'POST', body: payload, idempotencyKey: `resubmit:${id}` });
      },
    },
    badges: {
      async list() {
        return api ? request('/badges') : clone(BADGES);
      },
      async progress(studentId) {
        if (api) return request(`/badges/progress${queryString({ studentId })}`);
        const learners = studentId ? (store.data.learners || []).filter(learner => learner.id === studentId) : store.data.learners || [];
        if (studentId && !learners.length) throw new Error('未找到对应学员');
        const rows = learners.map(learner => ({
          studentId: learner.id,
          studentName: learner.name,
          xp: numeric(learner.xp),
          taskPoints: numeric(learner.taskPoints),
          badges: BADGES.map(badge => {
            const points = Math.max(0, numeric(learner.badges?.[badge.id]?.points ?? learner.badges?.[badge.id]));
            const level = Math.min(3, Math.floor(points / 100));
            const nextThreshold = level === 3 ? null : (level + 1) * 100;
            return { id: badge.id, name: badge.name, points, level, nextThreshold, remaining: nextThreshold === null ? 0 : nextThreshold - points, progress: level === 3 ? 100 : points % 100 };
          }),
        }));
        return clone(studentId ? rows[0] : rows);
      },
    },
    certifications: {
      async list(filters = {}) {
        requireCertificationAdmin();
        const normalizedFilters = filters.role ? { ...filters, role: normalizeCertificationRole(filters.role) } : filters;
        const records = api ? await request(`/certifications${queryString(normalizedFilters)}`) : store.data.certifications || [];
        if (Array.isArray(records)) return clone(filterList(records.map(certificationView), normalizedFilters, ['name', 'domain', 'role']));
        if (Array.isArray(records?.items)) return { ...records, items: filterList(records.items.map(certificationView), normalizedFilters, ['name', 'domain', 'role']) };
        return records;
      },
      async grant(payload) { return saveCertification(payload); },
    },
  };
}
