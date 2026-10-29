import { BADGES, escapeHtml as e } from './core.js?v=20261028-publication-local';
import { normalizeBadgeImage, readBadgeImage, svgToBadgeImage } from './badge-image.js?v=20261028-badges-local';

const labels = { draft: '草稿', published: '已上架', unpublished: '已下架' };
const styles = [{ id: 'blue', label: '蓝色' }, { id: 'gold', label: '金色' }, { id: 'green', label: '绿色' }];
const pointsName = id => `${BADGES.find(badge => badge.id === id)?.category || id}徽章点`;
const count = value => Math.round(Number(value || 0)).toLocaleString('zh-CN', { maximumFractionDigits: 0 });
const date = value => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—';
const fresh = () => ({ name: '', description: '', image: '', style: 'blue', costs: [], stock: null, status: 'draft', redemptionLimit: 1 });
const imageCache = new Map();
const imageSource = source => {
  if (!source) return '';
  if (imageCache.has(source)) return imageCache.get(source);
  let image = '';
  try { image = normalizeBadgeImage(source); } catch {}
  if (imageCache.size >= 24) imageCache.clear();
  imageCache.set(source, image);
  return image;
};

function svgPrompt(draft) {
  const direction = draft.costs.map(item => BADGES.find(badge => badge.id === item.badgeId)?.category).filter(Boolean).join('、');
  const color = { blue: '蓝色为主，搭配浅蓝与白色', gold: '金色为主，搭配暖白与深金色', green: '绿色为主，搭配浅绿与白色' }[draft.style] || '蓝色为主';
  return `请为「沐晨 Journey」公司内部游戏化培训平台设计一枚可兑换的能力徽章，并输出完整 SVG 源代码。

徽章名称：${draft.name.trim() || '成长探索者徽章'}
徽章含义：${draft.description.trim() || '通过学习和实践积累能力，记录成长成果。'}
能力方向：${direction || '学习、实践与成长'}
建议配色：${color}。

视觉要求：
1. 根据徽章名称和含义设计一个清晰的中心符号，可用盾牌、圆形或六边形轮廓，具有游戏成就感，简洁精致。
2. 透明背景，图案居中，四周留出约 8% 的安全边距；在浅色、深色背景及 48px 小尺寸下都清晰可辨。
3. 不添加标题、点数、说明文字、水印或复杂背景。用形状和少量渐变体现层次，避免过密细节。

文件要求：
1. 输出可独立保存为 .svg 的静态矢量代码，根节点包含 xmlns="http://www.w3.org/2000/svg"、width="512"、height="512"、viewBox="0 0 512 512"。
2. 使用 path、circle、rect、ellipse、polygon、polyline、line、g 等基础图形，可使用 defs、linearGradient、radialGradient、stop、clipPath；颜色直接写在 fill、stroke 等属性上，渐变仅引用文件内的 url(#id)。
3. 不使用脚本、事件处理、动画、foreignObject、外部图片、外部链接、外部字体、DOCTYPE、滤镜或 CSS style 标签；不输出 base64 图片。
4. 只输出一份完整 SVG 源代码，不要说明文字或 Markdown 代码围栏，文件小于 2 MB。`;
}

export function createMedalsController({ economy, ui }) {
  const state = { tab: 'catalog', status: 'all', query: '', view: 'list', draft: fresh(), saving: false, reading: false, error: '' };
  const ic = (name, size = 16) => ui.icon(name, size);
  const guard = () => { if (economy.isAdmin()) return true; ui.toast('仅管理员可管理徽章', 'error'); return false; };
  const badge = status => `<span class="md-status md-status-${e(status)}">${e(labels[status] || status)}</span>`;
  function artwork(medal, large = false) {
    const source = imageSource(medal.image);
    return `<span class="md-art md-art-${styles.some(style => style.id === medal.style) ? medal.style : 'blue'} ${large ? 'md-art-large' : ''}">${source ? `<img src="${e(source)}" alt="${e(medal.name || '徽章样式')}">` : ic('award', large ? 60 : 28)}</span>`;
  }
  function costList(costs, placeholder = '尚未配置兑换点数') {
    return costs?.length ? `<div class="md-cost-list">${costs.map(item => `<span>${e(pointsName(item.badgeId))}<strong>${count(item.points)}</strong></span>`).join('')}</div>` : `<span class="md-muted">${placeholder}</span>`;
  }
  const redemptionCount = id => economy.listRedemptions({}).filter(record => record.medalId === id).length;

  function medalTable() {
    const medals = economy.listMedals({ query: state.query, status: state.status });
    if (!medals.length) return '<div class="md-empty">暂无徽章，可新增徽章或调整筛选条件。</div>';
    return `<div class="md-table-wrap"><table class="md-table"><thead><tr><th>徽章</th><th>兑换所需点数</th><th>剩余库存</th><th>已兑换</th><th>状态</th><th>操作</th></tr></thead><tbody>${medals.map(medal => `<tr><td><div class="md-medal-cell">${artwork(medal)}<div><button type="button" class="md-row-title" data-md-preview="${e(medal.id)}">${e(medal.name)}</button><small>${e(medal.description || '暂无简介')}</small></div></div></td><td>${costList(medal.costs)}</td><td>${medal.stock === null ? '不限量' : count(medal.stock)}</td><td>${redemptionCount(medal.id)}</td><td>${badge(medal.status)}</td><td><div class="md-row-actions"><button class="text-btn" type="button" data-md-preview="${e(medal.id)}">查看</button><button class="text-btn" type="button" data-md-edit="${e(medal.id)}">编辑</button><button class="text-btn" type="button" data-md-status="${e(medal.id)}">${medal.status === 'published' ? '下架' : '上架'}</button></div></td></tr>`).join('')}</tbody></table></div>`;
  }
  function recordTable() {
    const records = economy.listRedemptions({ query: state.query });
    if (!records.length) return '<div class="md-empty"><strong>暂无兑换记录</strong><p>学员兑换后，这里会显示兑换时间和实际扣除的各类徽章点。</p></div>';
    return `<div class="md-table-wrap"><table class="md-table"><thead><tr><th>学员</th><th>徽章</th><th>实际扣除点数</th><th>兑换时间</th><th>状态</th></tr></thead><tbody>${records.map(record => `<tr><td><strong>${e(record.studentName || record.studentId)}</strong><small>${e(record.studentId)}</small></td><td><div class="md-medal-cell">${artwork({ ...record, name: record.medalName })}<strong>${e(record.medalName)}</strong></div></td><td>${costList(record.costs)}</td><td>${e(date(record.redeemedAt))}</td><td><span class="md-status md-status-published">已兑换</span></td></tr>`).join('')}</tbody></table></div>`;
  }
  function renderList() {
    const stats = economy.getStats();
    return `<header class="md-heading"><h1>徽章系统</h1><button type="button" class="btn btn-primary" data-md-new>${ic('plus')} 新增徽章</button></header><div class="md-tabs" aria-label="徽章管理栏目"><button type="button" class="${state.tab === 'catalog' ? 'active' : ''}" data-md-tab="catalog">徽章管理</button><button type="button" class="${state.tab === 'records' ? 'active' : ''}" data-md-tab="records">兑换记录</button></div><div class="md-stats">${[['全部徽章', stats.total], ['已上架', stats.published], ['草稿', stats.draft], ['累计兑换', stats.redemptions]].map(([label, value]) => `<div><span>${label}</span><strong>${count(value)}</strong></div>`).join('')}</div><div class="md-toolbar">${state.tab === 'catalog' ? `<div class="md-filters" aria-label="徽章状态">${[['all', '全部'], ['published', '已上架'], ['unpublished', '已下架'], ['draft', '草稿']].map(([status, label]) => `<button type="button" class="${state.status === status ? 'active' : ''}" data-md-filter="${status}" aria-pressed="${state.status === status}">${label}</button>`).join('')}</div>` : '<span class="md-muted">按兑换时的点数记录</span>'}<label class="md-search">${ic('search')}<input type="search" value="${e(state.query)}" data-md-search placeholder="${state.tab === 'catalog' ? '搜索徽章名称' : '搜索学员或徽章'}" aria-label="${state.tab === 'catalog' ? '搜索徽章名称' : '搜索学员或徽章'}"></label></div><div data-md-results>${state.tab === 'catalog' ? medalTable() : recordTable()}</div>`;
  }
  function previewCard(medal) {
    return `<div class="md-live-preview">${artwork(medal, true)}<h3>${e(medal.name || '徽章名称')}</h3><p>${e(medal.description || '徽章简介')}</p>${costList(medal.costs)}<div class="md-preview-meta"><span>库存</span><strong>${medal.stock === null ? '不限量' : count(medal.stock)}</strong></div><div class="md-preview-meta"><span>每人限兑</span><strong>1 次</strong></div><small>兑换成功后扣除以上各类徽章点。</small></div>`;
  }
  function costFields() {
    return `<div class="md-cost-fields">${BADGES.map(item => {
      const cost = state.draft.costs.find(value => value.badgeId === item.id);
      return `<div class="md-cost-field ${cost ? 'selected' : ''}"><label><input type="checkbox" data-md-cost-enable="${e(item.id)}" ${cost ? 'checked' : ''}>${e(pointsName(item.id))}</label><div class="md-point-input"><input type="number" min="1" max="1000000" step="1" inputmode="numeric" data-md-cost-value="${e(item.id)}" value="${cost ? e(cost.points) : ''}" ${cost ? '' : 'disabled'} aria-label="${e(pointsName(item.id))}兑换数量"><span>点</span></div></div>`;
    }).join('')}</div>`;
  }
  function renderForm() {
    const draft = state.draft;
    return `<header class="md-heading"><h1>${draft.id ? '编辑徽章' : '新增徽章'}</h1><button type="button" class="btn btn-secondary" data-md-back>返回徽章列表</button></header><div class="md-editor"><div class="md-editor-main"><section class="md-form-section"><h2>基础信息</h2><label class="md-field"><span>徽章名称 <i>*</i></span><input type="text" maxlength="60" data-md-field="name" value="${e(draft.name)}" placeholder="例如：MMOS 开发徽章"></label><label class="md-field"><span>徽章简介</span><textarea maxlength="300" rows="3" data-md-field="description" placeholder="说明徽章代表的能力或项目经历">${e(draft.description)}</textarea></label><div class="md-field"><span>徽章样式</span><div class="md-art-controls"><div class="md-presets">${styles.map(style => `<button type="button" class="md-preset ${draft.style === style.id && !draft.image ? 'active' : ''}" data-md-style="${style.id}" aria-pressed="${draft.style === style.id && !draft.image}" aria-label="使用${style.label}样式">${artwork({ style: style.id })}<span>${style.label}</span></button>`).join('')}</div><div class="md-upload"><label class="btn btn-secondary">${ic('upload')} 上传图片<input type="file" accept=".svg,image/svg+xml,image/png,image/jpeg,image/webp" data-md-image hidden></label>${draft.image ? '<button type="button" class="text-btn" data-md-image-clear>移除图片</button>' : ''}<small>SVG、PNG、JPG、WebP，最大 2 MB</small></div></div><div class="md-svg-help"><div><strong>用豆包制作徽章</strong><small>复制提示词给豆包，生成后上传 SVG 文件，或直接粘贴 SVG 代码。</small></div><div class="md-svg-actions"><button type="button" class="btn btn-secondary" data-md-prompt>复制 SVG 提示词</button><button type="button" class="text-btn" data-md-svg-paste>粘贴 SVG 代码</button></div></div></div></section><section class="md-form-section"><h2>兑换点数 <i>*</i></h2><p class="md-section-hint">勾选所需点数类型；兑换时需同时满足，并分别扣除。</p><div data-md-cost-fields>${costFields()}</div></section><section class="md-form-section"><h2>兑换规则</h2><div class="md-form-grid"><div class="md-field"><span>库存</span><div class="md-stock-options"><label><input type="radio" name="medal-stock" value="unlimited" ${draft.stock === null ? 'checked' : ''}>不限量</label><label><input type="radio" name="medal-stock" value="limited" ${draft.stock !== null ? 'checked' : ''}>限量</label></div><label class="md-field md-stock-count" ${draft.stock === null ? 'hidden' : ''}><span>剩余库存</span><input type="number" min="0" step="1" max="1000000" value="${draft.stock ?? 100}" data-md-stock aria-label="剩余库存"></label></div><div class="md-field"><span>个人兑换上限</span><div class="md-readonly">每人限兑 1 次</div><small>重复提交兑换不会重复扣点。</small></div></div><div class="md-rule-note">已兑换徽章持续保留。下架后停止新兑换，修改价格仅影响后续兑换。</div></section><div class="md-form-error" role="alert" data-md-error>${e(state.error)}</div><div class="md-form-actions"><span class="md-muted" data-md-working>${state.reading ? '正在读取图片…' : ''}</span><div><button type="button" class="btn btn-secondary" data-md-save="current">${draft.status === 'draft' ? '保存草稿' : '保存修改'}</button>${draft.status !== 'published' ? '<button type="button" class="btn btn-primary" data-md-save="published">保存并上架</button>' : ''}</div></div></div><aside class="md-editor-aside"><span class="md-preview-label">样式预览</span><div data-md-live-preview>${previewCard(draft)}</div></aside></div>`;
  }
  function edit(id) {
    if (!guard()) return;
    const medal = id ? economy.getMedal(id) : null;
    if (id && !medal) { ui.toast('未找到徽章', 'error'); return; }
    state.draft = medal ? structuredClone(medal) : fresh();
    state.error = ''; state.view = 'form'; state.reading = false; ui.refresh();
  }
  function detail(id) {
    if (!guard()) return;
    const medal = economy.getMedal(id);
    if (!medal) { ui.toast('未找到徽章', 'error'); return; }
    ui.openModal(`<div class="modal-header"><h2>徽章详情</h2></div><div class="md-detail">${badge(medal.status)}${previewCard(medal)}<div class="md-preview-meta"><span>累计兑换</span><strong>${redemptionCount(medal.id)} 次</strong></div><div class="md-preview-meta"><span>更新时间</span><strong>${e(date(medal.updatedAt))}</strong></div></div><div class="modal-footer"><button type="button" class="btn btn-secondary" data-md-close>关闭</button><button type="button" class="btn btn-primary" data-md-modal-edit>编辑徽章</button></div>`, modal => {
      modal.classList.add('md-detail-modal');
      modal.querySelector('[data-md-close]').onclick = ui.closeModal;
      modal.querySelector('[data-md-modal-edit]').onclick = () => { ui.closeModal(); edit(id); };
    });
  }
  async function setStatus(id) {
    if (!guard() || state.saving) return;
    const medal = economy.getMedal(id);
    if (!medal) return;
    state.saving = true;
    try { await economy.setMedalStatus(id, medal.status === 'published' ? 'unpublished' : 'published'); ui.toast(medal.status === 'published' ? '徽章已下架' : '徽章已上架'); ui.refresh(); }
    catch (error) { ui.toast(error.message || '状态更新失败', 'error'); }
    finally { state.saving = false; }
  }
  function bindList(root) {
    root.onclick = event => {
      const target = event.target.closest('button');
      if (!target) return;
      if (target.hasAttribute('data-md-new')) edit();
      else if (target.dataset.mdTab) { state.tab = target.dataset.mdTab; state.query = ''; ui.refresh(); }
      else if (target.dataset.mdFilter) { state.status = target.dataset.mdFilter; ui.refresh(); }
      else if (target.dataset.mdEdit) edit(target.dataset.mdEdit);
      else if (target.dataset.mdPreview) detail(target.dataset.mdPreview);
      else if (target.dataset.mdStatus) setStatus(target.dataset.mdStatus);
    };
    root.querySelector('[data-md-search]')?.addEventListener('input', event => {
      state.query = event.target.value;
      root.querySelector('[data-md-results]').innerHTML = state.tab === 'catalog' ? medalTable() : recordTable();
    });
  }
  function bindForm(root) {
    const preview = () => { root.querySelector('[data-md-live-preview]').innerHTML = previewCard(state.draft); };
    const error = message => { state.error = message; root.querySelector('[data-md-error]').textContent = message; };
    const lock = () => { root.querySelectorAll('[data-md-save], [data-md-back], [data-md-image], [data-md-svg-paste], [data-md-image-clear]').forEach(input => { input.disabled = state.saving || state.reading; }); root.querySelector('[data-md-working]').textContent = state.reading ? '正在读取图片…' : state.saving ? '正在保存…' : ''; };
    root.querySelectorAll('[data-md-field]').forEach(input => input.addEventListener('input', () => { state.draft[input.dataset.mdField] = input.value; error(''); preview(); }));
    root.querySelector('[data-md-back]').onclick = () => { if (!state.saving && !state.reading) { state.view = 'list'; state.error = ''; ui.refresh(); } };
    root.querySelectorAll('[data-md-style]').forEach(button => button.onclick = () => {
      if (state.reading || state.saving) return;
      state.draft.style = button.dataset.mdStyle; state.draft.image = ''; ui.refresh();
    });
    root.querySelector('[data-md-image-clear]')?.addEventListener('click', () => { if (state.reading || state.saving) return; state.draft.image = ''; ui.refresh(); });
    root.querySelector('[data-md-prompt]').onclick = async event => {
      const button = event.currentTarget;
      const prompt = svgPrompt(state.draft);
      button.disabled = true;
      try {
        await navigator.clipboard.writeText(prompt);
        ui.toast('提示词已复制，粘贴到豆包即可');
      } catch {
        ui.openModal(`<div class="modal-header"><h2>SVG 生成提示词</h2></div><label class="md-field"><span>复制以下内容，粘贴到豆包</span><textarea class="md-code-input" data-md-prompt-text readonly rows="14">${e(prompt)}</textarea></label><div class="modal-footer"><span class="md-muted">已选中，可按 Ctrl+C / ⌘C 复制</span><button type="button" class="btn btn-primary" data-md-close>完成</button></div>`, modal => {
          modal.querySelector('[data-md-close]').onclick = ui.closeModal;
          setTimeout(() => { const field = modal.querySelector('[data-md-prompt-text]'); if (field?.isConnected) { field.focus(); field.select(); } }, 0);
        });
      } finally { if (button.isConnected) button.disabled = false; }
    };
    root.querySelector('[data-md-svg-paste]').onclick = () => {
      if (state.reading || state.saving) return;
      const draft = state.draft;
      ui.openModal(`<div class="modal-header"><h2>粘贴 SVG 代码</h2></div><label class="md-field"><span>粘贴豆包生成的完整 SVG 代码</span><textarea class="md-code-input" data-md-svg-text rows="12" spellcheck="false" placeholder="&lt;svg xmlns=&quot;http://www.w3.org/2000/svg&quot; viewBox=&quot;0 0 512 512&quot;&gt;…&lt;/svg&gt;"></textarea></label><p class="md-form-error" role="alert" data-md-svg-error></p><div class="modal-footer"><button type="button" class="btn btn-secondary" data-md-close>取消</button><button type="button" class="btn btn-primary" data-md-svg-use disabled>使用此样式</button></div>`, modal => {
        const field = modal.querySelector('[data-md-svg-text]');
        const apply = modal.querySelector('[data-md-svg-use]');
        const message = modal.querySelector('[data-md-svg-error]');
        modal.querySelector('[data-md-close]').onclick = ui.closeModal;
        field.oninput = () => { apply.disabled = !field.value.trim(); message.textContent = ''; };
        apply.onclick = () => {
          if (state.draft !== draft || !root.isConnected) { ui.closeModal(); return; }
          try {
            const image = svgToBadgeImage(field.value);
            state.draft.image = image; state.error = '';
            ui.closeModal(); ui.refresh(); ui.toast('SVG 样式已应用');
          } catch (err) { message.textContent = err.message || 'SVG 格式无效，请检查代码'; }
        };
      });
    };
    root.querySelector('[data-md-image]').addEventListener('change', async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      error('');
      state.reading = true; lock();
      const draft = state.draft;
      try {
        const data = await readBadgeImage(file);
        if (state.draft === draft && root.isConnected) { state.draft.image = data; state.reading = false; ui.refresh(); }
      } catch (err) { if (root.isConnected) error(err.message || '图片上传失败'); }
      finally { state.reading = false; if (root.isConnected) { event.target.value = ''; lock(); } }
    });
    const costs = root.querySelector('[data-md-cost-fields]');
    costs.addEventListener('change', event => {
      const id = event.target.dataset.mdCostEnable;
      if (!id) return;
      if (event.target.checked) state.draft.costs.push({ badgeId: id, points: 10 });
      else state.draft.costs = state.draft.costs.filter(item => item.badgeId !== id);
      costs.innerHTML = costFields(); error(''); preview();
    });
    costs.addEventListener('input', event => {
      const id = event.target.dataset.mdCostValue;
      const cost = state.draft.costs.find(item => item.badgeId === id);
      if (cost) { cost.points = event.target.value === '' ? '' : Number(event.target.value); error(''); preview(); }
    });
    root.querySelectorAll('[name="medal-stock"]').forEach(input => input.onchange = () => {
      const field = root.querySelector('[data-md-stock]');
      state.draft.stock = input.value === 'unlimited' ? null : Number(field.value || 100);
      root.querySelector('.md-stock-count').hidden = state.draft.stock === null; preview();
    });
    root.querySelector('[data-md-stock]').oninput = event => { state.draft.stock = event.target.value === '' ? '' : Number(event.target.value); error(''); preview(); };
    root.querySelectorAll('[data-md-save]').forEach(button => button.onclick = async () => {
      if (!guard() || state.saving || state.reading) return;
      error('');
      const status = button.dataset.mdSave === 'published' ? 'published' : state.draft.status;
      state.saving = true; lock();
      try { await economy.saveMedal({ ...structuredClone(state.draft), name: state.draft.name.trim(), status }); state.view = 'list'; state.query = ''; state.status = 'all'; ui.toast(status === 'published' ? '徽章已保存并上架' : '徽章已保存'); ui.refresh(); }
      catch (err) { error(err.message || '保存失败，请重试'); }
      finally { state.saving = false; if (root.isConnected) lock(); }
    });
  }
  return {
    render() { return economy.isAdmin() ? `<div class="medals-page">${state.view === 'form' ? renderForm() : renderList()}</div>` : '<div class="md-empty">仅管理员可管理徽章。</div>'; },
    bind(root) { const page = root.querySelector('.medals-page'); if (!page || !economy.isAdmin()) return; if (state.view === 'form') bindForm(page); else bindList(page); },
    reset() { Object.assign(state, { tab: 'catalog', status: 'all', query: '', view: 'list', draft: fresh(), saving: false, reading: false, error: '' }); },
  };
}
