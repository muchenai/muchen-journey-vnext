import {escapeHtml as e} from './core.js?v=20261029-reward-types';
import {openBulkAccess} from './member-bulk.js';
const domains = ['产品开发','数据交付','技术开发','PMO','AI评测','质量检测','项目管理','AI 能力'];
const levels = ['初级','中级','高级'];
const options = (values, selected) => values.map(v=>`<option ${v===selected?'selected':''}>${e(v)}</option>`).join('');
const allowed = level => ({'初级':'入门','中级':'入门、进阶','高级':'入门、进阶、挑战'})[level] || '入门';
export const grantRoleOptions = canGrantSuperAdmins => '<option value="admin">普通管理员</option>' + (canGrantSuperAdmins ? '<option value="super_admin">超级管理员</option>' : '');
const rootOf = modal => modal?.querySelector ? modal : document;
const check = ui => { if (ui.isSuperAdmin) return true; ui.toast('仅超级管理员可以管理成员权限','error'); return false; };

export function filterAdministrators(members, query) {
  const key=query.trim().toLocaleLowerCase();
  return members.filter(m=>!key || [m.name,m.employee_no].some(value=>String(value||'').toLocaleLowerCase().includes(key)));
}

export function memberRows(members) {
  if (!members.length) return '<div class="empty-state"><strong>暂无管理员</strong></div>';
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>成员</th><th>方向</th><th>认证等级</th><th>状态</th><th>操作</th></tr></thead><tbody>${members.map(m=>`<tr><td class="admin-member-details"><strong>${e(m.name)}</strong><div class="table-subtitle">工号：${e(m.employee_no||'未填写')}</div><div class="table-subtitle">部门：${e((m.department_paths?.length?m.department_paths:m.departments)?.join('；')||'未填写')}</div><div class="table-subtitle">${m.accessRole==='super_admin'?'超级管理员':'普通管理员'}</div></td><td>${e(m.certification?.domain||'产品开发')}</td><td>${m.accessRole==='super_admin'?'全部难度':`${e(m.certification?.level||'初级')}<div class="table-subtitle">可发布${allowed(m.certification?.level)}</div>`}</td><td><span class="tag ${m.status==='revoked'?'tag-neutral':'tag-success'}">${m.status==='revoked'?'已撤销':'已开通'}</span></td><td>${m.accessRole==='super_admin'?'—':m.status==='revoked'?`<button class="text-btn" data-member-restore="${e(m.id)}">重新授权</button>`:`<button class="text-btn" data-member-edit="${e(m.id)}">修改等级</button><button class="text-btn member-revoke" data-member-revoke="${e(m.id)}">撤销管理权限</button>`}</td></tr>`).join('')}</tbody></table></div>`;
}

export function directoryStatusText(info) {
  if (!info) return '正在读取通讯录状态…';
  if (!info.ready) return info.error_code ? '通讯录首次同步失败，请刷新重试。' : '正在准备公司通讯录，完成后即可搜索。';
  const stamp=new Date(info.last_updated_at);
  const updated=Number.isNaN(stamp.getTime())?'未知':stamp.toLocaleString('zh-CN',{hour12:false});
  const suffix=info.syncing?'正在后台更新，可继续搜索':info.error_code==='DIRECTORY_PERMISSION_REQUIRED'?'通讯录权限已变化，请核实后刷新':info.error_code?'上次更新失败，暂用已有名单，稍后自动重试':'每天凌晨 3 点自动更新（北京时间）';
  return `通讯录更新于 ${updated} · ${suffix}`;
}

function memberDetails(member) {
  const departments=member.department_paths?.length?member.department_paths:member.departments;
  return `<strong>${e(member.name)}</strong><small>工号：${e(member.employee_no||'未填写')}</small><small>职务：${e(member.job_title||'未填写')}</small><small>部门：${e(departments?.join('；')||'未填写')}</small>`;
}

export function searchRows(items) {
  if (!items.length) return '<p class="muted">没有找到匹配的公司成员，请检查姓名、工号或通讯录可见范围。</p>';
  return items.map((m,i)=>`<button type="button" class="member-choice" data-member-choice="${i}">${m.avatar?.startsWith('https://')?`<img src="${e(m.avatar)}" alt="" width="32" height="32" referrerpolicy="no-referrer">`:'<span class="avatar avatar-small">'+e(m.name.slice(0,1))+'</span>'}<span class="member-identity">${memberDetails(m)}</span></button>`).join('');
}

export function openCertification(store, ui, initialName='') {
  if (!check(ui)) return;
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">MEMBER CERTIFICATION</div><h2>认证</h2></div></div><div class="modal-body"><div class="inline-note certification-note">${ui.canGrantSuperAdmins ? '搜索公司飞书成员，可授予普通管理员或超级管理员身份。新添加的超级管理员只能授权普通管理员。' : '搜索公司飞书成员，选择账号后开通普通管理员权限。认证等级决定可发布的任务难度。'}</div><section class="certification-section"><h3>添加成员</h3><form id="member-access-form" class="certification-form"><div class="form-grid"><label class="form-field"><span class="field-label">成员姓名或工号 <span class="required">*</span></span><input name="name" maxlength="60" autocomplete="off" required placeholder="输入姓名或工号搜索公司飞书成员" value="${e(initialName)}"></label><label class="form-field"><span class="field-label">身份类型</span><select name="access_role">${grantRoleOptions(ui.canGrantSuperAdmins === true)}</select></label></div><div class="directory-toolbar"><span class="muted" data-directory-status role="status">正在读取通讯录状态…</span><button type="button" class="text-btn" data-directory-refresh>刷新通讯录</button></div><div class="member-search-results" data-member-results aria-live="polite"></div><div class="member-selected" data-member-selected hidden></div><div class="form-grid"><label class="form-field"><span class="field-label">专业方向</span><select name="domain">${options(domains,'产品开发')}</select></label><label class="form-field"><span class="field-label">认证等级</span><select name="level">${options(levels,'初级')}</select><span class="field-hint" data-level-hint>初级：入门；中级：入门、进阶；高级：全部难度</span></label></div><div class="cert-form-footer"><span class="muted">确认后即可使用该飞书账号登录</span><button class="btn btn-primary" type="submit" disabled>添加成员</button></div><div class="field-error" data-member-error role="alert"></div></form></section><section class="certification-section member-list-section"><h3>管理员 <span class="count-pill">${(store.administrators||[]).length}</span></h3><div class="member-list-toolbar"><label class="member-list-search"><span class="field-label">搜索管理员</span><input type="search" data-admin-search placeholder="输入管理员姓名或工号" autocomplete="off" value="${e(ui.memberSearchQuery||'')}"></label><span class="muted" data-admin-count role="status" aria-live="polite"></span></div><div class="member-list-scroll" data-admin-list role="region" aria-label="管理员列表" tabindex="0"></div></section></div><div class="modal-footer"><button class="btn btn-secondary" data-close-modal>关闭</button></div>`, modal=>{
    const root=rootOf(modal), form=root.querySelector('#member-access-form'), input=form.elements.name;
    const results=root.querySelector('[data-member-results]'), selectedBox=root.querySelector('[data-member-selected]'), error=root.querySelector('[data-member-error]'), submit=form.querySelector('[type=submit]');
    let selected=null, sequence=0, timer, composing=false, lastUpdated=null, pollTimer, pollSequence=0;
    const directoryStatus=root.querySelector('[data-directory-status]'), refreshDirectory=root.querySelector('[data-directory-refresh]');
    function showDirectoryStatus(info) {
      directoryStatus.textContent=directoryStatusText(info);
      refreshDirectory.disabled=!!info.syncing;
    }
    async function pollDirectory() {
      if (!root.isConnected || !ui.service.certifications.directoryStatus) return;
      clearTimeout(pollTimer);
      const pollId=++pollSequence;
      let delay=30000;
      try {
        const info=await ui.service.certifications.directoryStatus();
        if (!root.isConnected || pollId!==pollSequence) return;
        showDirectoryStatus(info);
        if (info.last_updated_at && info.last_updated_at!==lastUpdated) {
          const previouslyLoaded=lastUpdated!==null;
          lastUpdated=info.last_updated_at;
          if (previouslyLoaded && input.value.trim() && !selected) void search();
        } else if (!info.ready) lastUpdated='';
        if (info.syncing || !info.ready) delay=5000;
      } catch {directoryStatus.textContent='通讯录状态读取失败，可点击刷新重试。';}
      if(root.isConnected && pollId===pollSequence) pollTimer=setTimeout(pollDirectory,delay);
    }
    refreshDirectory.onclick=async()=>{
      refreshDirectory.disabled=true;
      ++pollSequence;clearTimeout(pollTimer);
      try {
        const info=await ui.service.certifications.refreshDirectory();
        if(!root.isConnected)return;
        showDirectoryStatus(info);
        if(info.retry_after_seconds) ui.toast(`请在 ${info.retry_after_seconds} 秒后再次刷新。`);
        else ui.toast('已请求更新通讯录，期间可继续搜索已有名单。');
        pollTimer=setTimeout(()=>{if(root.isConnected)void pollDirectory();},2000);
      } catch(err){directoryStatus.textContent=err.message;refreshDirectory.disabled=false;}
    };
    void pollDirectory();
    form.elements.access_role.addEventListener('change',()=>{
      const isSuper=form.elements.access_role.value==='super_admin';
      form.elements.level.disabled=isSuper;
      form.elements.level.value=isSuper?'高级':'初级';
      root.querySelector('[data-level-hint]').textContent=isSuper?'超级管理员可发布全部难度的任务':'初级：入门；中级：入门、进阶；高级：全部难度';
    });
    async function search() {
      const current=++sequence, query=input.value.trim();
      selected=null; selectedBox.hidden=true; submit.disabled=true; error.textContent='';
      results.innerHTML=query?'<p class="muted">正在搜索公司成员…</p>':'';
      if (!query) return;
      try {
        const value=await ui.service.certifications.search(query);
        if (current!==sequence || !root.isConnected) return;
        if(value.directory) {
          showDirectoryStatus(value.directory);
          if(!value.directory.ready) {results.innerHTML='<p class="muted">公司通讯录正在准备中，请稍候。</p>';return;}
        }
        results.innerHTML=searchRows(value.items)+(value.has_more?'<p class="muted">结果较多，请输入更完整的姓名或工号。</p>':'');
        results.querySelectorAll('[data-member-choice]').forEach(button=>button.onclick=()=>{
          selected=value.items[Number(button.dataset.memberChoice)]; input.value=selected.name;
          selectedBox.innerHTML=`<span class="muted">已选择成员</span><div class="member-identity">${memberDetails(selected)}</div>`;
          selectedBox.hidden=false; results.innerHTML=''; submit.disabled=false;
        });
      } catch(err) { if (current===sequence) { results.innerHTML=''; error.textContent=err.message; } }
    }
    function scheduleSearch(){++sequence;clearTimeout(timer);selected=null;submit.disabled=true;selectedBox.hidden=true;results.innerHTML='';if(!composing)timer=setTimeout(search,200);}
    input.addEventListener('compositionstart',()=>{composing=true;scheduleSearch();});
    input.addEventListener('compositionend',()=>{composing=false;scheduleSearch();});
    input.addEventListener('input',scheduleSearch);
    if(initialName) void search();
    form.addEventListener('submit',async event=>{
      event.preventDefault(); if(!check(ui))return;
      if(!selected){error.textContent='请从搜索结果中选择具体的公司飞书账号。';return;}
      const payload={open_id:selected.open_id,expected_revision:selected.revision,domain:form.elements.domain.value,level:form.elements.level.value,access_role:form.elements.access_role.value};
      modal.dataset.operationPending='true'; submit.disabled=true;
      try {await ui.service.certifications.grant(payload);modal.dataset.operationPending='false';ui.toast(payload.access_role==='super_admin'?'超级管理员权限已开通':'普通管理员权限已开通');openCertification(store,ui);}
      catch(err){error.textContent=err.message;}
      finally{modal.dataset.operationPending='false';submit.disabled=false;}
    });
    root.querySelector('[data-close-modal]').onclick=ui.closeModal;
    const bulkButton=document.createElement('button');
    bulkButton.type='button';bulkButton.className='btn btn-secondary member-bulk-entry';
    bulkButton.textContent='按部门和职位批量授权';
    const actions=document.createElement('div');
    actions.className='member-form-actions';
    submit.before(actions);
    actions.append(bulkButton,submit);
    bulkButton.onclick=()=>openBulkAccess(store,ui,()=>openCertification(store,ui));
    const adminSearch=root.querySelector('[data-admin-search]'), adminList=root.querySelector('[data-admin-list]'), adminCount=root.querySelector('[data-admin-count]');
    function renderAdministrators(){
      const all=store.administrators||[], query=adminSearch.value.trim().toLocaleLowerCase();
      ui.memberSearchQuery=adminSearch.value;
      const matches=filterAdministrators(all,query);
      adminCount.textContent=query?`找到 ${matches.length} 人 / 共 ${all.length} 人`:`共 ${all.length} 人`;
      adminList.innerHTML=matches.length?memberRows(matches):`<div class="empty-state"><strong>${query?'没有找到匹配的管理员':'暂无管理员'}</strong>${query?'<p>请更换姓名或工号关键词，或清空搜索查看全部管理员。</p>':''}</div>`;
      adminList.scrollTop=0;
    }
    adminSearch.addEventListener('input',renderAdministrators);
    adminList.addEventListener('click',event=>{
      const button=event.target.closest('button');
      if(!button || !adminList.contains(button))return;
      if(button.dataset.memberEdit)editMember(store,ui,button.dataset.memberEdit);
      else if(button.dataset.memberRevoke)revokeMember(store,ui,button.dataset.memberRevoke);
      else if(button.dataset.memberRestore)openCertification(store,ui,store.administrators.find(m=>m.id===button.dataset.memberRestore)?.name||'');
    });
    renderAdministrators();
  });
}

function editMember(store,ui,id){
  if(!check(ui))return; const m=store.administrators.find(x=>x.id===id);if(!m||m.accessRole==='super_admin')return;
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">${e(m.name)} · 普通管理员</div><h2>修改认证等级</h2></div></div><form data-member-edit-form><div class="modal-body"><label class="form-field"><span class="field-label">专业方向</span><select name="domain">${options(domains,m.certification?.domain)}</select></label><label class="form-field"><span class="field-label">认证等级</span><select name="level">${options(levels,m.certification?.level)}</select></label><p class="muted">保存后立即按新等级限制发布，已发布的任务保留。</p><p class="field-error" role="alert"></p></div><div class="modal-footer"><button class="btn btn-secondary" type="button" data-back>返回</button><button class="btn btn-primary" type="submit">保存修改</button></div></form>`,modal=>{
    const form=modal.querySelector('form');modal.querySelector('[data-back]').onclick=()=>openCertification(store,ui);
    form.onsubmit=async event=>{event.preventDefault();modal.dataset.operationPending='true';const button=form.querySelector('[type=submit]');button.disabled=true;
      try{await ui.service.certifications.update(m,form.elements.domain.value,form.elements.level.value);modal.dataset.operationPending='false';ui.toast('认证等级已更新');openCertification(store,ui);}
      catch(err){form.querySelector('[role=alert]').textContent=err.message;}finally{modal.dataset.operationPending='false';button.disabled=false;}};
  });
}

function revokeMember(store,ui,id){
  if(!check(ui))return;const m=store.administrators.find(x=>x.id===id);if(!m||m.accessRole==='super_admin')return;
  ui.openModal(`<div class="modal-header"><h2>撤销管理权限</h2></div><div class="modal-body"><p>确认撤销 <strong>${e(m.name)}</strong>（${e(m.id.slice(-8))}）的管理权限？</p><p class="muted">确认后不能再进入管理系统，已有管理端会话立即失效。已发布任务、审核记录和学员端学习记录均保留。</p><p class="field-error" role="alert"></p></div><div class="modal-footer"><button class="btn btn-secondary" data-back>取消</button><button class="btn btn-primary" data-confirm-revoke>确认撤销</button></div>`,modal=>{
    modal.querySelector('[data-back]').onclick=()=>openCertification(store,ui);
    const button=modal.querySelector('[data-confirm-revoke]');button.onclick=async()=>{button.disabled=true;modal.dataset.operationPending='true';
      try{await ui.service.certifications.revoke(m);modal.dataset.operationPending='false';ui.toast('管理权限已撤销');openCertification(store,ui);}
      catch(err){modal.querySelector('[role=alert]').textContent=err.message;}finally{button.disabled=false;modal.dataset.operationPending='false';}};
  });
}
