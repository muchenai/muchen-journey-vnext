import { escapeHtml as e, icon } from './core.js?v=20261030-member-action-spacing';
import { localMaterialUrl, materialSizeLabel, materialVideoPreviewUrl } from './exploration-material-files.js';
import { EXPLORATION_COMPLETION_MODES, explorationCompletionMode, validAssessmentUrl, explorationTaskFiles, taskResourceLinks } from './exploration-completion.js';
import { showFieldError } from './field-feedback.js';

export function confirmPublicationFields(modal, reviewer) {
  if (reviewer && !reviewer.value) {
    showFieldError(reviewer, '请选择内容复核人。');
    return false;
  }
  const missing = modal.querySelector('[data-verified-link]:not(:checked)');
  if (missing) {
    showFieldError(missing, '请打开并确认这份材料可供学员访问。');
    return false;
  }
  return true;
}

// Keep file previews inside the confirmation so opening one never loses its selections.
export function renderPublishMaterials(materials = [], task) {
  const mode=task?.camp==='exploration'?EXPLORATION_COMPLETION_MODES.find(item=>item.id===explorationCompletionMode(task)):null;
  const completion=mode?`<section class="notice" aria-label="任务完成方式"><strong>完成方式 · ${e(mode.label)}</strong><p>${e(mode.description)}</p>${mode.id==='assessment'&&task.assessmentUrl&&validAssessmentUrl(task.assessmentUrl)?`<a href="${e(task.assessmentUrl)}" target="_blank" rel="noopener noreferrer">打开培训测试链接 ↗</a>`:''}</section>`:'';
  const taskFiles=explorationTaskFiles(task);
  const links = taskResourceLinks({...task,materials});
  const rows = files => files.map(m => {
    const header = `<div class="material-info"><strong>${e(m.name)}</strong>`;
    if (m.type === 'link') {
      const safe = /^https:\/\//i.test(m.url || '');
      return `<div class="material-row">${header}<span>外部链接</span>${safe ? `<a href="${e(m.url)}" target="_blank" rel="noopener noreferrer">${e(m.url)} ↗</a>` : '<span>链接地址无效</span>'}</div></div>`;
    }
    if (m.type === 'file' || m.type === 'image') {
      const size = materialSizeLabel(m.size);
      const kind = m.type === 'image' ? '图片' : String(m.mime||'').startsWith('video/')?'视频':'文档';
      const local = localMaterialUrl(m.url);
      const downloadUrl = local || m.url;
      const downloadable = Boolean(local) || /^data:[^;,]+;base64,/i.test(m.url || '');
      const preview = m.type === 'image' && /^data:image\/(png|jpeg|webp);base64,/i.test(m.url || '');
      return `<div class="material-row"><div class="file-icon">${icon(m.type === 'image' ? 'image' : 'file',20)}</div>${header}<span>${kind} · ${e(m.mime || '')} · ${e(size)}</span>${preview ? `<details><summary>查看图片</summary><img class="material-image" src="${e(m.url)}" alt="${e(m.name)}"></details>` : ''}${materialVideoPreviewUrl(m) ? `<details><summary>预览视频</summary><video controls preload="none" playsinline style="max-width:100%" src="${e(materialVideoPreviewUrl(m))}"></video></details>` : ''}${downloadable ? `<a href="${e(downloadUrl)}" download="${e(m.name)}">下载文件</a>` : '<span>文件内容不可用</span>'}</div></div>`;
    }
    return `<div class="material-row">${header}<span>文本材料</span><details><summary>查看内容</summary><p>${e(m.url || '')}</p></details></div></div>`;
  }).join('');
  return `${completion}<section aria-label="发布材料清单"><h3>学习材料（${materials.length}）</h3><div class="material-list">${rows(materials) || '<p class="field-hint">暂无学习材料</p>'}</div></section>${mode?.id==='assessment'?`<section aria-label="发布任务文件"><h3>任务文件（${taskFiles.length}）</h3><div class="material-list">${rows(taskFiles)||'<p class="field-hint">使用已有培训测试链接完成任务</p>'}</div></section>`:''}${links.length ? `<section aria-label="外部链接确认"><p class="field-hint">请逐项打开以上外部链接，确认可供学员访问。</p>${links.map((url,i) => `<label class="admin-check-link"><input type="checkbox" data-verified-link="${i}"><span>已确认：${e([...materials,...taskFiles].filter(m => m.type === 'link' && m.url === url).map(m => m.name || url).join('、')||'培训测试链接')} · ${e(url)}</span></label>`).join('')}</section>` : ''}`;
}
