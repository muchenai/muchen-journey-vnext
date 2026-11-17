// Match native input maxlength: raw UTF-16 length, including whitespace.
export const TASK_FIELD_LIMITS = Object.freeze({title: 60, summary: 400});

export function taskFieldLength(value) {
  return String(value ?? '').length;
}

export function validateTaskFieldLimits(task = {}) {
  const errors = [];
  if (taskFieldLength(task.title) > TASK_FIELD_LIMITS.title) errors.push(`任务标题不能超过 ${TASK_FIELD_LIMITS.title} 字`);
  if (taskFieldLength(task.summary) > TASK_FIELD_LIMITS.summary) errors.push(`任务简述不能超过 ${TASK_FIELD_LIMITS.summary} 字`);
  return errors;
}
