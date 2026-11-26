import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';
import { uploadAcademyAsset } from './academy-upload.js';
import { showFieldError } from './field-feedback.js';

function preview(course) {
  const images = course.materials.filter(item => item.kind === 'image');
  const video = course.materials.find(item => item.kind === 'video');
  if (course.cover?.assetId) {
    return { image: '/api/review-native/content-assets/' + encodeURIComponent(course.cover.assetId), caption: '自定义封面' };
  }
  const selected = images.find(item => item.id === course.cover?.materialId);
  if (selected) return { image: selected.url, caption: '课程图片 · ' + selected.title };
  if (images.length) return { image: images[0].url, caption: '自动使用第一张课程图片' };
  if (video) return { video: video.url, caption: '自动使用第一段视频的开头画面' };
  return { caption: '添加图片或视频后，可直接用作封面。' };
}

function materialOptions(items, selected) {
  return items.map(item => `<option value="${e(item.id)}" ${item.id === selected ? 'selected' : ''}>${e(item.title)}</option>`).join('');
}

export function renderCourseCover(editor) {
  const { course } = editor;
  const images = course.materials.filter(item => item.kind === 'image');
  const videos = course.materials.filter(item => item.kind === 'video');
  const current = preview(course);
  const frameSource = videos.find(item => item.id === editor.coverVideoId);
  const imageSelect = images.length ? `<label class="ac-field aw-cover-source"><span>使用课程图片</span><select data-aw-cover-image>
    <option value="" disabled ${course.cover?.materialId ? '' : 'selected'}>选择图片</option>${materialOptions(images,course.cover?.materialId)}
  </select></label>` : '';
  const framePicker = frameSource ? `<div class="aw-frame-picker">
    <label class="ac-field"><span>截帧视频</span><select data-aw-frame-source>${materialOptions(videos,frameSource.id)}</select></label>
    <video data-aw-frame-video controls playsinline muted preload="auto" aria-label="选择课程封面画面"></video>
    <div class="aw-cover-actions"><button type="button" class="ac-btn ac-btn-primary" data-aw-frame-use disabled>使用当前画面</button>
      <button type="button" class="ac-btn ac-btn-secondary" data-aw-frame-cancel>取消截帧</button>
      <small class="ac-muted">拖动视频进度条，停在想用作封面的画面。</small></div>
  </div>` : '';
  return `<section class="aw-section aw-course-cover"><h2>课程封面</h2>
    <div class="aw-cover-layout"><div class="aw-cover-preview">
      ${current.image ? `<img src="${e(current.image)}" alt="当前课程封面" data-aw-preview-media>` :
        current.video ? `<video src="${e(current.video)}" muted playsinline preload="metadata" aria-label="当前视频封面" data-aw-preview-media></video>` : ''}
      <span data-aw-preview-placeholder ${current.image || current.video ? 'hidden' : ''}>${current.image || current.video ? '封面预览暂不可用' : '学院默认封面'}</span></div>
      <div class="aw-cover-settings"><p class="ac-muted">${e(current.caption)}</p>
        ${imageSelect}<div class="aw-cover-actions"><button type="button" class="ac-btn ac-btn-secondary" data-aw-cover-upload>上传封面图</button>
        <input type="file" accept=".png,.jpg,.jpeg,.webp,.gif" data-aw-cover-file hidden>
        ${videos.length && !frameSource ? '<button type="button" class="ac-btn ac-btn-secondary" data-aw-open-frames>从视频截帧</button>' : ''}
        ${course.cover ? '<button type="button" class="ac-btn ac-btn-ghost" data-aw-cover-auto>恢复自动封面</button>' : ''}</div>
      </div></div>${framePicker}
    </section>`;
}

async function verifyImage(file) {
  if (!/\.(png|jpe?g|webp|gif)$/i.test(file.name)) throw new Error('请上传 JPG、PNG、WebP 或 GIF 图片。');
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
  } catch {
    throw new Error('无法读取这张图片，请重新选择。');
  } finally {
    URL.revokeObjectURL(url);
  }
}

function captureFrame(video) {
  if (video.seeking || video.readyState < 2 || !video.videoWidth) throw new Error('请等画面加载完成后再截取。');
  video.pause();
  const scale = Math.min(1,1280 / Math.max(video.videoWidth,video.videoHeight));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1,Math.round(video.videoWidth * scale));
  canvas.height = Math.max(1,Math.round(video.videoHeight * scale));
  const context = canvas.getContext('2d');
  if (!context) throw new Error('当前浏览器无法生成视频截图，请上传封面图。');
  context.drawImage(video,0,0,canvas.width,canvas.height);
  return new Promise((resolve,reject) => {
    try {
      canvas.toBlob(blob => blob ? resolve(new File([blob],'视频封面.jpg',{type:'image/jpeg'})) : reject(new Error('未能生成截图，请重试。')), 'image/jpeg', 0.9);
    } catch {
      reject(new Error('视频来源限制了截图，请单独上传封面图。'));
    }
  });
}

export function bindCourseCover(form,editor,{work,redraw}) {
  const section = form.querySelector('.aw-course-cover');
  const find = selector => section.querySelector(selector);
  const media = find('[data-aw-preview-media]');
  if (media) {
    const failed = () => { media.hidden = true; find('[data-aw-preview-placeholder]').hidden = false; };
    media.addEventListener('error',failed);
    if (media instanceof HTMLVideoElement) {
      const loadFrame = () => { if (Number.isFinite(media.duration)) media.currentTime = Math.min(0.1, media.duration / 2); };
      if (media.error) failed();
      else if (media.readyState >= 1) loadFrame();
      else media.addEventListener('loadedmetadata',loadFrame,{once:true});
    } else if (media.complete && !media.naturalWidth) failed();
  }
  function closePicker() {
    editor.coverVideoId = null;
    editor.coverTime = 0;
  }
  function changeCover(cover) {
    editor.course.cover = cover;
    closePicker();
    redraw();
  }
  function chooseVideo(id) {
    editor.coverVideoId = id;
    editor.coverTime = 0;
    redraw();
  }
  function upload(fileOrFrame,verify) {
    void work(async () => {
      const file = await fileOrFrame;
      if (verify) await verifyImage(file);
      const image = await uploadAcademyAsset(file);
      editor.course.cover = {assetId:image.assetId};
      closePicker();
    },undefined,{selector:verify ? '[data-aw-cover-upload]' : '[data-aw-frame-source]'});
  }
  const input = find('[data-aw-cover-file]');
  find('[data-aw-cover-upload]').onclick = () => input.click();
  input.onchange = () => { if (input.files[0]) upload(input.files[0],true); };
  find('[data-aw-cover-image]')?.addEventListener('change',event => changeCover({materialId:event.target.value}));
  find('[data-aw-cover-auto]')?.addEventListener('click',() => changeCover(null));
  find('[data-aw-open-frames]')?.addEventListener('click',() => chooseVideo(editor.course.materials.find(item => item.kind === 'video').id));
  find('[data-aw-frame-cancel]')?.addEventListener('click',() => { closePicker(); redraw(); });

  const player = find('[data-aw-frame-video]');
  if (!player || editor.busy) return;
  const source = editor.course.materials.find(item => item.id === editor.coverVideoId);
  const button = find('[data-aw-frame-use]');
  find('[data-aw-frame-source]').onchange = event => chooseVideo(event.target.value);
  const url = new URL(source.url,location.origin);
  if (url.origin !== location.origin) player.crossOrigin = 'anonymous';
  player.onloadedmetadata = () => {
    if (editor.coverTime > 0 && Number.isFinite(player.duration)) player.currentTime = Math.min(editor.coverTime,player.duration);
  };
  player.ontimeupdate = () => { editor.coverTime = player.currentTime; };
  const updateButton = () => { button.disabled = player.seeking || player.readyState < 2; };
  player.onloadeddata = player.onseeked = player.onseeking = updateButton;
  player.onerror = () => {
    button.disabled = true;
    showFieldError(find('[data-aw-frame-source]'),'未能读取视频画面。请检查视频地址及截图权限，或单独上传封面图。',{focus:false});
  };
  player.src = url.href;
  button.onclick = () => {
    try { upload(captureFrame(player),false); }
    catch (error) { showFieldError(button,error.message); }
  };
}
