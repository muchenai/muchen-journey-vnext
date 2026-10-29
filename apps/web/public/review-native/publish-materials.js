import { escapeHtml as e, icon } from './core.js?v=20261028-publication-local';

// Keep file previews inside the confirmation so opening one never loses its selections.
export function renderPublishMaterials(materials = []) {
  const links = [...new Set(materials.filter(m => m.type === 'link').map(m => m.url))];
  const rows = materials.map(m => {
    const header = `<div class="material-info"><strong>${e(m.name)}</strong>`;
    if (m.type === 'link') {
      const safe = /^https:\/\//i.test(m.url || '');
      return `<div class="material-row">${header}<span>外部链接</span>${safe ? `<a href="${e(m.url)}" target="_blank" rel="noopener noreferrer">${e(m.url)} ↗</a>` : '<span>链接地址无效</span>'}</div></div>`;
    }
    if (m.type === 'file' || m.type === 'image') {
      const size = `${(Number(m.size || 0) / 1024).toLocaleString('zh-CN', {maximumFractionDigits: 3})} KB`;
      const kind = m.type === 'image' ? '图片' : '文档';
      const downloadable = /^data:[^;,]+;base64,/i.test(m.url || '');
      const preview = m.type === 'image' && /^data:image\/(png|jpeg|webp);base64,/i.test(m.url || '');
      return `<div class="material-row"><div class="file-icon">${icon(m.type === 'image' ? 'image' : 'file',20)}</div>${header}<span>${kind} · ${e(m.mime || '')} · ${e(size)}</span>${preview ? `<details><summary>查看图片</summary><img class="material-image" src="${e(m.url)}" alt="${e(m.name)}"></details>` : ''}${downloadable ? `<a href="${e(m.url)}" download="${e(m.name)}">下载文件</a>` : '<span>文件内容不可用</span>'}</div></div>`;
    }
    return `<div class="material-row">${header}<span>文本材料</span><details><summary>查看内容</summary><p>${e(m.url || '')}</p></details></div></div>`;
  }).join('');
  return `<section aria-label="发布材料清单"><h3>学习材料（${materials.length}）</h3><div class="material-list">${rows || '<p class="field-hint">暂无学习材料</p>'}</div>${links.length ? `<p class="field-hint">请逐项打开以上外部链接，确认可供学员访问。</p>${links.map((url,i) => `<label class="admin-check-link"><input type="checkbox" data-verified-link="${i}"><span>已确认：${e(materials.filter(m => m.type === 'link' && m.url === url).map(m => m.name || url).join('、'))}</span></label>`).join('')}` : ''}</section>`;
}
