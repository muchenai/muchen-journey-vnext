/** Local AI Academy prototype. Metadata is JSON; video bytes live only in IndexedDB. */
export const COURSE_TYPES = Object.freeze([
  { id: 'link', label: '外链课程' },
  { id: 'video', label: '平台视频' },
  { id: 'share', label: '员工分享' },
]);

const STORAGE_KEY = 'journey_academy_v1';
const VIDEO_DB = 'journey_academy_videos_v1';
const VIDEO_STORE = 'videos';
const LEVELS = ['入门', '进阶', '挑战'];
const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));
const text = value => String(value ?? '').trim();
const now = () => new Date().toISOString();
const uid = prefix => `${prefix}-${Date.now().toString(36)}-${globalThis.crypto?.randomUUID?.() || Math.random().toString(36).slice(2)}`;
const finite = value => value !== null && value !== undefined && text(value) !== '' && Number.isFinite(Number(value));
const rounded = value => Math.round(value * 10) / 10;

export function validateExternalUrl(value) {
  const raw = String(value ?? '');
  const invalid = message => ({ valid: false, url: '', message });
  if (!raw) return invalid('请填写完整的课程链接');
  if (/\s|\\/.test(raw)) return invalid('课程链接不能包含空格或反斜杠');
  if (!/^https?:\/\//i.test(raw)) return invalid('课程链接需以 http:// 或 https:// 开头');
  try {
    const url = new URL(raw);
    if (!['http:', 'https:'].includes(url.protocol)) return invalid('仅支持 http 或 https 链接');
    const authority = raw.match(/^https?:\/\/([^/?#]*)/i)?.[1] || '';
    if (url.username || url.password || authority.includes('@')) return invalid('课程链接不能包含账号或密码');
    const host = url.hostname.toLowerCase();
    if (!host || host.length > 253) return invalid('请填写有效的课程域名');
    const ipv6 = host.startsWith('[') && host.endsWith(']');
    const ipv4 = /^\d{1,3}(\.\d{1,3}){3}$/.test(host) && host.split('.').every(part => Number(part) <= 255);
    const labels = host.replace(/\.$/, '').split('.');
    const validLabels = labels.every(label => label.length <= 63 && /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i.test(label));
    const localhost = host === 'localhost' || host.endsWith('.localhost') && validLabels;
    const domain = labels.length >= 2 && validLabels;
    if (!ipv6 && !ipv4 && !localhost && !domain) return invalid('请填写有效的课程域名');
    return { valid: true, url: url.href, message: '' };
  } catch { return invalid('链接格式无效，请填写完整的 http 或 https 地址'); }
}

function seedData() {
  const editor = { id: 'academy-editor', name: 'AI 学院' };
  const course = (id, title, summary, url, minutes, level, category, extra = {}) => ({
    id, type: 'link', title, summary, url, minutes, level, category, author: editor,
    createdAt: '2026-10-21T02:00:00.000Z', linkState: 'active', status: 'published', demo: true, ...extra,
  });
  const courses = [
    course('academy-ai-foundations', '认识生成式 AI：从概念到工作场景', '建立对大模型能力、使用方式和常见边界的基础认识，找到适合自己的第一个应用场景。', 'https://openai.com/', 20, '入门', 'AI 基础'),
    course('academy-prompt-design', '把问题说清楚：提示词设计入门', '练习目标、背景、约束与输出格式的组织方式，让每一次提问都有明确的期待。', 'https://www.anthropic.com/', 25, '入门', '提示词实践'),
    course('academy-model-landscape', '模型与工具：搭建自己的学习地图', '了解模型、数据集和工具之间的关系，为后续实践整理一份可持续更新的学习清单。', 'https://huggingface.co/', 35, '进阶', '模型与工具'),
    course('academy-office-ai', 'AI 与日常办公：找到可复用的流程', '从会议整理、文档分析和知识归纳出发，把一次性的尝试变成可复用的工作方法。', 'https://www.microsoft.com/', 30, '进阶', '办公提效'),
    course('academy-verification', 'AI 信息核查：一份案例复盘', '通过案例理解事实核查、来源追踪与交叉验证。本演示条目的链接已标记失效，等待管理员更新。', 'https://www.deepseek.com/', 40, '挑战', '质量与评估', { linkState: 'expired' }),
    course('academy-video-workflow', '用 AI 拆解一个完整的工作任务', '平台视频演示占位：尚未上传真实视频文件。管理员上传课程视频后，即可在站内观看并记录学习进度。', '', 28, '进阶', '工作流实践', {
      type: 'video', videoName: '演示课程 · 暂无视频文件', videoSize: 0, demo: true,
    }),
  ];
  const share = (id, title, summary, url, author, status, extra = {}) => ({
    id, courseId: id, type: 'share', title, summary, url, author, status, demo: true,
    minutes: 15, level: '入门', category: '员工实践', createdAt: '2026-10-21T03:00:00.000Z',
    linkState: 'active', reason: '', reviewedAt: status === 'pending' ? null : '2026-10-21T05:00:00.000Z', ...extra,
  });
  const member = { id: 'preview-member', name: '陈一诺' };
  const shares = [
    share('academy-share-research', '我的实践：把调研笔记变成结构化洞察', '分享如何整理零散访谈、核对原始材料，再用 AI 辅助提炼可验证的产品洞察。', 'https://openai.com/', { id: 'employee-qiao', name: '乔安' }, 'approved', { minutes: 18, level: '进阶' }),
    share('academy-share-review', '团队共学：给 AI 输出做一次质量复盘', '一份围绕准确性、完整性与可执行性的复盘方法，适合在团队内开展轻量共学。', 'https://huggingface.co/', { id: 'employee-lin', name: '林可' }, 'approved', { minutes: 22, category: '经验复盘' }),
    share('academy-share-pending-1', '我用 AI 整理每周工作复盘', '把周报素材分成事实、问题与行动，保留人工确认环节，减少遗漏。', 'https://www.anthropic.com/', member, 'pending'),
    share('academy-share-pending-2', '从零搭建个人提示词笔记', '分享提示词分类、结果对照和迭代记录的组织方法。', 'https://www.microsoft.com/', { id: 'employee-xu', name: '许知夏' }, 'pending'),
    share('academy-share-rejected-1', '一次自动生成行业报告的尝试', '记录用 AI 辅助整理行业资料的过程与踩坑经验。', 'https://www.deepseek.com/', member, 'rejected', { reason: '请补充引用来源、人工核查步骤和一份完整的输出示例后再分享。' }),
  ];
  const records = {
    'preview-member': {
      'academy-ai-foundations': { courseId: 'academy-ai-foundations', courseTitle: courses[0].title, type: 'link', progress: 100, completed: true, seconds: 1200, duration: 1200, updatedAt: '2026-10-21T06:20:00.000Z' },
      'academy-prompt-design': { courseId: 'academy-prompt-design', courseTitle: courses[1].title, type: 'link', progress: 20, completed: false, seconds: 300, duration: 1500, updatedAt: '2026-10-21T06:30:00.000Z' },
    },
  };
  return { version: 1, courses, shares, records };
}

export function createAcademyStore({ getCurrentUser } = {}) {
  let storage;
  try { storage = globalThis.localStorage; } catch { storage = null; }
  let data = seedData();
  try {
    const saved = JSON.parse(storage?.getItem(STORAGE_KEY) || 'null');
    if (saved && Array.isArray(saved.courses) && Array.isArray(saved.shares) && saved.records && typeof saved.records === 'object') data = saved;
  } catch { /* Keep the independent academy seed when no readable metadata exists. */ }
  let dbPromise;
  const videoUrls = new Map();
  const verifiedVideos = new Set();

  function user() {
    const current = typeof getCurrentUser === 'function' ? getCurrentUser() : null;
    return current ? { id: current.id, name: current.name, accessRole: current.accessRole } : null;
  }
  function isAdmin() { return ['super_admin', 'admin'].includes(user()?.accessRole); }
  function requireUser() {
    const current = user();
    if (!current?.id) throw new Error('请先登录后使用 AI 学院');
    return current;
  }
  function requireAdmin() {
    if (!isAdmin()) throw new Error('仅管理员可管理学院课程与分享审核');
    return requireUser();
  }
  function persist() {
    if (!storage) throw new Error('浏览器本地存储不可用，暂时无法保存学院数据');
    try { storage.setItem(STORAGE_KEY, JSON.stringify(data)); }
    catch { throw new Error('学院数据保存失败，浏览器存储空间可能不足'); }
  }
  function commit(change) {
    const snapshot = clone(data);
    try { const result = change(); persist(); return clone(result); }
    catch (error) { data = snapshot; throw error; }
  }
  function managedCourseView(course) {
    return {
      ...clone(course),
      ...(course.type === 'share' ? { status: 'published', shareStatus: 'approved', courseId: course.id } : {}),
      visibility: course.visibility === 'unpublished' ? 'unpublished' : 'published',
    };
  }
  function managedCourses() {
    return [
      ...data.courses.filter(course => course.status === 'published'),
      ...data.shares.filter(share => share.status === 'approved'),
    ].map(managedCourseView);
  }
  function publicCourses() { return managedCourses().filter(course => course.visibility !== 'unpublished'); }
  function withProgress(course) {
    if (!course) return null;
    const record = data.records[user()?.id]?.[course.id];
    return { ...clone(course), progress: Number(record?.progress) || 0, completed: Boolean(record?.completed) };
  }
  function getCourse(id) { return withProgress(publicCourses().find(course => course.id === id)); }
  function courseSource(id) { return data.courses.find(course => course.id === id) || data.shares.find(share => share.id === id && share.status === 'approved'); }
  function metadata(payload = {}) {
    const title = text(payload.title);
    const summary = text(payload.summary);
    if (!title || title.length > 100) throw new Error('课程标题需为 1～100 个字符');
    if (!summary) throw new Error('请填写简介');
    if (summary.length > 1200) throw new Error('课程简介不能超过 1200 个字符');
    const minutes = payload.minutes === undefined || payload.minutes === '' ? 20 : Number(payload.minutes);
    if (!Number.isFinite(minutes) || minutes <= 0) throw new Error('预计学习时长需大于 0 分钟');
    const level = payload.level || '入门';
    if (!LEVELS.includes(level)) throw new Error('请选择入门、进阶或挑战难度');
    return { title, summary, minutes: Math.max(0.1, rounded(minutes)), level };
  }
  function openVideoDB() {
    if (!globalThis.indexedDB) return Promise.reject(new Error('当前浏览器不支持本地视频存储'));
    if (!dbPromise) dbPromise = new Promise((resolve, reject) => {
      const request = globalThis.indexedDB.open(VIDEO_DB, 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(VIDEO_STORE)) request.result.createObjectStore(VIDEO_STORE, { keyPath: 'courseId' });
      };
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => { db.close(); dbPromise = null; };
        resolve(db);
      };
      request.onerror = () => { dbPromise = null; reject(new Error('无法打开本地视频存储')); };
      request.onblocked = () => { dbPromise = null; reject(new Error('本地视频存储被其他页面占用，请关闭旧页面后重试')); };
    });
    return dbPromise;
  }
  async function writeVideo(courseId, file) {
    const db = await openVideoDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(VIDEO_STORE, 'readwrite');
      transaction.objectStore(VIDEO_STORE).put({ courseId, blob: file, name: file.name, size: file.size, storedAt: now() });
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(new Error('视频保存失败，请检查浏览器可用存储空间'));
      transaction.onabort = () => reject(new Error('视频保存未完成，请重试'));
    });
  }
  async function deleteVideo(courseId) {
    const db = await openVideoDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(VIDEO_STORE, 'readwrite');
      transaction.objectStore(VIDEO_STORE).delete(courseId);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(new Error('无法清理本地视频'));
      transaction.onabort = () => reject(new Error('本地视频清理未完成'));
    });
  }
  async function readVideo(courseId) {
    const db = await openVideoDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(VIDEO_STORE, 'readonly');
      const request = transaction.objectStore(VIDEO_STORE).get(courseId);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(new Error('无法读取本地课程视频'));
      transaction.onabort = () => reject(new Error('本地视频读取未完成'));
    });
  }

  return {
    isAdmin,
    user,
    listCourses({ query = '', type = 'all' } = {}) {
      const search = text(query).toLocaleLowerCase();
      return publicCourses().filter(course => (type === 'all' || course.type === type) && (!search || [course.title, course.summary, course.category, course.author?.name].some(value => text(value).toLocaleLowerCase().includes(search)))).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))).map(withProgress);
    },
    getCourse,
    listManagedCourses({ query = '', type = 'all' } = {}) {
      requireAdmin();
      const search = text(query).toLocaleLowerCase();
      return managedCourses().filter(course => (type === 'all' || course.type === type) && (!search || [course.title, course.summary, course.category, course.author?.name].some(value => text(value).toLocaleLowerCase().includes(search)))).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
    },
    getManagedCourse(id) {
      requireAdmin();
      return managedCourses().find(course => course.id === id) || null;
    },
    getAdminStats() {
      requireAdmin();
      const courses = managedCourses();
      const published = courses.filter(course => course.visibility === 'published').length;
      return { total: courses.length, published, unpublished: courses.length - published, pending: data.shares.filter(share => share.status === 'pending').length };
    },
    setCourseVisibility(id, visible) {
      requireAdmin();
      if (typeof visible !== 'boolean') throw new Error('请选择上架或下架状态');
      if (!managedCourses().some(course => course.id === id)) throw new Error('未找到可管理的课程');
      const source = courseSource(id);
      return commit(() => {
        source.visibility = visible ? 'published' : 'unpublished';
        source.updatedAt = now();
        return managedCourseView(source);
      });
    },
    listShares({ mine = false } = {}) {
      const current = user();
      if (!current?.id) return [];
      return clone(data.shares.filter(share => isAdmin() && !mine || share.author?.id === current.id).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))));
    },
    async addCourse(payload = {}) {
      const current = requireAdmin();
      if (!['link', 'video'].includes(payload.type)) throw new Error('管理员可添加外链课程或平台视频');
      const values = metadata(payload);
      let url = '';
      if (payload.type === 'link') {
        const result = validateExternalUrl(payload.url);
        if (!result.valid) throw new Error(result.message);
        url = result.url;
      }
      const file = payload.file;
      if (payload.type === 'video') {
        if (typeof globalThis.File !== 'function' || !(file instanceof globalThis.File) || file.size <= 0) throw new Error('请选择真实且非空的视频文件');
        if (!file.type.startsWith('video/') && !/\.(mp4|webm|ogv|ogg|mov|m4v)$/i.test(file.name)) throw new Error('请选择 MP4、WebM 或其他视频文件');
      }
      const course = {
        id: uid('academy-course'), type: payload.type, ...values, url,
        category: payload.type === 'video' ? '视频课程' : 'AI 学习',
        author: { id: current.id, name: current.name || '管理员' }, createdAt: now(), linkState: 'active', status: 'published', visibility: 'published',
        ...(payload.type === 'video' ? { videoName: file.name, videoSize: file.size } : {}),
      };
      if (payload.type === 'video') await writeVideo(course.id, file);
      try {
        // Re-read authorization after an asynchronous upload before making it public.
        const latest = requireAdmin();
        if (latest.id !== current.id) throw new Error('当前账号已切换，请重新添加课程');
        const result = commit(() => { data.courses.unshift(course); return course; });
        if (payload.type === 'video') verifiedVideos.add(course.id);
        return { ...result, progress: 0, completed: false };
      } catch (error) {
        if (payload.type === 'video') { try { await deleteVideo(course.id); } catch { /* Metadata was never published. */ } }
        throw error;
      }
    },
    async updateCourse(id, payload = {}) {
      const current = requireAdmin();
      if (!managedCourses().some(course => course.id === id)) throw new Error('未找到可管理的课程');
      const original = courseSource(id);
      const fields = {};
      for (const field of ['title', 'summary', 'url', 'minutes', 'level']) {
        if (payload[field] !== undefined) fields[field] = payload[field];
      }
      const values = metadata({ ...original, ...fields });
      let url = '';
      if (original.type !== 'video') {
        const result = validateExternalUrl(fields.url ?? original.url);
        if (!result.valid) throw new Error(result.message);
        url = result.url;
      }
      const file = payload.file;
      const replacingVideo = original.type === 'video' && file != null;
      let stagedVideoKey = null;
      const oldVideoKey = original.videoStorageKey || original.id;
      if (replacingVideo) {
        if (typeof globalThis.File !== 'function' || !(file instanceof globalThis.File) || file.size <= 0) throw new Error('请选择真实且非空的视频文件');
        if (!file.type.startsWith('video/') && !/\.(mp4|webm|ogv|ogg|mov|m4v)$/i.test(file.name)) throw new Error('请选择 MP4、WebM 或其他视频文件');
        // Stage a separate blob; the currently published video remains untouched.
        stagedVideoKey = `${id}:${uid('video')}`;
        await writeVideo(stagedVideoKey, file);
      }
      let result;
      try {
        const latestUser = requireAdmin();
        if (latestUser.id !== current.id) throw new Error('当前账号已切换，请重新保存课程');
        if (!managedCourses().some(course => course.id === id)) throw new Error('未找到可管理的课程');
        result = commit(() => {
          const source = courseSource(id);
          Object.assign(source, values, { url, updatedAt: now() });
          if (source.type !== 'video') source.linkState = 'active';
          if (replacingVideo) {
            source.videoStorageKey = stagedVideoKey;
            source.videoName = file.name;
            source.videoSize = file.size;
          }
          return managedCourseView(source);
        });
      } catch (error) {
        if (stagedVideoKey) { try { await deleteVideo(stagedVideoKey); } catch { /* Original video remains available. */ } }
        throw error;
      }
      if (replacingVideo) {
        const cached = videoUrls.get(id);
        if (cached) { try { URL.revokeObjectURL(cached); } catch { /* A cache URL may already be revoked. */ } }
        videoUrls.delete(id);
        verifiedVideos.delete(id);
        try { await deleteVideo(oldVideoKey); } catch { /* Keep an unreferenced old blob rather than fail a committed edit. */ }
      }
      return result;
    },
    submitShare(payload = {}) {
      const current = requireUser();
      const values = metadata({ ...payload, minutes: 15, level: '入门' });
      const result = validateExternalUrl(payload.url);
      if (!result.valid) throw new Error(result.message);
      const id = uid('academy-share');
      const share = {
        id, courseId: id, type: 'share', ...values, url: result.url, category: '员工实践',
        author: { id: current.id, name: current.name || '学院成员' }, createdAt: now(), linkState: 'active',
        status: 'pending', reason: '', reviewedAt: null,
      };
      return commit(() => { data.shares.unshift(share); return share; });
    },
    reviewShare(id, { decision, reason = '' } = {}) {
      const current = requireAdmin();
      if (!['approved', 'rejected'].includes(decision)) throw new Error('请选择批准或驳回');
      const reviewReason = text(reason);
      if (decision === 'rejected' && !reviewReason) throw new Error('驳回分享时请填写原因');
      if (reviewReason.length > 1000) throw new Error('审核原因不能超过 1000 个字符');
      const share = data.shares.find(item => item.id === id);
      if (!share) throw new Error('未找到这条分享');
      if (share.status === decision) return clone(share);
      if (share.status !== 'pending') throw new Error('这条分享已经审核完成');
      if (decision === 'approved') {
        const result = validateExternalUrl(share.url);
        if (!result.valid) throw new Error(result.message);
      }
      return commit(() => {
        share.status = decision;
        share.reason = decision === 'rejected' ? reviewReason : '';
        share.reviewedAt = now();
        share.reviewedBy = { id: current.id, name: current.name };
        share.courseId = share.id;
        return share;
      });
    },
    async getVideoUrl(courseId) {
      const course = (isAdmin() ? managedCourses() : publicCourses()).find(item => item.id === courseId && item.type === 'video');
      if (!course || course.linkState === 'expired') return null;
      if (!globalThis.indexedDB) return null;
      const record = await readVideo(course.videoStorageKey || courseId);
      if (!record || typeof globalThis.Blob !== 'function' || !(record.blob instanceof globalThis.Blob) || record.blob.size <= 0) {
        verifiedVideos.delete(courseId);
        return null;
      }
      verifiedVideos.add(courseId);
      if (!videoUrls.has(courseId)) videoUrls.set(courseId, URL.createObjectURL(record.blob));
      return videoUrls.get(courseId);
    },
    updateProgress(courseId, { seconds, duration, completed } = {}) {
      const current = requireUser();
      const course = getCourse(courseId);
      if (!course) throw new Error('课程未公开或不存在');
      if (course.linkState === 'expired') throw new Error('这门课程的链接已失效，暂时无法记录完成');
      if (course.type === 'video' && !verifiedVideos.has(courseId)) throw new Error('请先加载真实课程视频后再记录学习进度');
      if (seconds !== undefined && (!finite(seconds) || Number(seconds) < 0)) throw new Error('学习进度需为有效的非负秒数');
      if (duration !== undefined && (!finite(duration) || Number(duration) <= 0)) throw new Error('视频总时长需大于 0');
      const previous = data.records[current.id]?.[courseId];
      const totalSeconds = duration === undefined ? Number(previous?.duration) || 0 : Number(duration);
      const reported = seconds === undefined ? Number(previous?.seconds) || 0 : Number(seconds);
      const watchedSeconds = Math.max(Number(previous?.seconds) || 0, totalSeconds > 0 ? Math.min(reported, totalSeconds) : reported);
      const videoEnded = course.type === 'video' && totalSeconds > 0 && watchedSeconds >= totalSeconds;
      const isCompleted = Boolean(previous?.completed || completed === true || videoEnded);
      const measured = totalSeconds > 0 ? watchedSeconds / totalSeconds * 100 : 0;
      const progress = isCompleted ? 100 : Math.min(99, Math.max(Number(previous?.progress) || 0, rounded(measured)));
      const record = {
        courseId, courseTitle: course.title, type: course.type, progress, completed: isCompleted,
        seconds: watchedSeconds, duration: totalSeconds, updatedAt: now(),
      };
      return commit(() => { data.records[current.id] ||= {}; data.records[current.id][courseId] = record; return record; });
    },
    getRecords() {
      const current = user();
      if (!current?.id) return [];
      return clone(Object.values(data.records[current.id] || {}).sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt))));
    },
    getStats() {
      const current = user();
      const records = current?.id ? Object.values(data.records[current.id] || {}) : [];
      const completed = records.filter(record => record.completed).length;
      const minutes = records.reduce((sum, record) => {
        const course = publicCourses().find(item => item.id === record.courseId);
        if (course?.type !== 'video' && record.completed) return sum + Number(course?.minutes || 0);
        return sum + (Number(record.seconds) || 0) / 60;
      }, 0);
      return { total: publicCourses().length, completed, inProgress: records.filter(record => !record.completed).length, minutes: rounded(minutes) };
    },
    reportInvalidLink(id) {
      const course = getCourse(id);
      if (!course) throw new Error('课程未公开或不存在');
      if (course.type === 'video') throw new Error('平台视频无需报告外链失效');
      const source = courseSource(id);
      return commit(() => { source.linkState = 'expired'; return source; });
    },
  };
}
