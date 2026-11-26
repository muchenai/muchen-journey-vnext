export const MAX_VIDEO_BYTES = 2 * 1024 ** 3;
const videos = /\.(mp4|m4v|mov|webm|ogv|ogg)$/i;
export function isUploadVideo(file) {
  return videos.test(file?.name || '');
}
export function fileUploadLimit(file, documentLimit) {
  return isUploadVideo(file) ? MAX_VIDEO_BYTES : documentLimit;
}

async function send(path, method, body, type) {
  const response = await fetch('/api/review-native/content-assets' + path, {
    method, credentials: 'same-origin', cache: 'no-store',
    headers: type ? {'Content-Type': type} : undefined, body,
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || '文件上传失败，请重试。');
  return result.data;
}

async function upload(file, purpose, onProgress) {
  if (!file || !Number.isSafeInteger(file.size) || file.size < 1) throw new Error('请选择非空文件。');
  if (file.size > fileUploadLimit(file, 100 * 1024 ** 2)) {
    throw new Error(isUploadVideo(file) ? '单个视频最多 2 GB。' : '单个文档最多 100 MB。');
  }
  const session = await send('', 'POST', JSON.stringify({name:file.name, size:file.size, purpose}), 'application/json');
  if (!Number.isSafeInteger(session.chunkSize) || session.chunkSize <= 0) throw new Error('上传分片参数无效。');
  const path = '/' + encodeURIComponent(session.id);
  try {
    for (let offset=0, pos=0; offset<file.size; offset+=session.chunkSize, pos++) {
      const end = Math.min(file.size, offset + session.chunkSize);
      await send(path+'/chunks/'+pos, 'PUT', file.slice(offset,end), 'application/octet-stream');
      onProgress?.(Math.round(100 * end / file.size));
    }
    return await send(path+'/complete', 'POST', '{}', 'application/json');
  } catch (error) {
    await send(path, 'DELETE').catch(()=>{});
    throw error;
  }
}

export const uploadCourseAsset = (file,onProgress) => upload(file,'course',onProgress);
export async function uploadTaskVideo(file,camp,onProgress) {
  const {id,name,type,url,mime,size} = await upload(file,camp,onProgress);
  return {id,name,type,url,mime,size};
}
