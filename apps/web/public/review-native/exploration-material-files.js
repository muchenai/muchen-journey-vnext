import {isUploadVideo, uploadTaskVideo} from './course-asset-upload.js';
export const EXPLORATION_MATERIAL_MAX_BYTES = 100 * 1024 * 1024;
const rasterMimeByExtension = { png:'image/png', jpg:'image/jpeg', jpeg:'image/jpeg', gif:'image/gif', webp:'image/webp', avif:'image/avif', bmp:'image/bmp' };
const rasterMimes = new Set(Object.values(rasterMimeByExtension));
const videoMimeByExtension = {mp4:'video/mp4',webm:'video/webm',ogv:'video/ogg',ogg:'video/ogg',m4v:'video/mp4',mov:'video/quicktime'};

export function learningMaterialFileMime(file) {
  const extension=String(file.name||'').split('.').pop().toLowerCase();
  let mime=String(file.type||'').toLowerCase();
  if(extension==='svg'||mime==='image/svg+xml')return 'application/octet-stream';
  if(mime==='image/jpg')mime='image/jpeg';
  if(!mime)mime=rasterMimeByExtension[extension]||videoMimeByExtension[extension]||'application/octet-stream';
  return mime.startsWith('image/')&&!rasterMimes.has(mime)?'application/octet-stream':mime;
}

export function materialImagePreviewUrl(material) {
  if(!material||material.type==='link'||/\.svg$/i.test(material.name||''))return '';
  const local=localMaterialUrl(material.url);
  if(local&&rasterMimes.has(String(material.mime||'').toLowerCase()))return `${local}?inline=1`;
  const inline=typeof material.url==='string'&&material.url.match(/^data:([^;,]+);base64,/i);
  return inline&&rasterMimes.has(inline[1].toLowerCase())?material.url:'';
}

export function materialVideoPreviewUrl(material) {
  const local = localMaterialUrl(material?.url);
  return local && Object.values(videoMimeByExtension).includes(material?.mime) ? `${local}?inline=1` : '';
}

export function localMaterialUrl(value) {
  const match = typeof value === 'string' && value.match(/^exploration-material:([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})$/i);
  return match ? `/api/review-native/exploration/materials/${encodeURIComponent(match[1])}` : '';
}

export function materialSizeLabel(size) {
  const bytes = Number(size || 0);
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} GB`;
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} MB`
    : `${(bytes / 1024).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} KB`;
}

// Send the File itself so large learning materials never become base64 JSON or
// occupy the browser's draft cache. Task records store only the authenticated file reference.
export async function uploadExplorationMaterial(file, {label='学习材料'} = {}) {
  if (!file || !Number.isSafeInteger(file.size) || file.size < 1) throw new Error(`请选择非空的${label}文件。`);
  if (isUploadVideo(file)) return uploadTaskVideo(file, 'exploration');
  if (file.size > EXPLORATION_MATERIAL_MAX_BYTES) throw new Error(`${file.name} 超过 100 MB，请选择不超过 100 MB 的文件。`);
  const response = await fetch(`/api/review-native/exploration/materials?name=${encodeURIComponent(file.name)}&type=${learningMaterialFileMime(file).startsWith('image/')?'image':'file'}`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { Accept: 'application/json', 'Content-Type': learningMaterialFileMime(file) }, body: file,
  });
  let result;
  try { result = await response.json(); } catch { throw new Error(`${label}上传未完成，请重试。`); }
  if (!response.ok || !result.ok) throw new Error(result.error || `${label}上传未完成，请重试。`);
  const material = result.data;
  if (!material || !localMaterialUrl(material.url) || !['file', 'image'].includes(material.type)
    || material.size !== file.size || material.size > EXPLORATION_MATERIAL_MAX_BYTES) {
    throw new Error(`${label}上传结果无效，请重试。`);
  }
  return material;
}
