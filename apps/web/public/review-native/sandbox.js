import { escapeHtml as e, icon } from './core.js?v=20261021-review-decision';

const MAX_ANSWER_LENGTH = 20000;
const clone = value => JSON.parse(JSON.stringify(value));
const text = value => String(value ?? '').trim();
const finite = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const formatScore = value => finite(value).toLocaleString('zh-CN', { maximumFractionDigits: 1 });

function normalizeResult(result) {
  if (result?.advisory && typeof result.comment === 'string') return { ...result, score: null, dimensions: [] };
  if (!result || !Number.isFinite(Number(result.score)) || !Array.isArray(result.dimensions)) return null;
  return {
    score: finite(result.score), passed: Boolean(result.passed),
    comment: String(result.comment || ''), source: String(result.source || ''),
    dimensions: result.dimensions.filter(item => item && typeof item === 'object').map(item => ({
      name: String(item.name || ''), score: finite(item.score), max: finite(item.max),
    })),
  };
}

// Keep only a small digest locally, including for attachments containing data URLs.
function digest(value) {
  const input = typeof value === 'string' ? value : JSON.stringify(value);
  let first = 2166136261;
  let second = 5381;
  for (let index = 0; index < input.length; index++) {
    const code = input.charCodeAt(index);
    first = Math.imul(first ^ code, 16777619);
    second = Math.imul(second, 33) ^ code;
  }
  return `${input.length}:${(first >>> 0).toString(36)}:${(second >>> 0).toString(36)}`;
}

function configuration(task = {}) {
  const files = items => (items || []).map(item => ({
    name: item.name, type: item.type, url: item.url, size: item.size, mime: item.mime,
  }));
  return digest({
    title: task.title, summary: task.summary, domain: task.domain, difficulty: task.difficulty,
    materials: files(task.materials),
    rubric: (task.rubric || []).map(item => ({ name: item.name, points: Number(item.points), description: item.description })),
    rubricAttachments: files(task.rubricAttachments),
    reviewMode: task.reviewMode, passScore: Number(task.passScore),
  });
}

function evaluationIssues(task) {
  if (!text(task.title) || !text(task.summary)) return ['请先填写任务标题和任务简述。'];
  if (!task.materials?.length) return ['请先添加学习材料。'];
  const rubric = task.rubric || [];
  if (!rubric.length || rubric.some(item => !text(item.name) || !text(item.description) || !Number.isFinite(Number(item.points)) || Number(item.points) <= 0)) {
    return ['请先完善 AI 评分标准。'];
  }
  if (Math.abs(rubric.reduce((sum, item) => sum + Number(item.points), 0) - 100) > 0.000001) return ['AI 评分标准的总分需为 100 分。'];
  if (task.passScore == null || !text(task.passScore) || !Number.isFinite(Number(task.passScore)) || Number(task.passScore) < 0 || Number(task.passScore) > 100) return ['请先设置有效的通过分数。'];
  return [];
}

/** Optional author-only test state. Never attached to a task or learner data. */
export function createSandboxController({ store, service, openModal, toast, onChange = () => {} }) {
  const STORAGE_KEY = `${store.storageKey}:sandbox`;
  let records = Object.create(null);
  let aliases = Object.create(null);
  let storageError = false;
  const running = new Set();
  let activeDialog;
  try {
    const saved = JSON.parse(globalThis.localStorage?.getItem(STORAGE_KEY) || 'null');
    if (saved?.version === 1 && saved.records && typeof saved.records === 'object') {
      for (const [key, record] of Object.entries(saved.records)) {
        if (!key.startsWith('task:') || !record || typeof record !== 'object') continue;
        const restoredResult = normalizeResult(record.latest?.result);
        const latest = restoredResult ? { ...record.latest, result: restoredResult } : null;
        records[key] = { answer: String(record.answer || '').slice(0, MAX_ANSWER_LENGTH), updatedAt: record.updatedAt || '', latest };
      }
      for (const [key, target] of Object.entries(saved.aliases || {})) {
        if (key.startsWith('task:') && typeof target === 'string' && target.startsWith('task:') && key !== target) aliases[key] = target;
      }
    }
  } catch { storageError = true; }

  const keyFor = task => `task:${String(task?.sourceTaskId || task?.id || 'unidentified')}`;
  function resolveKey(key) {
    const seen = new Set();
    while (aliases[key] && !seen.has(key)) { seen.add(key); key = aliases[key]; }
    return key;
  }
  function entryFor(key) {
    const resolved = resolveKey(key);
    return records[resolved] ||= { answer: '', updatedAt: '', latest: null };
  }
  function changed() { try { onChange(); } catch { /* Local test state must never block publishing. */ } }
  function persist() {
    try {
      if (!globalThis.localStorage) throw new Error('Storage unavailable');
      globalThis.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, records, aliases }));
      storageError = false;
      return true;
    } catch { storageError = true; return false; }
  }
  function historyReason(task, record) {
    if (!record.latest) return '';
    if (record.latest.fingerprint !== configuration(task)) return '配置已更新';
    if (record.latest.answerFingerprint !== digest(record.answer)) return '示例答案已更新';
    return '';
  }
  function isRunning(key) { return [...running].some(item => resolveKey(item) === resolveKey(key)); }

  function renderCard() {
    const task = store.data.draft;
    const key = keyFor(task);
    const record = entryFor(key);
    const history = historyReason(task, record);
    const busy = isRunning(key);
    const state = busy ? '评测中' : history || (record.latest ? '已有试测结果' : '尚未试测');
    return `<section class="card sandbox-launch-card" aria-label="AI 沙盒评测（选填）">
      <div class="sandbox-launch-head"><h3>${icon('sparkles', 16)} AI 沙盒评测</h3><span class="tag">选填</span></div>
      <p class="sandbox-launch-state${history ? ' is-history' : ''}">${icon(history ? 'clock' : record.latest ? 'checkCircle' : 'help', 14)}<span>${e(state)}</span></p>
      ${record.latest ? `<div class="sandbox-previous-score"><strong>${record.latest.result.advisory ? '已完成' : formatScore(record.latest.result.score)}</strong><span>${record.latest.result.advisory ? '不计分' : '分'} · ${history ? '历史结果' : record.latest.result.advisory ? '建议' : record.latest.result.passed ? '通过' : '未通过'}</span></div>` : ''}
      <p class="sandbox-launch-note">按需试测，不影响发布；答案和结果会保留。</p>
      <button type="button" class="btn btn-secondary sandbox-open-btn" data-open-sandbox>${icon('sparkles', 15)} ${record.latest || record.answer ? '查看 / 继续试测' : '打开沙盒'}</button>
    </section>`;
  }

  function resultHtml(task, record) {
    if (!record.latest) return '<p class="sandbox-empty">暂无试测结果</p>';
    const { result, testedAt } = record.latest;
    const history = historyReason(task, record);
    const date = new Date(testedAt);
    const dateText = Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { hour12: false });
    return `${history ? `<div class="notice sandbox-history-notice">${icon('clock', 16)}<span>${e(history)}，以下为历史结果。可按需重新试测。</span></div>` : ''}
      <section class="sandbox-result" aria-label="最近试测结果">
        <div class="sandbox-result-head"><div><span class="field-hint">最近试测${dateText ? ` · ${e(dateText)}` : ''}</span><h3>${result.advisory ? '评价建议' : formatScore(result.score)}<small>${result.advisory ? '不计分' : '/ 100'}</small></h3></div><span class="tag ${history || result.advisory ? '' : result.passed ? 'tag-green' : 'tag-red'}">${history ? '历史结果' : result.advisory ? '仅供参考' : result.passed ? '通过' : '未通过'}</span></div>
        ${result.dimensions.map(dimension => `<div class="dimension-row"><span>${e(dimension.name)}</span><div class="mini-track"><i style="width:${Math.max(0, Math.min(100, finite(dimension.max) ? finite(dimension.score) / finite(dimension.max) * 100 : 0))}%"></i></div><strong>${formatScore(dimension.score)} <small>/ ${formatScore(dimension.max)}</small></strong></div>`).join('')}
        <p>${e(result.comment || '')}</p>
        ${result.source === 'demo' ? '<div class="field-hint">演示评测，未调用真实 AI。</div>' : ''}
      </section>`;
  }

  function open() {
    if (store.data.draft.reviewMode === 'manual') {
      toast?.('人工审核任务无需 AI 沙盒评测');
      return;
    }
    // Capture this task, so navigating or publishing during an async test cannot
    // place the answer on another task.
    const task = clone(store.data.draft);
    const key = keyFor(task);
    let error = '';
    let modal;
    function render() {
      const record = entryFor(key);
      const busy = isRunning(key);
      const html = `<div class="sandbox-dialog"><div class="modal-heading"><h2>AI 沙盒评测 <span class="tag">选填</span></h2><p>仅供发布前试测，不影响任务发布。</p></div>
        <label class="form-field"><span class="field-label">示例答案</span><textarea id="sandbox-sample-answer" rows="7" maxlength="${MAX_ANSWER_LENGTH}" placeholder="填写一份示例答案，检查评分效果"${busy ? ' disabled' : ''}>${e(record.answer)}</textarea></label>
        <p class="sandbox-local-status field-hint" role="status">${storageError ? '当前浏览器无法保存试测内容，请保留答案后再关闭页面。' : '示例答案和结果仅保存在当前浏览器。'}</p>
        <div class="sandbox-modal-status" role="status" aria-live="polite">${error ? `<p class="notice">${icon('alert', 16)}<span>${e(error)}</span></p>` : busy ? '<p class="field-hint">正在评测…</p>' : ''}</div>
        <div class="modal-actions"><button type="button" class="btn btn-primary" id="sandbox-run"${busy || !text(record.answer) ? ' disabled' : ''}>${icon('sparkles', 16)} ${busy ? '评测中…' : record.latest ? '重新试测' : '开始试测'}</button></div>
        <div id="sandbox-test-result">${resultHtml(task, record)}</div></div>`;
      if (!modal) return html;
      modal.querySelector('.modal-content').innerHTML = html;
      bind();
      return html;
    }
    function bind() {
      const textarea = modal.querySelector('#sandbox-sample-answer');
      const runButton = modal.querySelector('#sandbox-run');
      textarea.addEventListener('input', () => {
        const record = entryFor(key);
        record.answer = textarea.value.slice(0, MAX_ANSWER_LENGTH);
        record.updatedAt = new Date().toISOString();
        persist();
        runButton.disabled = isRunning(key) || !text(record.answer);
        modal.querySelector('.sandbox-local-status').textContent = storageError
          ? '当前浏览器无法保存试测内容，请保留答案后再关闭页面。' : '已保存在当前浏览器';
        modal.querySelector('#sandbox-test-result').innerHTML = resultHtml(task, record);
        changed();
      });
      runButton.addEventListener('click', async () => {
        if (task.reviewMode === 'manual' || store.data.draft.reviewMode === 'manual') {
          error = '人工审核任务无需 AI 沙盒评测';
          toast?.(error);
          render();
          return;
        }
        if (isRunning(key)) return;
        const record = entryFor(key);
        if (!text(record.answer)) { error = '请先填写示例答案。'; render(); return; }
        const issues = evaluationIssues(task);
        if (issues.length) { error = issues[0]; render(); return; }
        const answer = record.answer;
        const fingerprint = configuration(task);
        running.add(key);
        error = '';
        render();
        changed();
        try {
          const result = normalizeResult(await service.evaluations.run(clone(task), answer));
          if (!result) throw new Error('评测结果格式无效，请稍后重试。');
          entryFor(key).latest = { result, fingerprint, answerFingerprint: digest(answer), testedAt: new Date().toISOString() };
          persist();
        } catch (failure) {
          error = failure?.message || '评测失败，请稍后重试。';
          toast?.(error, 'error');
        } finally {
          running.delete(key);
          render();
          if (activeDialog?.render !== render) activeDialog?.render();
          changed();
        }
      });
    }
    openModal(render(), element => { modal = element; activeDialog = { key, render }; bind(); });
  }

  // A first publication can replace a draft ID. Keep author-only state linked
  // to that same task, without adding it to public task payloads.
  function retainForPublishedTask(previousTask, publishedTask) {
    try {
      const oldKey = resolveKey(keyFor(previousTask));
      const nextKey = resolveKey(keyFor(publishedTask));
      if (oldKey === nextKey || !records[oldKey]) return;
      records[nextKey] = records[oldKey];
      aliases[oldKey] = nextKey;
      delete records[oldKey];
      persist();
    } catch { /* Successful publishing must remain successful if local storage fails. */ }
  }

  return { renderCard, open, retainForPublishedTask };
}
