import {rubricAttachmentErrors, normalizeImportedRubricMaterial} from './rubric-materials.js?v=20261118-document-rubric';
import {issueMessage} from './task-field-limits.js';

export const ANSWER_DOCUMENT_DIMENSION = Object.freeze({
  id: 'answer-document',
  name: '标准答案评分',
  points: 100,
  description: '按已导入标准答案文档逐题核对，遵循文档分值和扣分规则并换算为百分制。选择题文档未注明分值时各题等权；未注明扣分规则时，错选、漏选或多选该题记 0 分。主观题遵循文档评分要点，不自创标准；无法依据文档核对时不评分。',
});

function attachmentHasContent(file) {
  const data = /^data:([^;,]+)(?:;charset=utf-8)?;base64,([A-Za-z0-9+/]+={0,2})$/i.exec(file?.url || '');
  if (!data) return false;
  try {
    const content = atob(data[2]);
    if (!content || content.length !== file.size || data[1].toLowerCase() !== String(file.mime || '').toLowerCase()) return false;
    // Ordinary uploads round-trip through the API with empty source fields.
    // Any nonempty or whitespace-only source field still requires complete,
    // valid import metadata rather than silently becoming an ordinary upload.
    if (['sourceUrl', 'sourceRevision', 'sourceTitle'].some(key => file[key] != null && file[key] !== '')) normalizeImportedRubricMaterial(file);
    const extension = String(file.name).split('.').pop().toLowerCase();
    if (extension === 'txt' || extension === 'md') {
      if (!(extension === 'txt' ? ['text/plain'] : ['text/plain', 'text/markdown']).includes(file.mime)) return false;
      try {
        const body = new TextDecoder('utf-8', {fatal: true}).decode(Uint8Array.from(content, char => char.charCodeAt(0)));
        return Boolean(body.trim());
      } catch {
        // UTF-16 and GB18030 are also accepted by the server. Only it can
        // authoritatively decode those uploads and confirm readable text.
        return true;
      }
    }
    if (extension === 'pdf') return file.mime === 'application/pdf';
    if (extension === 'docx') return file.mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
    return false;
  } catch { return false; }
}

/** The server still parses real document bytes and confirms readable content. */
export function hasUsableRubricAttachments(files) {
  return Array.isArray(files) && files.length > 0 && rubricAttachmentErrors(files).length === 0 && files.every(attachmentHasContent);
}

export function usesAnswerDocumentRubric(task = {}) {
  return task.camp === 'exploration' && task.reviewMode === 'ai' &&
    Array.isArray(task.rubric) && task.rubric.length === 0 && hasUsableRubricAttachments(task.rubricAttachments);
}

/** Never write a generated dimension into the author's raw rubric array. */
export function effectiveRubric(task = {}) {
  return usesAnswerDocumentRubric(task) ? [ANSWER_DOCUMENT_DIMENSION] : Array.isArray(task.rubric) ? task.rubric : [];
}

export function rubricScoreTotal(task = {}) {
  return effectiveRubric(task).reduce((sum, dimension) => sum + (Number(dimension?.points) || 0), 0);
}

/** Shared by publication, readiness and the optional author sandbox. */
export function rubricDimensionErrors(task = {}, issue = issueMessage) {
  const errors = [];
  const rubric = effectiveRubric(task);
  const text = value => String(value ?? '').trim();
  if (!rubric.length) errors.push(issue('rubric', task.camp === 'exploration' ? '请添加有效的标准答案文档，或至少配置一个评分维度' : '请至少配置一个评分维度'));
  if (rubric.length > 12) errors.push(issue('rubric', '最多配置 12 个评分维度'));
  const ids = rubric.map((dimension, index) => dimension?.id || `dimension-${index + 1}`);
  if (new Set(ids).size !== ids.length) errors.push(issue('rubric', '评分维度不能重复'));
  rubric.forEach((dimension, index) => {
    if (!text(dimension?.name)) errors.push(issue('rubric.name', `请填写评分维度 ${index + 1} 的名称`, index));
    if (text(dimension?.name).length > 120) errors.push(issue('rubric.name', `评分维度 ${index + 1} 的名称不能超过 120 字`, index));
    if (!Number.isFinite(Number(dimension?.points)) || Number(dimension?.points) <= 0 || Number(dimension?.points) > 100) errors.push(issue('rubric.points', `评分维度 ${index + 1} 的分值需大于 0 且不超过 100`, index));
    else if (Math.abs(Number(dimension.points) * 100 - Math.round(Number(dimension.points) * 100)) > 0.0000001) errors.push(issue('rubric.points', `评分维度 ${index + 1} 的分值最多保留两位小数`, index));
    if (!text(dimension?.description)) errors.push(issue('rubric.description', `请填写评分维度 ${index + 1} 的评分描述`, index));
    if (text(dimension?.description).length > 2000) errors.push(issue('rubric.description', `评分维度 ${index + 1} 的评分描述不能超过 2,000 字`, index));
  });
  errors.push(...rubricAttachmentErrors(task.rubricAttachments || []).map(message => issue('rubricAttachments', message)));
  if (Math.abs(rubric.reduce((sum, dimension) => sum + (Number(dimension?.points) || 0), 0) - 100) > 0.000001) errors.push(issue('rubric.total', '评分维度总分需为 100 分'));
  return errors;
}
