// Translate the existing server contract without changing the supplied view's design.
import { learnerTaskTitle } from './task-titles.js';
const toBadge = { tech: 'dev', 'ai-eval': 'evaluation' };
const fromBadge = { dev: 'tech', evaluation: 'ai-eval' };
export const reasonNames = { materials_incomplete: '提交材料不完整', incorrect_answer: '答案错误', requirements_not_met: '未达到任务要求', insufficient_evidence: '依据或论证不足', other: '其他' };
export function reviewFeedbackError(decision, value) {
  const text = String(value || '');
  const count = Array.from(text.replace(/\s/gu, '')).length;
  if (decision === 'returned' && count < 5) return `退回时请填写至少 5 个字的具体修改建议（空格和换行不计入），当前 ${count} 个字。`;
  if (Array.from(text).length > 2000) return '审核评语不能超过 2000 个字。';
  return '';
}
export function taskView(task) {
  return { ...task, title: learnerTaskTitle(task.stableKey, task.title), badges: (task.badges || []).map(b => ({ ...b, id: toBadge[b.id] || b.id })), questions: task.questions || [], rubric: task.rubric || [], rubricAttachments: task.rubricAttachments || [], materials: task.materials || [], participants: task.participants ?? 0, completions: task.completions ?? 0 };
}
export function taskWrite(task) {
  return { ...task, passScore: task.passScore ?? 60, revision: task.revision || 0, badges: (task.badges || []).map(b => ({ ...b, id: fromBadge[b.id] || b.id })) };
}
export function reviewView(item, task) {
  return { id: item.id, taskId: item.task_id, taskStableKey: task?.stableKey, studentId: item.learner_id, studentName: item.learner_name,
    studentIsFeishu: item.learner_is_feishu === true, studentEmployeeNo: item.learner_employee_no || '', studentPhone: item.learner_phone || '',
    camp: item.camp, reviewMode: 'manual', status: item.decision === 'PASS' ? 'passed' : item.decision === 'REVISION_REQUIRED' ? 'returned' : 'pending',
    finalScore: item.score, reviewComment: item.feedback, failureReasons: (item.reasons || []).map(name => Object.keys(reasonNames).find(key => reasonNames[key] === name) || name),
    submittedAt: item.submitted_at, attempt: item.submission_version_no, revision: item.revision,
    actualReviewer: item.actual_reviewer ?? null, reviewedAt: item.reviewed_at ?? null,
    claim: item.claim ?? null, aiStatus: checkStatus[item.ai_status] || '暂无自查记录', aiCheckedAt: item.ai_checked_at ?? null,
    hasAi: (item.ai_statuses || []).some(s => s !== 'NOT_FOUND'), canReview: ['ASSIGNED','IN_REVIEW'].includes(item.status) && (item.allowed_commands || []).some(c => ['start', 'approve', 'request_revision'].includes(c)),
    taskSnapshot: { title: learnerTaskTitle(task?.stableKey, item.task_title), domain: item.domain, reviewMode: 'manual', camp: item.camp, badges: [], xp: 0, taskPoints: 0 },
  };
}
const checkStatus = { COMPLETED: '已完成', RUNNING: '自查中', SENDING: '正在写入评论', UNCERTAIN: '评论状态待确认', FAILED: '自查未完成', NOT_FOUND: '暂无自查记录' };
export function aiComment(checks) {
  return (checks || []).map(check => {
    const latest = [check.result ? `最近一次评价${check.generated_at ? `（${check.generated_at}）` : ''}\n${check.result}` : '暂无评价内容'];
    const seen = new Set([check.record_id || `${check.generated_at}:${check.result}`]);
    for (const record of check.history || []) {
      const key = record.record_id || `${record.generated_at}:${record.result}`;
      if (seen.has(key)) continue;
      seen.add(key);
      if (record.result) latest.push(`历史评价${record.generated_at ? `（${record.generated_at}）` : ''}\n${record.result}`);
    }
    return `${check.document_url}\n${checkStatus[check.status] || check.status}\n${latest.join('\n\n')}`;
  }).join('\n\n──────────\n\n');
}
export function detailView(base, detail, task, origin) {
  const evaluation = detail.evaluation || detail.coaching_feedback;
  return { ...base, revision: detail.revision, detail, answer: detail.submission_body,
    actualReviewer: detail.actual_reviewer ?? null, reviewedAt: detail.reviewed_at ?? null,
    claim: detail.claim ?? null,
    status: evaluation?.decision === 'PASS' ? 'passed' : evaluation?.decision === 'REVISION_REQUIRED' ? 'returned' : base.status,
    canReview: ['ASSIGNED','IN_REVIEW'].includes(detail.status) && (detail.allowed_commands || []).some(c => ['start', 'approve', 'request_revision'].includes(c)),
    reviewComment: evaluation?.overall_feedback || base.reviewComment || '',
    attachments: (detail.materials?.attachments || []).map(a => ({ name: a.original_filename, url: a.status === 'READY' && a.scan_status === 'CLEAN' ? `${origin}/review/${encodeURIComponent(detail.id)}/attachments/${encodeURIComponent(a.id)}` : '' })),
    taskSnapshot: { ...(task || base.taskSnapshot), title: learnerTaskTitle(task?.stableKey || base.taskStableKey, detail.task_title), summary: detail.task_purpose, camp: base.camp, reviewMode: 'manual',
      questions: (detail.completion_criteria || []).map(title => ({ title })),
      materials: (detail.task_learning_materials || []).map(m => ({ name: m.title, url: m.url || '', text: m.body || '', type: m.url ? 'link' : 'text' })),
      rubric: (detail.rubric?.dimensions || []).map(d => ({ name: d.title, description: d.evidence_expected, points: d.max_points })),
    },
    hasAi: !!detail.document_ai_checks?.length,
    ai: { advisory: true, score: null, dimensions: [], comment: aiComment(detail.document_ai_checks) },
  };
}
