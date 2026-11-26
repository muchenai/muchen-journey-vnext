import { uploadCourseAsset, isUploadVideo } from './course-asset-upload.js';
async function fileDuration(file) {
  if (!isUploadVideo(file)) return undefined;
  const player = document.createElement('video'), url = URL.createObjectURL(file);
  try {
    return await new Promise(resolve => {
      const finish = () => {
        clearTimeout(timer);
        player.onloadedmetadata = player.onerror = null;
        resolve(Number.isFinite(player.duration) && player.duration > 0 ? player.duration : undefined);
      };
      const timer = setTimeout(finish, 8000);
      player.onloadedmetadata = player.onerror = finish;
      player.preload = 'metadata';
      player.src = url;
    });
  } finally { player.removeAttribute('src'); player.load(); URL.revokeObjectURL(url); }
}

export async function uploadAcademyAsset(file, onProgress) {
  const durationSeconds = await fileDuration(file);
  const video = isUploadVideo(file);
  if (video && !durationSeconds) throw new Error('无法读取视频时长，请选择浏览器支持播放的视频。');
  const asset = await uploadCourseAsset(file, onProgress);
  const kind = asset.mime.startsWith('video/') ? 'video' : asset.mime.startsWith('image/') ? 'image' : 'document';
  return { id: crypto.randomUUID(), assetId:asset.id, kind, name:asset.name, title:asset.name,
    url:'/api/review-native/content-assets/'+encodeURIComponent(asset.id), mime:asset.mime, size:asset.size,
    ...(durationSeconds ? {durationSeconds} : {}) };
}
