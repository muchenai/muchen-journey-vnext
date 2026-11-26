import { clearFieldErrors, showFieldError } from './field-feedback.js';

const fieldSelectors = {
  badges: '.badge-selector',
  weights: '.ratio-section',
  materials: '#material-dropzone',
  taskFiles: '#task-file-dropzone',
  completionMode: '[data-field="completionMode"], [data-requires-task]:checked',
  difficulty: '#task-basics',
  reviewMode: '[name="review-mode"]',
  rubric: '#add-rubric',
  'rubric.total': '[data-rubric][data-key="points"], #add-rubric',
  rubricAttachments: 'label:has(#rubric-upload)',
};

function fieldTarget(editor, {field, index}) {
  if (Number.isInteger(index)) {
    if (field === 'weights') return editor.querySelector(`[data-badge-weight="${index}"]`);
    if (field === 'taskFiles' || field === 'materials')
      return editor.querySelector(`[data-material-collection="${field}"][data-edit-material="${index}"]`);
    if (field.startsWith('rubric.'))
      return editor.querySelector(`[data-rubric="${index}"][data-key="${field.slice(7)}"]`);
  }
  return editor.querySelector(fieldSelectors[field] || `[data-field="${field}"]`);
}

export function showTaskIssues(editor, issues, action) {
  clearFieldErrors(editor);
  const fields = new Map();
  for (const issue of issues) {
    const target = fieldTarget(editor, issue) || action;
    if (target && !fields.has(target)) fields.set(target, issue.message);
  }
  const ordered = [...fields.keys()].sort((a,b) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
  ordered.forEach((field,index) => showFieldError(field, fields.get(field), {focus:index === 0}));
}
