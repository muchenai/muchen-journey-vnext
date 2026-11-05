/** AI Academy data is stored by the server; this cache only renders the current view. */
export const ACADEMY_TAGS = Object.freeze([
  'AI 入门', 'AI 工具推荐', '怎么问 AI', 'AI 使用避坑', 'AIGC 创意玩法',
  'AI 写文案', 'AI 做图片', 'AI 做视频', 'AI 配音与音乐', 'AI 做 PPT',
  'AI 做表格', 'AI 写邮件', 'AI 整理会议纪要', 'AI 写周报与总结', 'AI 查资料',
  'AI 读文档', 'AI 翻译', 'AI 做计划', 'AI 辅助学习', 'AI 日常妙用',
]);

const BASE = '/api/review-native/academy';
const clone = value => structuredClone(value);
const text = value => String(value ?? '').trim();
const CHUNK_SIZE = 524288;
const MAX_VIDEO_SIZE = 524288000;

export function createAcademyApi({ getCurrentUser, fetcher = (...args) => fetch(...args) } = {}) {
  let data = { courses: [], shares: [], stats: { total: 0, published: 0, unpublished: 0, pending: 0 }, tags: [...ACADEMY_TAGS] };
  let loading = false, loaded = false, error = '', refreshing, actorId;
  const uploads = new WeakMap();
  const isAdmin = () => ['super_admin', 'admin'].includes(getCurrentUser?.()?.accessRole);
  const guard = () => {
    const current = getCurrentUser?.();
    if (!current?.id || !isAdmin()) throw new Error('仅管理员可管理 AI 学院');
    if (actorId && actorId !== current.id) throw new Error('登录身份已变更，请刷新页面。');
    actorId = current.id;
    return current;
  };
  async function request(path = '', method = 'GET', body) {
    guard();
    const binary = body instanceof Blob;
    const response = await fetcher(BASE + path, {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': binary ? 'application/octet-stream' : 'application/json' } : {}) },
      ...(body !== undefined ? { body: binary ? body : JSON.stringify(body) } : {}),
    });
    let result;
    try { result = await response.json(); } catch { throw new Error('学院连接失败，请稍后重试。'); }
    guard();
    if (!response.ok || result.ok === false) throw new Error(result.error || '学院操作未完成，请重试。');
    return result.data;
  }
  function counts() {
    const published = data.courses.filter(course => course.visibility !== 'unpublished').length;
    data.stats = { total: data.courses.length, published, unpublished: data.courses.length - published, pending: data.shares.filter(share => share.status === 'pending').length };
  }
  function rememberCourse(course) {
    data.courses = [course, ...data.courses.filter(item => item.id !== course.id)];
    counts();
    return clone(course);
  }
  async function refresh() {
    if (refreshing) return refreshing;
    loading = true; error = '';
    refreshing = (async () => {
      try {
        const snapshot = await request();
        if (!Array.isArray(snapshot?.courses) || !Array.isArray(snapshot?.shares)) throw new Error('学院返回的数据格式不正确。');
        data = { ...snapshot, tags: snapshot.tags?.length ? snapshot.tags : [...ACADEMY_TAGS] };
        loaded = true;
        return clone(data);
      } catch (cause) { error = cause.message || '学院读取失败'; throw cause; }
      finally { loading = false; refreshing = undefined; }
    })();
    return refreshing;
  }
  async function uploadVideo(file, onProgress) {
    if (!(file instanceof Blob) || !file.size) throw new Error('请选择非空的视频文件');
    if (file.size > MAX_VIDEO_SIZE) throw new Error('视频不能超过 500 MB');
    if (!/\.(mp4|webm|ogv|ogg|mov|m4v)$/i.test(file.name || '')) throw new Error('请选择 MP4、WebM、MOV 或 Ogg 视频文件');
    const cached = uploads.get(file);
    if (cached) { onProgress?.(100); return cached; }
    const upload = await request('/uploads', 'POST', { fileName: file.name, size: file.size, mimeType: file.type || 'application/octet-stream' });
    const chunkSize = Number(upload.chunkSize) || CHUNK_SIZE;
    try {
      for (let offset = 0, position = 0; offset < file.size; offset += chunkSize, position++) {
        await request(`/uploads/${encodeURIComponent(upload.id)}/chunks/${position}`, 'PUT', file.slice(offset, offset + chunkSize));
        onProgress?.(Math.min(99, Math.floor(Math.min(offset + chunkSize, file.size) / file.size * 100)));
      }
      const complete = await request(`/uploads/${encodeURIComponent(upload.id)}/complete`, 'POST', {});
      uploads.set(file, complete.id); onProgress?.(100);
      return complete.id;
    } catch (cause) {
      try { await request(`/uploads/${encodeURIComponent(upload.id)}`, 'DELETE'); } catch { /* The server retains interrupted uploads for expiry cleanup. */ }
      throw cause;
    }
  }
  async function writeCourse(id, payload) {
    guard();
    const body = { title: text(payload.title), summary: text(payload.summary), minutes: Number(payload.minutes), tags: payload.tags || [], url: text(payload.url) };
    if (payload.file) body.uploadId = await uploadVideo(payload.file, payload.onProgress);
    if (id) body.expected_revision = payload.expected_revision ?? data.courses.find(item => item.id === id)?.revision;
    else { body.type = payload.type; if (payload.id) body.id = payload.id; }
    const course = await request(id ? `/courses/${encodeURIComponent(id)}` : '/courses', id ? 'PATCH' : 'POST', body);
    if (payload.file) uploads.delete(payload.file);
    return rememberCourse(course);
  }
  return {
    isAdmin, user: getCurrentUser, refresh,
    get loading() { return loading; }, get loaded() { return loaded; }, get error() { return error; },
    getTags: () => [...data.tags],
    listManagedCourses({ query = '', tag = 'all', type = 'all' } = {}) {
      const term = text(query).toLocaleLowerCase();
      return clone(data.courses.filter(course => (tag === 'all' || course.tags?.includes(tag)) && (type === 'all' || course.type === type) && (!term || [course.title, course.summary, course.author?.name, ...(course.tags || [])].some(value => text(value).toLocaleLowerCase().includes(term)))).sort((a, b) => String(b.updatedAt || b.createdAt).localeCompare(String(a.updatedAt || a.createdAt))));
    },
    getManagedCourse: id => clone(data.courses.find(course => course.id === id) || null),
    listShares: () => clone(data.shares),
    getAdminStats: () => clone(data.stats),
    addCourse: payload => writeCourse(null, payload),
    updateCourse: (id, payload) => writeCourse(id, payload),
    async setCourseVisibility(id, visible) {
      const course = data.courses.find(item => item.id === id);
      if (!course) throw new Error('课程已更新，请刷新列表。');
      return rememberCourse(await request(`/courses/${encodeURIComponent(id)}/visibility`, 'POST', { visible, expected_revision: course.revision }));
    },
    async reviewShare(id, { decision, reason, tags }) {
      const share = data.shares.find(item => item.id === id);
      if (!share) throw new Error('分享已更新，请刷新列表。');
      const result = await request(`/shares/${encodeURIComponent(id)}/review`, 'POST', { decision, reason, expected_revision: share.revision, ...(decision === 'approved' && Array.isArray(tags) ? { tags: [...tags] } : {}) });
      const saved = result.share || result;
      data.shares = data.shares.map(item => item.id === id ? saved : item);
      if (result.course) rememberCourse(result.course);
      counts();
      // An acknowledged review remains successful if the following read fails.
      try { await refresh(); } catch { /* Retry is available without repeating the decision. */ }
      return clone(result);
    },
    getVideoUrl(id) { guard(); return `${BASE}/courses/${encodeURIComponent(id)}/video`; },
  };
}
