import {escapeHtml as e} from './core.js?v=20261030-member-action-spacing';
import {validateMaterialFields} from './material-validation.js';

export function createMaterialEditor({store, openModal, closeModal, saveDraft, refresh, toast}) {
  return function openMaterialEditor(index = null, {collection = 'materials'} = {}) {
    const draft = store.data.draft;
    if (!['materials', 'taskFiles'].includes(collection)) return;
    draft[collection] ||= [];
    const taskFile = collection === 'taskFiles';
    const itemLabel = taskFile ? '任务文件' : '材料';
    const editing = Number.isInteger(index);
    const original = editing ? draft[collection][index] : null;
    if (editing && !original) return;
    const type = original?.type || 'link';
    const nameLimit = draft.camp === 'exploration' && type !== 'link' ? 240 : 160;
    openModal(`<div class="modal-heading"><h2>${editing ? '编辑' : '添加'}${taskFile ? '任务文件' : '学习材料'}</h2><p>${type === 'link' ? taskFile ? '添加可访问的任务文档链接，学员阅读题目后提交成果。' : '为学员提供可访问的文档或参考链接。' : '修改文件显示名称，已上传的文件内容保持不变。'}</p></div>
      <form id="material-form" novalidate>
        <label class="form-field"><span class="field-label">${itemLabel}名称</span><input name="name" required maxlength="${nameLimit}" value="${e(original?.name || '')}" placeholder="${taskFile ? '例如：培训练习题' : '例如：用户访谈记录'}" aria-describedby="material-name-error"><span id="material-name-error" class="material-field-error" role="alert" hidden></span></label>
        ${type === 'link' ? `<label class="form-field"><span class="field-label">链接地址</span><input name="url" type="url" required maxlength="2000" value="${e(original?.url || '')}" placeholder="https://" aria-describedby="material-url-error"><span id="material-url-error" class="material-field-error" role="alert" hidden></span></label>` : ''}
        <p id="material-save-error" class="material-field-error" role="alert" hidden></p>
        <div class="modal-actions"><button class="btn btn-secondary" type="button" data-cancel-material>取消</button><button class="btn btn-primary" type="submit">${editing ? '保存修改' : `添加${itemLabel}`}</button></div>
      </form>`, modal => {
      const form = modal.querySelector('#material-form');
      const saveError = modal.querySelector('#material-save-error');
      modal.querySelector('[data-cancel-material]').onclick = closeModal;
      function showError(key, message = '') {
        const input = form.elements.namedItem(key);
        const error = modal.querySelector(`#material-${key}-error`);
        if (!input || !error) return;
        input.setAttribute('aria-invalid', String(!!message));
        error.textContent = message;
        error.hidden = !message;
      }
      for (const key of ['name', 'url']) {
        form.elements.namedItem(key)?.addEventListener('input', () => { showError(key); saveError.hidden = true; });
      }
      form.onsubmit = event => {
        event.preventDefault();
        const {values, errors} = validateMaterialFields({
          name: form.elements.namedItem('name').value,
          url: form.elements.namedItem('url')?.value,
          type,
          nameLimit,
        });
        for (const key of ['name', 'url']) showError(key, taskFile ? errors[key]?.replaceAll('材料', '任务文件') : errors[key]);
        const firstInvalid = Object.keys(errors)[0];
        if (firstInvalid) { form.elements.namedItem(firstInvalid).focus(); return; }
        if (store.data.draft !== draft || (editing && draft[collection][index] !== original)) {
          saveError.textContent = '材料列表已更新，请关闭弹窗后重试';
          saveError.hidden = false;
          return;
        }
        if (!editing && draft.camp === 'exploration' && draft[collection].length >= 20) {
          saveError.textContent = `每个任务最多添加 20 份${itemLabel}`;
          saveError.hidden = false;
          return;
        }
        const previous = draft[collection];
        const next = original ? {...original, name: values.name} : {id: crypto.randomUUID(), type, name: values.name};
        if (type === 'link') next.url = values.url;
        draft[collection] = editing ? previous.map((item, i) => i === index ? next : item) : [...previous, next];
        if (!saveDraft()) {
          draft[collection] = previous;
          refresh();
          saveError.textContent = '材料尚未保存，请重试；若附件较多，请先减少附件';
          saveError.hidden = false;
          return;
        }
        closeModal();
        refresh();
        toast(`${itemLabel}${editing ? '已更新' : '已添加'}`);
      };
    });
  };
}
