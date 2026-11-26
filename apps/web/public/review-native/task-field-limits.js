// Match native input maxlength: raw UTF-16 length, including whitespace.
export const TASK_FIELD_LIMITS = Object.freeze({title: 60, summary: 400});

export function taskFieldLength(value) {
  return String(value ?? '').length;
}

export const taskIssue = (field, message, index) => ({field, message, index});
export const issueMessage = (field, message) => message;

export function validateTaskFieldLimits(task = {}, issue = issueMessage) {
  const errors = [];
  if (taskFieldLength(task.title) > TASK_FIELD_LIMITS.title) errors.push(issue('title', `任务标题不能超过 ${TASK_FIELD_LIMITS.title} 字`));
  if (taskFieldLength(task.summary) > TASK_FIELD_LIMITS.summary) errors.push(issue('summary', `任务简述不能超过 ${TASK_FIELD_LIMITS.summary} 字`));
  return errors;
}
