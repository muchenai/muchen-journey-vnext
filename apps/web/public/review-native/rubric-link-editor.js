import {escapeHtml as e, icon} from './core.js?v=20261118-answer-link';
import {RUBRIC_MAX_FILES, normalizeRubricLink, rubricSourceUrl, rubricLinkConflict, normalizeImportedRubricMaterial} from './rubric-materials.js?v=20261118-answer-link';

export function renderRubricAttachments(files = [], {editable = false} = {}) {
  return files.map((file, index) => {
    const sourceUrl = rubricSourceUrl(file.sourceUrl);
    return `<div class="${editable ? 'attachment-line' : 'detail-material'} rubric-attachment"><span class="rubric-attachment-name">${icon('file', 16)} ${e(file.name)}${sourceUrl ? `<small class="muted">已读取 · 来源：${e(file.sourceTitle || '飞书文档')} · 版本 ${e(file.sourceRevision || '—')}</small>` : ''}</span>${sourceUrl ? `<a class="text-btn" href="${e(sourceUrl)}" target="_blank" rel="noopener noreferrer">打开源文档 ↗</a>${editable ? `<button type="button" class="text-btn" data-edit-rubric-link="${index}">编辑链接</button><button type="button" class="text-btn" data-reread-rubric-link="${index}">重新读取</button>` : ''}` : ''}${!editable && /^data:[^,]*;base64,/i.test(file.url || '') ? `<button type="button" class="text-btn" data-rubric-download="${index}">${sourceUrl ? '下载已导入标准 TXT' : '下载评分文档'}</button>` : ''}${editable ? `<button type="button" class="text-btn" data-remove-rubric-file="${index}">移除</button>` : ''}</div>`;
  }).join('');
}

/** Only a successful, still-current import may change the current task's attachments. */
export function createRubricLinkEditor({store, request, openModal, closeModal, saveDraft, refresh, toast}) {
  let currentSession;
  return function openRubricLinkEditor(index = null, {reread = false} = {}) {
    const draft = store.data.draft;
    const files = draft.rubricAttachments || [];
    const editing = Number.isInteger(index);
    const original = editing ? files[index] : null;
    if (editing && !rubricSourceUrl(original?.sourceUrl)) return;
    if (!editing && files.length >= RUBRIC_MAX_FILES) {
      toast('最多附加 4 份评分文档，请先移除一份后再添加答案链接。', 'error');
      return;
    }
    if (currentSession) currentSession.active = false;
    const session = {active: true, pending: false};
    currentSession = session;
    const context = {camp: draft.camp, difficulty: draft.difficulty};
    openModal(`<div class="modal-heading"><h2>${reread ? '重新读取标准答案' : editing ? '编辑答案链接' : '添加答案链接'}</h2><p>读取飞书文档正文，保存为本任务的标准答案。AI 评分使用已导入的版本；源文档更新后，请手动重新读取。</p></div>
      <form id="rubric-link-form" novalidate>
        <label class="form-field"><span class="field-label">标准答案飞书链接</span><input name="url" type="url" maxlength="2000" value="${e(original?.sourceUrl || '')}" placeholder="https://…feishu.cn/docx/…" aria-describedby="rubric-link-error" ${reread ? 'readonly' : ''}><span class="field-hint">支持 Docx 或 Wiki 文档。请确保文档已授权给飞书应用读取。导入不会运行 AI，也不会发送评论。</span></label>
        ${original ? `<p class="field-hint">当前已导入：${e(original.sourceTitle || original.name)}。读取失败时，保留原来的标准答案。</p>` : ''}
        <p id="rubric-link-error" class="material-field-error" role="alert" hidden></p>
        <p id="rubric-link-status" class="field-hint" role="status" aria-live="polite"></p>
        <div class="modal-actions"><button type="button" class="btn btn-secondary" data-cancel-rubric-link>取消</button><button type="submit" class="btn btn-primary">${reread ? '确认重新读取' : editing ? '读取并保存修改' : '读取并添加'}</button></div>
      </form>`, modal => {
      const form = modal.querySelector('#rubric-link-form');
      const input = form.elements.namedItem('url');
      const errorNode = modal.querySelector('#rubric-link-error');
      const status = modal.querySelector('#rubric-link-status');
      const submit = form.querySelector('button[type="submit"]');
      const submitLabel = submit.textContent;
      const cancel = () => { session.active = false; closeModal(); };
      modal.querySelector('[data-cancel-rubric-link]').onclick = cancel;
      modal.addEventListener('review-close', () => { session.active = false; }, {once: true});
      const active = () => session.active && currentSession === session && store.data.draft === draft &&
        draft.camp === context.camp && draft.difficulty === context.difficulty;
      const showError = message => {
        errorNode.textContent = message;
        errorNode.hidden = !message;
        input.setAttribute('aria-invalid', String(Boolean(message)));
      };
      input.addEventListener('input', () => showError(''));
      form.onsubmit = async event => {
        event.preventDefault();
        if (session.pending || !session.active) return;
        showError('');
        let url;
        try {
          url = normalizeRubricLink(input.value);
          if (!active()) throw new Error('当前草稿已切换，请关闭弹窗后重试。');
          const currentFiles = draft.rubricAttachments || [];
          if (editing && currentFiles[index] !== original) throw new Error('评分文档列表已更新，请关闭弹窗后重试。');
          if (!editing && currentFiles.length >= RUBRIC_MAX_FILES) throw new Error('最多附加 4 份评分文档。');
          if (rubricLinkConflict(currentFiles, url, editing ? index : null)) throw new Error('这份标准答案已添加，请编辑或重新读取已有文档。');
        } catch (error) { showError(error.message); input.focus(); return; }
        session.pending = true;
        submit.disabled = true;
        input.disabled = true;
        submit.textContent = '正在读取…';
        status.textContent = '正在读取飞书文档正文，请稍候；取消后不会添加到草稿。';
        try {
          const result = await request({command: 'importRubricDocument', payload: {url, ...context}});
          if (!active()) return;
          const material = normalizeImportedRubricMaterial(result?.material);
          const previous = draft.rubricAttachments || [];
          if (editing && previous[index] !== original) throw new Error('评分文档列表已更新，请关闭弹窗后重试。');
          if (!editing && previous.length >= RUBRIC_MAX_FILES) throw new Error('最多附加 4 份评分文档。');
          if (rubricLinkConflict(previous, material.sourceUrl, editing ? index : null)) throw new Error('这份标准答案已添加，请编辑或重新读取已有文档。');
          draft.rubricAttachments = editing ? previous.map((item, i) => i === index ? material : item) : [...previous, material];
          let saved = false;
          try { saved = saveDraft() !== false; } catch { /* Restore the frozen original on failed storage. */ }
          if (!saved) {
            draft.rubricAttachments = previous;
            refresh();
            throw new Error('标准答案尚未保存，请重试；原评分文档保持不变。');
          }
          session.active = false;
          closeModal();
          refresh();
          toast(editing ? '标准答案已重新读取并保存' : '标准答案已读取并添加');
        } catch (error) {
          if (active()) showError(error.message || '标准答案读取失败，请重试。');
        } finally {
          session.pending = false;
          if (active()) {
            submit.disabled = false;
            input.disabled = false;
            submit.textContent = submitLabel;
            status.textContent = '';
          }
        }
      };
    });
  };
}
