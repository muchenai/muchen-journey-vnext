const feedback = new WeakMap();
const boundRoots = new WeakSet();
let nextId = 0;

export function clearFieldError(target) {
  const entry = feedback.get(target);
  if (!entry) return;
  const descriptions = (target.getAttribute('aria-describedby') || '').split(/\s+/)
    .filter(id => id && id !== entry.note.id);
  if (descriptions.length) target.setAttribute('aria-describedby', descriptions.join(' '));
  else target.removeAttribute('aria-describedby');
  if (entry.previousInvalid === null) target.removeAttribute('aria-invalid');
  else target.setAttribute('aria-invalid', entry.previousInvalid);
  if (entry.addedTabIndex) target.removeAttribute('tabindex');
  target.removeAttribute('data-field-feedback-invalid');
  entry.note.remove();
  feedback.delete(target);
}

export function clearFieldErrors(root) {
  root.querySelectorAll('[data-field-feedback-invalid]').forEach(clearFieldError);
}

export function bindFieldFeedback(root) {
  if (boundRoots.has(root)) return;
  boundRoots.add(root);
  const clearEdited = event => clearFieldError(event.target.closest?.('[data-field-feedback-invalid]'));
  root.addEventListener('input', clearEdited);
  root.addEventListener('change', clearEdited);
}

export function showFieldError(target, message, {container, focus = true} = {}) {
  if (!target || !message) return false;
  let entry = feedback.get(target);
  if (!entry) {
    const note = target.ownerDocument.createElement('span');
    note.className = 'field-feedback-message';
    note.id = 'field-feedback-' + (++nextId);
    note.setAttribute('role', 'alert');
    const wrapper = container || target.closest('.form-field, .ac-field, label');
    if (wrapper) wrapper.append(note);
    else target.after(note);
    entry = {note, previousInvalid:target.getAttribute('aria-invalid'), addedTabIndex:false};
    feedback.set(target, entry);
    const previousDescription = target.getAttribute('aria-describedby');
    target.setAttribute('aria-describedby', [previousDescription, note.id].filter(Boolean).join(' '));
    target.setAttribute('aria-invalid', 'true');
    target.setAttribute('data-field-feedback-invalid', '');
  }
  entry.note.textContent = message;
  if (focus) {
    for (let node = target.parentElement; node; node = node.parentElement) {
      if (node.tagName === 'DETAILS') node.open = true;
    }
    if (target.tabIndex < 0 && !target.hasAttribute('tabindex')) {
      target.tabIndex = -1;
      entry.addedTabIndex = true;
    }
    target.focus({preventScroll:true});
    target.scrollIntoView({block:'center', inline:'nearest', behavior:'instant'});
  }
  return true;
}
