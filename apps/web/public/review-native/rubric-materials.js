export const RUBRIC_MAX_FILES = 4;
export const RUBRIC_MAX_BYTES = 2 * 1024 * 1024;
const types = {
  txt: 'text/plain', md: 'text/markdown', pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
};

/** Only open document links from the same trusted hosts as learner evidence. */
export function rubricSourceUrl(value) {
  try {
    const raw = String(value ?? '').trim();
    if (!raw || raw.length > 2000) return '';
    const url = new URL(raw);
    if (url.protocol !== 'https:' || url.username || url.password || url.port) return '';
    if (!['.feishu.cn', '.larksuite.com'].some(host => url.hostname.endsWith(host))) return '';
    if (!/^\/(?:docx|wiki)\/[A-Za-z0-9]{10,100}\/?$/.test(url.pathname)) return '';
    url.pathname = url.pathname.replace(/\/$/, '');
    url.search = '';
    url.hash = '';
    return url.href;
  } catch { return ''; }
}

export function normalizeRubricLink(value) {
  const raw = String(value ?? '');
  if (!raw) throw new Error('请填写标准答案的飞书文档链接。');
  if (!raw.trim()) throw new Error('答案链接不能只包含空格。');
  const url = rubricSourceUrl(raw);
  if (!url) throw new Error('请填写有效的 HTTPS 飞书文档链接，仅支持 Docx 文档或 Wiki 知识库文档。');
  return url;
}

export function rubricLinkConflict(files, sourceUrl, excludedIndex = null) {
  return files.some((file, index) => index !== excludedIndex && rubricSourceUrl(file?.sourceUrl) === sourceUrl);
}

/** Import responses must contain a frozen, readable TXT, never a live URL as its bytes. */
export function normalizeImportedRubricMaterial(material) {
  const sourceUrl = rubricSourceUrl(material?.sourceUrl);
  const data = /^data:text\/plain;base64,([A-Za-z0-9+/]+={0,2})$/.exec(material?.url || '');
  let bytes = 0;
  try { if (data) bytes = atob(data[1]).length; } catch { /* Reject malformed base64 below. */ }
  if (!sourceUrl || !new URL(sourceUrl).pathname.startsWith('/docx/') ||
      !String(material?.id || '').trim() || material?.type !== 'file' || material?.mime !== 'text/plain' ||
      !String(material?.name || '').trim().toLowerCase().endsWith('.txt') ||
      !String(material?.sourceTitle || '').trim() || !/^\d+$/.test(String(material?.sourceRevision ?? '')) ||
      !data || !bytes || bytes !== material?.size || bytes > RUBRIC_MAX_BYTES) {
    throw new Error('未能读取完整的标准答案正文，请重新读取或更换文档。');
  }
  return {...material, sourceUrl};
}

/** Validate at selection time; the server still parses the actual file bytes. */
export function normalizeRubricFile(file, count = 0) {
  if (count >= RUBRIC_MAX_FILES) throw new Error('最多附加 4 份评分文档。');
  const extension = String(file?.name || '').split('.').pop().toLowerCase();
  if (extension === 'doc') throw new Error('旧版 DOC 暂不支持读取，请转换为 DOCX、PDF 或 TXT 后上传。');
  if (!types[extension]) throw new Error('评分文档仅支持 TXT、MD、DOCX 和含文字的 PDF。');
  if (!Number.isFinite(file.size) || file.size <= 0) throw new Error('评分文档不能为空，请检查文件后重试。');
  if (file.size > RUBRIC_MAX_BYTES) throw new Error(`${file.name} 超过 2 MB，请精简后上传。`);
  return file.type === types[extension] ? file : new File([file], file.name, {type: types[extension], lastModified: file.lastModified});
}

export function rubricAttachmentErrors(files) {
  if (!Array.isArray(files) || files.length > RUBRIC_MAX_FILES) return ['最多附加 4 份评分文档。'];
  const errors = [];
  for (const file of files) {
    const extension = String(file?.name || '').split('.').pop().toLowerCase();
    if (extension === 'doc') errors.push('旧版 DOC 暂不支持读取，请转换为 DOCX、PDF 或 TXT 后上传。');
    else if (!types[extension] || file?.type !== 'file') errors.push('评分文档仅支持 TXT、MD、DOCX 和含文字的 PDF。');
    if (!Number.isFinite(file?.size) || file.size <= 0 || file.size > RUBRIC_MAX_BYTES) errors.push('评分文档不能为空，且单文件不能超过 2 MB。');
  }
  return errors;
}
