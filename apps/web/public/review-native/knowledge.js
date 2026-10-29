import { validateKnowledgeUrl, knowledgeFileType } from './knowledge-store.js?v=20261028-server';

const e = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const types = [['all','全部格式'],['link','在线文档'],['ppt','PPT'],['word','Word'],['pdf','PDF'],['sheet','表格'],['image','图片'],['other','其他文件']];
const bytes = value => { const n = Number(value) || 0; return n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.ceil(n / 1024)} KB` : `${n} B`; };
const date = value => { const d = new Date(value); return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('zh-CN'); };
const fileKind = item => item.kind === 'link' ? 'link' : knowledgeFileType(item.fileName || '');
const fileLabel = item => item.kind === 'link' ? '在线文档' : (String(item.fileName || '').match(/\.([a-z0-9]{1,10})$/i)?.[1]?.toUpperCase() || '文件');
const errorText = error => error?.message || '操作失败，请重试';

export function createKnowledgeController({ knowledge, ui }) {
  const state = { loaded: false, loading: false, loadError: '', query: '', category: 'all', type: 'all' };
  let active = false, generation = 0;
  const previewCleanups = new Set();
  const ic = (name, size = 16) => ui.icon(name, size);
  const snapshot = () => knowledge.snapshot();
  const categoryName = id => snapshot().categories.find(category => category.id === id)?.name || '未分类';
  const guard = () => { if (knowledge.isAdmin()) return true; ui.toast('仅管理员可管理知识库', 'error'); return false; };
  const changed = () => { if (active) ui.refresh(); };
  const categoryOptions = selected => snapshot().categories.map(category => `<option value="${e(category.id)}" ${category.id === selected ? 'selected' : ''}>${e(category.name)}</option>`).join('');
  const defaultCategory = () => state.category !== 'all' ? state.category : 'uncategorized';
  const itemById = id => snapshot().items.find(item => item.id === id);
  function results() {
    const query = state.query.trim().toLocaleLowerCase();
    return snapshot().items.filter(item => (state.category === 'all' || item.categoryId === state.category)
      && (state.type === 'all' || fileKind(item) === state.type)
      && (!query || [item.title,item.description,item.fileName,item.url,item.createdBy?.name,categoryName(item.categoryId)].some(value => String(value || '').toLocaleLowerCase().includes(query))))
      .sort((a,b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
  }
  function table() {
    if (state.loadError) return `<div class="kb-empty"><strong>资料暂时无法加载</strong><p>${e(state.loadError)}</p><button class="kb-btn kb-btn-secondary" data-kb-retry>重新加载</button></div>`;
    if (!state.loaded) return '<div class="kb-empty" role="status">正在加载知识库…</div>';
    const list = results();
    if (!list.length) return `<div class="kb-empty">${ic('library',36)}<strong>${snapshot().items.length ? '没有找到相关资料' : '还没有公司资料'}</strong><p>${snapshot().items.length ? '换个关键词或分类试试。' : '通过右上角上传文件或添加在线文档，并选择所属分类。'}</p></div>`;
    return `<div class="kb-table-wrap"><table class="kb-table"><thead><tr><th scope="col">资料名称</th><th scope="col">分类</th><th scope="col">格式</th><th scope="col">添加人</th><th scope="col">更新时间</th><th scope="col">操作</th></tr></thead><tbody>${list.map(item => `<tr><td><div class="kb-file-cell"><span class="kb-file-icon kb-file-${fileKind(item)}">${ic(item.kind === 'link' ? 'link' : fileKind(item) === 'image' ? 'image' : 'file',21)}</span><div><button type="button" class="kb-title" data-kb-view="${e(item.id)}" title="${e(item.title)}">${e(item.title)}</button><span class="kb-row-note" title="${e(item.description || item.fileName || item.url)}">${e(item.description || (item.kind === 'link' ? item.url : item.fileName))}</span></div></div></td><td><span class="kb-category-label">${e(categoryName(item.categoryId))}</span></td><td>${e(fileLabel(item))}<small>${item.kind === 'file' ? bytes(item.size) : '外部链接'}</small></td><td>${e(item.createdBy?.name || '管理员')}</td><td>${date(item.updatedAt)}</td><td><div class="kb-row-actions"><button type="button" data-kb-view="${e(item.id)}">查看</button><button type="button" data-kb-edit="${e(item.id)}">编辑</button><button type="button" data-kb-delete="${e(item.id)}">删除</button></div></td></tr>`).join('')}</tbody></table><div class="kb-table-total">共 ${list.length} 份资料</div></div>`;
  }
  function render() {
    if (!knowledge.isAdmin()) return '<section class="knowledge-page"><div class="kb-empty">仅管理员可管理知识库。</div></section>';
    const data = snapshot();
    return `<section class="knowledge-page"><header class="kb-heading"><h1>知识库管理</h1><div class="kb-actions"><button type="button" class="kb-btn kb-btn-secondary" data-kb-add-link ${!state.loaded?'disabled':''}>${ic('link')} 添加在线文档</button><button type="button" class="kb-btn kb-btn-primary" data-kb-upload ${!state.loaded?'disabled':''}>${ic('upload')} 上传文件</button></div></header><div class="kb-category-bar"><div class="kb-categories" aria-label="资料分类">${[{id:'all',name:'全部资料'},...data.categories].map(category => `<button type="button" class="${state.category === category.id ? 'active' : ''}" data-kb-category="${e(category.id)}" aria-pressed="${state.category === category.id}">${e(category.name)}<span>${category.id === 'all' ? data.items.length : data.items.filter(item => item.categoryId === category.id).length}</span></button>`).join('')}</div><button class="kb-manage-categories" type="button" data-kb-manage ${!state.loaded?'disabled':''}>${ic('edit',15)} 分类管理</button></div><div class="kb-toolbar"><label class="kb-search">${ic('search')}<input type="search" data-kb-search value="${e(state.query)}" placeholder="搜索资料名称、说明或添加人" aria-label="搜索知识库"></label><select data-kb-type aria-label="按资料格式筛选">${types.map(([id,label])=>`<option value="${id}" ${state.type===id?'selected':''}>${label}</option>`).join('')}</select></div><div data-kb-results>${table()}</div><p class="kb-storage-note">资料已接入公司知识库，由管理员共同维护。</p></section>`;
  }
  function load() {
    if (state.loading || state.loaded || !knowledge.isAdmin()) return;
    state.loading = true;
    const token = generation;
    knowledge.ready().then(() => {
      if (token !== generation) return;
      state.loaded = true; state.loadError = '';
    }).catch(error => { if (token === generation) state.loadError = errorText(error); })
      .finally(() => { if (token === generation) { state.loading = false; changed(); } });
  }
  function bind(root) {
    active = true;
    if (!knowledge.isAdmin()) return;
    if (!state.loaded && !state.loadError) load();
    const paintResults = () => { const target = root.querySelector('[data-kb-results]'); if (target) target.innerHTML = table(); };
    root.querySelector('[data-kb-search]')?.addEventListener('input', event => { state.query = event.target.value; paintResults(); });
    root.querySelector('[data-kb-type]')?.addEventListener('change', event => { state.type = event.target.value; paintResults(); });
    root.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button || !root.contains(button) || button.disabled) return;
      if (button.hasAttribute('data-kb-upload')) uploadForm();
      else if (button.hasAttribute('data-kb-add-link')) itemForm();
      else if (button.hasAttribute('data-kb-manage')) categoryManager();
      else if (button.hasAttribute('data-kb-category')) { state.category = button.dataset.kbCategory; changed(); }
      else if (button.hasAttribute('data-kb-retry')) { state.loadError = ''; load(); paintResults(); }
      else if (button.dataset.kbView) showItem(itemById(button.dataset.kbView));
      else if (button.dataset.kbEdit) itemForm(itemById(button.dataset.kbEdit));
      else if (button.dataset.kbDelete) removeItem(itemById(button.dataset.kbDelete));
    });
  }
  function modal(title, body, ready, wide = false) {
    if (!guard()) return;
    ui.openModal(`<div class="kb-modal-heading"><h2>${e(title)}</h2></div>${body}`, node => {
      node.classList.add('kb-modal'); if (wide) node.classList.add('kb-modal-wide');
      node.querySelectorAll('[data-kb-cancel]').forEach(button => button.onclick = () => ui.closeModal());
      ready?.(node);
    });
  }
  const formError = (node, message) => { const target = node.querySelector('[data-kb-error]'); if (target) target.textContent = message; };
  async function perform(node, operation, success, after) {
    if (node.dataset.kbBusy === 'true' || !guard()) return;
    formError(node, ''); node.dataset.kbBusy = 'true';node.dataset.operationPending='true';
    const controls = [...node.querySelectorAll('button,input,select,textarea')].map(control => [control,control.disabled]);
    controls.forEach(([control]) => { control.disabled = true; });
    try {
      await operation();delete node.dataset.operationPending;
      if (node.isConnected) { if (after) after(); else ui.closeModal(); }
      changed(); if (success) ui.toast(success);
    } catch (error) { if (node.isConnected) formError(node,errorText(error)); else ui.toast(errorText(error),'error'); }
    finally { node.dataset.kbBusy = 'false';delete node.dataset.operationPending; controls.forEach(([control,disabled]) => { control.disabled = disabled; }); }
  }
  function uploadForm() {
    let files = [];
    modal('上传文件', `<form class="kb-form" data-kb-upload-form><div class="kb-dropzone" data-kb-drop>${ic('upload',30)}<strong>拖动文件到这里</strong><span>PPT、Word、PDF、表格、图片等文件</span><button type="button" class="kb-btn kb-btn-secondary" data-kb-choose>选择文件</button><input type="file" multiple data-kb-file hidden><small>单文件最多 100 MB，每次最多 20 个</small></div><div class="kb-upload-list" data-kb-file-list aria-live="polite"></div><label class="kb-field"><span>资料分类</span><select name="categoryId">${categoryOptions(defaultCategory())}</select></label><label class="kb-field"><span>资料说明 <small>选填</small></span><textarea name="description" rows="3" maxlength="1000" placeholder="介绍这批资料的内容或使用场景"></textarea></label><p class="kb-error" data-kb-error role="alert"></p><footer class="kb-form-actions"><button type="button" class="kb-btn kb-btn-secondary" data-kb-cancel>取消</button><button type="submit" class="kb-btn kb-btn-primary">保存资料</button></footer></form>`, node => {
      const fileInput = node.querySelector('[data-kb-file]'), list = node.querySelector('[data-kb-file-list]'), drop = node.querySelector('[data-kb-drop]');
      const paint = () => { list.innerHTML = files.map((file,index)=>`<div><span>${ic('file')}<strong>${e(file.name)}</strong><small>${bytes(file.size)}</small></span><button type="button" class="kb-icon-button" data-kb-remove-file="${index}" aria-label="移除 ${e(file.name)}">${ic('close')}</button></div>`).join(''); };
      const addFiles = incoming => {
        const next = [...files];
        for (const file of incoming) if (!next.some(other => other.name === file.name && other.size === file.size && other.lastModified === file.lastModified)) next.push(file);
        if (next.length > 20) { formError(node,'每次最多上传 20 个文件，请分批添加'); return; }
        const tooLarge = next.find(file=>file.size > 100*1024*1024);
        if (tooLarge) { formError(node,`「${tooLarge.name}」超过 100 MB，请缩小文件后重试`); return; }
        files = next; formError(node,''); paint();
      };
      node.querySelector('[data-kb-choose]').onclick = () => fileInput.click();
      fileInput.onchange = () => { addFiles([...fileInput.files]); fileInput.value = ''; };
      drop.ondragover = event => { event.preventDefault(); if (node.dataset.kbBusy !== 'true') drop.classList.add('dragging'); };
      drop.ondragleave = () => drop.classList.remove('dragging');
      drop.ondrop = event => { event.preventDefault(); drop.classList.remove('dragging'); if (node.dataset.kbBusy !== 'true') addFiles([...event.dataTransfer.files]); };
      list.onclick = event => { const button=event.target.closest('[data-kb-remove-file]'); if (button && node.dataset.kbBusy !== 'true') { files.splice(Number(button.dataset.kbRemoveFile),1); paint(); } };
      node.querySelector('form').onsubmit = event => {
        event.preventDefault(); if (!files.length) { formError(node,'请先选择至少一个文件'); return; }
        const values = new FormData(event.currentTarget);
        perform(node, () => knowledge.uploadFiles(files,{categoryId:values.get('categoryId'),description:values.get('description')}),`已添加 ${files.length} 份资料`);
      };
    });
  }
  function itemForm(item = null) {
    const isLink = !item || item.kind === 'link';
    modal(item ? '编辑资料' : '添加在线文档', `<form class="kb-form"><label class="kb-field"><span>资料名称 <i>*</i></span><input name="title" required maxlength="120" value="${e(item?.title || '')}" placeholder="填写资料名称"></label>${isLink ? `<label class="kb-field"><span>文档链接 <i>*</i></span><input name="url" type="url" required value="${e(item?.url || '')}" placeholder="https://"><small>支持飞书、在线文档和其他网页链接。</small></label>` : `<div class="kb-file-summary">${ic('file',22)}<span>${e(item.fileName)}<small>${bytes(item.size)}</small></span></div>`}<label class="kb-field"><span>资料分类</span><select name="categoryId">${categoryOptions(item?.categoryId || defaultCategory())}</select></label><label class="kb-field"><span>资料说明 <small>选填</small></span><textarea name="description" maxlength="1000" rows="3" placeholder="介绍资料内容或适用场景">${e(item?.description || '')}</textarea></label><p class="kb-error" data-kb-error role="alert"></p><footer class="kb-form-actions"><button type="button" class="kb-btn kb-btn-secondary" data-kb-cancel>取消</button><button type="submit" class="kb-btn kb-btn-primary">${item ? '保存修改' : '添加文档'}</button></footer></form>`, node => {
      node.querySelector('form').onsubmit = event => {
        event.preventDefault(); const fields=Object.fromEntries(new FormData(event.currentTarget));
        if (!fields.title.trim()) { formError(node,'请填写资料名称'); return; }
        if (isLink) { const result=validateKnowledgeUrl(fields.url.trim()); if (!result.valid) { formError(node,result.message); return; } fields.url=result.url; }
        perform(node,()=>item ? knowledge.updateItem(item.id,fields) : knowledge.saveLink(fields),item?'资料已更新':'在线文档已添加');
      };
    });
  }
  function removeItem(item) {
    if (!item) return;
    modal('删除资料', `<p class="kb-confirm-copy">确定删除「${e(item.title)}」？${item.kind === 'file' ? '知识库中的原文件也会删除。' : '原始在线文档不会受到影响。'}</p><p class="kb-error" data-kb-error role="alert"></p><footer class="kb-form-actions"><button type="button" class="kb-btn kb-btn-secondary" data-kb-cancel>取消</button><button type="button" class="kb-btn kb-btn-danger" data-kb-confirm-delete>删除资料</button></footer>`, node => {
      node.querySelector('[data-kb-confirm-delete]').onclick=()=>perform(node,()=>knowledge.removeItem(item.id),'资料已删除');
    });
  }
  function categoryManager() {
    const data=snapshot();
    modal('分类管理', `<form class="kb-category-create"><label class="kb-field"><span>新增分类</span><input name="name" maxlength="30" required placeholder="例如：员工手册"></label><button type="submit" class="kb-btn kb-btn-primary">${ic('plus')} 添加分类</button></form><div class="kb-category-list">${data.categories.map(category => `<div class="kb-category-row"><label class="kb-field"><span>${data.items.filter(item=>item.categoryId===category.id).length} 份资料${category.id==='uncategorized'?' · 默认分类':''}</span><input maxlength="30" value="${e(category.name)}" data-kb-category-name="${e(category.id)}" aria-label="分类名称" ${category.id==='uncategorized'?'disabled':''}></label>${category.id==='uncategorized'?'<span class="kb-muted">不可删除</span>':`<button type="button" class="kb-btn kb-btn-secondary" data-kb-category-save="${e(category.id)}">保存</button><button type="button" class="kb-icon-button" data-kb-category-delete="${e(category.id)}" aria-label="删除 ${e(category.name)}">${ic('trash')}</button>`}</div>`).join('')}</div><p class="kb-error" data-kb-error role="alert"></p><p class="kb-modal-note">删除分类后，原有资料会移入「未分类」。</p>`, node => {
      node.querySelector('form').onsubmit=event=>{ event.preventDefault(); const name=new FormData(event.currentTarget).get('name'); perform(node,()=>knowledge.saveCategory({name}),'分类已添加',categoryManager); };
      node.querySelectorAll('[data-kb-category-save]').forEach(button=>button.onclick=()=>{ const id=button.dataset.kbCategorySave; const input=[...node.querySelectorAll('[data-kb-category-name]')].find(input=>input.dataset.kbCategoryName===id); perform(node,()=>knowledge.saveCategory({id,name:input.value}),'分类已更新',categoryManager); });
      node.querySelectorAll('[data-kb-category-delete]').forEach(button=>button.onclick=()=>categoryDelete(data.categories.find(category=>category.id===button.dataset.kbCategoryDelete)));
    });
  }
  function categoryDelete(category) {
    if (!category) return;
    const count=snapshot().items.filter(item=>item.categoryId===category.id).length;
    modal('删除分类', `<p class="kb-confirm-copy">删除「${e(category.name)}」后，${count ? `其中 ${count} 份资料将移入「未分类」，文件会保留。` : '其他分类和资料保持不变。'}</p><p class="kb-error" data-kb-error role="alert"></p><footer class="kb-form-actions"><button type="button" class="kb-btn kb-btn-secondary" data-kb-back-categories>返回</button><button type="button" class="kb-btn kb-btn-danger" data-kb-confirm-category>删除分类</button></footer>`, node=>{
      node.querySelector('[data-kb-back-categories]').onclick=categoryManager;
      node.querySelector('[data-kb-confirm-category]').onclick=()=>perform(node,async()=>{ await knowledge.removeCategory(category.id); if(state.category===category.id)state.category='all'; },'分类已删除，资料已保留',categoryManager);
    });
  }
  function trackPreview(node, url) {
    const observer = new MutationObserver(()=>{ if (!node.isConnected) cleanup(); });
    const cleanup=()=>{ observer.disconnect(); URL.revokeObjectURL(url); previewCleanups.delete(cleanup); };
    observer.observe(document.getElementById('modal-root'),{childList:true,subtree:true});
    previewCleanups.add(cleanup);
  }
  async function download(item, button) {
    if (!guard() || button?.disabled) return;
    if(button)button.disabled=true;
    try {
      const blob=await knowledge.getFile(item.id);
      const url=URL.createObjectURL(blob), link=document.createElement('a');
      link.href=url; link.download=item.fileName || item.title; link.style.display='none'; document.body.append(link); link.click(); link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),30000);
    } catch(error) { ui.toast(errorText(error),'error'); }
    finally { if(button)button.disabled=false; }
  }
  function showItem(item) {
    if (!item) return;
    const validated=item.kind==='link'?validateKnowledgeUrl(item.url):null;
    modal(item.title, `<div class="kb-detail-meta"><span>${e(categoryName(item.categoryId))}</span><span>${e(fileLabel(item))}${item.kind==='file'?' · '+bytes(item.size):''}</span><span>${e(item.createdBy?.name || '管理员')} · ${date(item.updatedAt)}</span></div>${item.description?`<p class="kb-detail-description">${e(item.description)}</p>`:''}${item.kind==='link'?`<div class="kb-link-preview">${ic('link',30)}<p>${e(item.url)}</p>${validated.valid?`<a class="kb-btn kb-btn-primary" href="${e(validated.url)}" target="_blank" rel="noopener noreferrer">${ic('external')} 打开在线文档</a><small>文档访问权限由原平台控制。</small>`:'<p class="kb-error">链接格式无效，请编辑后重试。</p>'}</div>`:`<div class="kb-preview-content" data-kb-preview-content role="status">正在读取文件…</div><p class="kb-error" data-kb-error role="alert"></p><footer class="kb-form-actions"><button type="button" class="kb-btn kb-btn-primary" data-kb-download>${ic('download')} 下载原文件</button></footer>`}`,node=>{
      if(item.kind==='link')return;
      node.querySelector('[data-kb-download]').onclick=event=>download(item,event.currentTarget);
      const target=node.querySelector('[data-kb-preview-content]');
      knowledge.getFile(item.id).then(async blob=>{
        if(!node.isConnected)return;
        const name=(item.fileName||'').toLowerCase();
        if(/\.(png|jpe?g|gif|webp|avif|bmp)$/.test(name)) {
          const url=URL.createObjectURL(blob); trackPreview(node,url);
          const img=document.createElement('img'); img.src=url; img.alt=item.title; img.onerror=()=>{target.textContent='图片无法预览，请下载原文件查看。';}; target.replaceChildren(img);
        } else if(/\.pdf$/.test(name)) {
          const url=URL.createObjectURL(new Blob([blob],{type:'application/pdf'})); trackPreview(node,url);
          const frame=document.createElement('iframe'); frame.src=url; frame.title=item.title; frame.setAttribute('sandbox','');
          const hint=document.createElement('p'); hint.className='kb-modal-note'; hint.textContent='若浏览器未显示 PDF，请下载原文件查看。'; target.replaceChildren(frame,hint);
        } else if(/\.(txt|md|csv|log|json)$/.test(name) && blob.size<=1024*1024) {
          const text=await blob.text(); if(!node.isConnected)return; const pre=document.createElement('pre'); pre.textContent=text.slice(0,200000)+(text.length>200000?'\n\n…内容较长，请下载完整文件。':''); target.replaceChildren(pre);
        } else {
          target.innerHTML=`<div class="kb-download-preview">${ic('file',40)}<strong>${e(item.fileName)}</strong><p>该格式暂不支持页面内预览，请下载原文件查看。</p></div>`;
        }
      }).catch(error=>{if(node.isConnected){target.textContent='文件暂时无法读取';formError(node,errorText(error));}});
    },true);
  }
  function deactivate() { active=false; for(const cleanup of [...previewCleanups])cleanup(); }
  function reset() { deactivate(); generation++; Object.assign(state,{loaded:false,loading:false,loadError:'',query:'',category:'all',type:'all'}); }
  return { render, bind, reset, deactivate };
}
