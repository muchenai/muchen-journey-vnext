import {escapeHtml as e} from './core.js?v=20261028-publication-local';

const domains=['产品开发','数据交付','技术开发','PMO','AI评测','质量检测','项目管理','AI 能力'];
const statusName={conflict:'需要确认',new:'待新增',super:'超级管理员',existing:'已有管理员',revoked:'已撤销',unavailable:'不可授权',missing_title:'职位未填写',not_matched:'职位不符合',created:'已新增',skipped:'已跳过',failed:'失败',unknown:'待核实'};

const levels=['初级','中级','高级'];
const departmentOrder=['总经办','PMO经营治理办公室','客户增长与战略解决方案部','AI平台与数据治理中心','人才与专家网络中心','财务法务合规部','行政与职场运营部','AI数据交付中心','品牌策划与内容传播部'];
export function departmentRows(items){
  const rank=d=>{const i=departmentOrder.indexOf(d.name.replace(/\s/g,''));return i<0?departmentOrder.length:i;};
  const roots=items.filter(d=>d.parent_id==='0').sort((a,b)=>rank(a)-rank(b));
  return roots.map(d=>`<div class="bulk-rule-row" data-bulk-rule><strong>${e(d.name)}</strong><label><span class="field-label">人员范围</span><select aria-label="${e(d.name)}授权范围" data-bulk-department="${e(d.id)}"><option value="off" ${d.default_mode==='off'?'selected':''}>不授权</option><option value="all" ${d.default_mode==='all'?'selected':''}>全体员工</option><option value="title" ${d.default_mode==='title'?'selected':''}>职位含经理或助理</option></select></label><label><span class="field-label">专业方向</span><select aria-label="${e(d.name)}专业方向" data-bulk-domain>${domains.map(v=>`<option>${e(v)}</option>`).join('')}</select></label><label><span class="field-label">认证等级</span><select aria-label="${e(d.name)}认证等级" data-bulk-level>${levels.map(v=>`<option>${e(v)}</option>`).join('')}</select></label></div>`).join('');
}
export function resolveBulkChoice(person,departmentId){
  if(!['new','conflict'].includes(person.status)||person.options?.length<2)return false;
  person.target=person.options.find(o=>o.department_id===departmentId)||null;
  person.status=person.target?'new':'conflict';
  person.action=person.target?`新增普通管理员 · ${person.target.domain} · ${person.target.level}`:'跨部门配置不同，请选择';
  return !!person.target;
}
function choiceControl(p,busy){
  if(!['new','conflict'].includes(p.status)||!(p.options?.length>1))return '';
  return `<select class="bulk-conflict-choice" data-bulk-choice="${e(p.open_id)}" aria-label="${e(p.name)}跨部门授权配置" ${busy?'disabled':''}><option value="">请选择方向和等级</option>${p.options.map(o=>`<option value="${e(o.department_id)}" ${p.target?.department_id===o.department_id?'selected':''}>${e(o.department_name)} · ${e(o.domain)} · ${e(o.level)}</option>`).join('')}</select>`;
}

export const filterBulkPeople=(people,query)=>{
  const key=query.trim().toLocaleLowerCase();
  return people.filter(p=>!key || [p.name,p.employee_no,p.job_title,...(p.departments||[]),...(p.department_paths||[])].some(value=>String(value||'').toLocaleLowerCase().includes(key)));
};
export function bulkRows(people,selected,busy=false){
  if(!people.length)return '<div class="empty-state">没有匹配的人员，请调整搜索条件。</div>';
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>选择</th><th>员工 / 部门</th><th>职位</th><th>当前权限</th><th>本次处理</th></tr></thead><tbody>${people.map(p=>`<tr><td>${p.status==='new'?`<input type="checkbox" data-bulk-person="${e(p.open_id)}" aria-label="选择 ${e(p.name)} ${e(p.employee_no||'工号未填写')}" ${selected.has(p.open_id)?'checked':''} ${busy?'disabled':''}>`:'—'}</td><td class="bulk-member-details"><strong>${e(p.name)}</strong><div class="table-subtitle">工号：${e(p.employee_no||'未填写')}</div><div class="table-subtitle">部门：${e((p.department_paths?.length?p.department_paths:p.departments)?.join('；')||'未填写')}</div></td><td>${e(p.job_title||'未填写')}</td><td>${e(p.current_access)}</td><td><span class="tag ${p.status==='created'?'tag-success':'tag-neutral'}">${e(statusName[p.status]||p.status)}</span><div class="table-subtitle">${e(p.result_reason||p.action)}</div>${choiceControl(p,busy)}</td></tr>`).join('')}</tbody></table></div>`;
}

export function openBulkAccess(store,ui,onBack){
  if(!ui.isSuperAdmin){ui.toast('仅超级管理员可以批量授权','error');return;}
  ui.openModal(`<div class="modal-header"><div><div class="eyebrow">BATCH AUTHORIZATION</div><h2>按部门和职位批量授权</h2></div></div><div class="modal-body"><div class="inline-note">按一级部门设置新增普通管理员的方向和等级，包含下级部门。已有管理员保留原权限，超级管理员及已撤销账号均跳过。</div><section class="certification-section"><h3>1. 选择部门和人员范围</h3><form data-bulk-rules><div class="bulk-rule-scroll" data-bulk-departments>正在读取公司部门…</div><div class="directory-toolbar"><span class="muted" data-bulk-sync-status role="status"></span><button type="button" class="text-btn" data-bulk-refresh>刷新通讯录</button></div><div class="bulk-settings"><button type="submit" class="btn btn-primary" disabled data-bulk-preview>预览名单</button></div></form></section><section class="certification-section" data-bulk-preview-section hidden><h3>2. 核对人员名单</h3><p class="muted" data-bulk-summary></p><div class="bulk-list-toolbar"><label><span class="field-label">搜索预览名单</span><input type="search" data-bulk-search placeholder="搜索姓名、工号、部门或职位"></label><button type="button" class="text-btn" data-bulk-select>选中当前搜索结果</button><button type="button" class="text-btn" data-bulk-unselect>取消当前搜索结果</button></div><label class="bulk-confirm"><input type="checkbox" data-bulk-show-all>显示职位不符合的员工</label><div class="member-list-scroll bulk-preview-scroll" data-bulk-list role="region" aria-label="批量授权名单" tabindex="0"></div><p class="muted" data-bulk-count role="status" aria-live="polite"></p><label class="bulk-confirm"><input type="checkbox" data-bulk-confirm>我已核对名单，确认按名单中的方向和等级给所选人员开通普通管理员权限。</label><button type="button" class="btn btn-primary" data-bulk-apply disabled>确认授权</button><p role="status" data-bulk-progress aria-live="polite"></p></section><p class="field-error" role="alert" data-bulk-error></p><button type="button" class="btn btn-secondary" data-bulk-retry hidden>重新读取部门</button></div><div class="modal-footer"><button type="button" class="btn btn-secondary" data-bulk-back>← 返回认证</button></div>`,modal=>{
    const find=s=>modal.querySelector(s), form=find('[data-bulk-rules]'), error=find('[data-bulk-error]');
    const section=find('[data-bulk-preview-section]'), list=find('[data-bulk-list]'), search=find('[data-bulk-search]');
    const confirm=find('[data-bulk-confirm]'), applyButton=find('[data-bulk-apply]'), previewButton=find('[data-bulk-preview]');
    let preview=null,selected=new Set(),busy=false,finished=false,syncTimer;
    const syncStatus=find('[data-bulk-sync-status]'), refreshButton=find('[data-bulk-refresh]');
    function showSync(info){
      if(!info)return;
      const updated=info.last_updated_at?new Date(info.last_updated_at).toLocaleString('zh-CN',{hour12:false}):'尚未完成';
      syncStatus.textContent=`通讯录更新于 ${updated} · ${info.syncing?'正在后台更新，可继续预览':info.error_code?'上次更新失败，暂用已有名单':'每天凌晨 3 点自动更新（北京时间）'}`;
      refreshButton.disabled=busy||!!info.syncing;
    }
    async function pollSync(){
      if(!modal.isConnected)return;
      try{
        const info=await ui.service.certifications.directoryStatus();
        if(!modal.isConnected)return;
        showSync(info);
        if(info.syncing)syncTimer=setTimeout(pollSync,2000);
        else if(info.last_updated_at)syncStatus.textContent+='；点击重新预览使用最新名单';
      }catch(err){if(modal.isConnected){error.textContent=err.message;refreshButton.disabled=false;}}
    }
    refreshButton.onclick=async()=>{
      if(busy)return;
      clearTimeout(syncTimer);refreshButton.disabled=true;
      try{
        const info=await ui.service.certifications.refreshDirectory();
        if(!modal.isConnected)return;
        showSync(info);
        if(info.retry_after_seconds)ui.toast(`请在 ${info.retry_after_seconds} 秒后再次刷新。`);
        syncTimer=setTimeout(pollSync,2000);
      }catch(err){error.textContent=err.message;refreshButton.disabled=false;}
    };
    const back=()=>{if(!busy)onBack();};
    const closeButton=find('.modal-close');
    closeButton.onclick=back;
    closeButton.textContent='← 返回认证';
    closeButton.classList.add('bulk-back-control');
    find('.modal-header').classList.add('bulk-modal-header');
    closeButton.setAttribute('aria-label','返回认证');
    closeButton.title='返回认证';
    const visiblePeople=()=>preview.items.filter(p=>find('[data-bulk-show-all]').checked || p.status!=='not_matched');
    const invalidate=()=>{preview=null;selected.clear();section.hidden=true;confirm.checked=false;};
    function render(){
      if(!preview)return;
      const shown=filterBulkPeople(visiblePeople(),search.value);
      list.innerHTML=bulkRows(shown,selected,busy||finished);
      find('[data-bulk-count]').textContent=`显示 ${shown.length} / ${preview.items.length} 人，已选择 ${selected.size} 人`;
      applyButton.textContent=`确认给 ${selected.size} 人开通普通管理员权限`;
      applyButton.disabled=busy||finished||!selected.size||!confirm.checked;
      find('[data-bulk-select]').disabled=busy||finished;
      find('[data-bulk-unselect]').disabled=busy||finished;
      confirm.disabled=busy||finished;
    }
    function operation(value){
      busy=value;modal.dataset.operationPending=String(value);
      form.querySelectorAll('select,button').forEach(el=>el.disabled=value);
      find('[data-bulk-back]').disabled=value;
      render();
    }
    form.addEventListener('change',invalidate);
    search.addEventListener('input',()=>{render();list.scrollTop=0;});
    confirm.addEventListener('change',render);
    find('[data-bulk-show-all]').addEventListener('change',render);
    list.addEventListener('change',event=>{
      if(busy||finished)return;
      const choiceId=event.target.dataset.bulkChoice;
      if(choiceId){
        const person=preview?.items.find(p=>p.open_id===choiceId);
        if(!person)return;
        if(resolveBulkChoice(person,event.target.value))selected.add(choiceId);else selected.delete(choiceId);
        confirm.checked=false;render();return;
      }
      const id=event.target.dataset.bulkPerson;
      if(!preview?.items.some(p=>p.open_id===id&&p.status==='new'))return;
      if(event.target.checked)selected.add(id);else selected.delete(id);
      render();
    });
    find('[data-bulk-select]').onclick=()=>{if(busy||finished||!preview)return;filterBulkPeople(visiblePeople(),search.value).filter(p=>p.status==='new').forEach(p=>selected.add(p.open_id));render();};
    find('[data-bulk-unselect]').onclick=()=>{if(busy||finished||!preview)return;filterBulkPeople(visiblePeople(),search.value).forEach(p=>selected.delete(p.open_id));render();};
    find('[data-bulk-back]').onclick=back;
    form.onsubmit=async event=>{
      event.preventDefault();if(busy)return;
      const rules=[...form.querySelectorAll('[data-bulk-rule]')].map(row=>({department_id:row.querySelector('[data-bulk-department]').dataset.bulkDepartment,mode:row.querySelector('[data-bulk-department]').value,domain:row.querySelector('[data-bulk-domain]').value,level:row.querySelector('[data-bulk-level]').value})).filter(r=>r.mode!=='off');
      error.textContent='';invalidate();
      if(!rules.length){error.textContent='请至少选择一个部门的授权范围。';return;}
      operation(true);previewButton.textContent='正在生成预览…';
      try{
        preview=await ui.service.certifications.previewBulk({rules});
        if(!modal.isConnected)return;
        showSync(preview.directory);
        selected=new Set(preview.items.filter(p=>p.status==='new').map(p=>p.open_id));
        finished=false;search.value='';find('[data-bulk-progress]').textContent='';
        const count=status=>preview.items.filter(p=>p.status===status).length;
        find('[data-bulk-summary]').textContent=`共 ${preview.items.length} 人：待新增 ${preview.new_count} 人，跨部门配置待确认 ${preview.conflict_count} 人，已有管理员 ${count('existing')} 人，超级管理员 ${count('super')} 人；职位未填写 ${count('missing_title')} 人。其他不符合条件或已撤销账号均跳过。方向和等级以每人的预览配置为准。预览有效期 30 分钟。`;
        section.hidden=false;render();
      }catch(err){error.textContent=err.message;}
      finally{operation(false);previewButton.textContent='重新预览名单';}
    };
    applyButton.onclick=async()=>{
      if(busy||finished||!preview||!confirm.checked||!selected.size)return;
      if(Date.now()/1000>=preview.expires_at){error.textContent='名单预览已过期，请重新预览。';return;}
      operation(true);error.textContent='';const ids=[...selected],counts={created:0,skipped:0,failed:0,unknown:0};
      let processed=0;
      try{
        for(let start=0;start<ids.length;start+=20){
          const batch=ids.slice(start,start+20);
          find('[data-bulk-progress]').textContent=`正在处理 ${processed} / ${ids.length} 人，请勿关闭页面…`;
          let result;
          try{result=await ui.service.certifications.applyBulk({preview_token:preview.preview_token,open_ids:batch,choices:Object.fromEntries(batch.map(id=>[id,preview.items.find(p=>p.open_id===id).target.department_id])),confirmed:true});}
          catch(err){
            batch.forEach(id=>{const p=preview.items.find(p=>p.open_id===id);p.status='unknown';p.result_reason='本批次结果待核实，请重新预览确认';selected.delete(id);counts.unknown++;});
            error.textContent=`${err.message} 已停止后续批次；请重新预览核实，勿仅凭连接错误判断授权失败。`;
            break;
          }
          for(const row of result.items){
            const p=preview.items.find(p=>p.open_id===row.open_id);
            p.status=row.status;p.result_reason=row.reason;selected.delete(row.open_id);counts[row.status]++;processed++;
          }
          render();
        }
      }finally{
        finished=true;operation(false);confirm.checked=false;render();
        find('[data-bulk-progress]').textContent=`本次结果：新增 ${counts.created} 人，跳过 ${counts.skipped} 人，失败 ${counts.failed} 人，待核实 ${counts.unknown} 人，未处理 ${ids.length-processed-counts.unknown} 人。需要继续时请重新预览。`;
        try{await store.refresh();}catch{/* Keep acknowledged results; refresh can be retried independently. */}
      }
    };
    const retryButton=find('[data-bulk-retry]');
    async function loadDepartments(){
      retryButton.hidden=true;retryButton.disabled=true;previewButton.disabled=true;error.textContent='';
      find('[data-bulk-departments]').textContent='正在读取公司部门…';
      try{
        const {items,directory}=await ui.service.certifications.departments();
        if(!modal.isConnected)return;
        showSync(directory);
        find('[data-bulk-departments]').innerHTML=departmentRows(items)||'未读取到一级部门，请检查通讯录可见范围。';
        previewButton.disabled=!items.some(d=>d.parent_id==='0');
        if(items.filter(d=>d.default_mode!=='off').length!==9)error.textContent='部分预设部门未匹配，请核对部门名称和可见范围，再调整规则。';
      }catch(err){find('[data-bulk-departments]').textContent='部门读取失败。';error.textContent=err.message;retryButton.hidden=false;}
      finally{retryButton.disabled=false;}
    }
    retryButton.onclick=()=>{if(!busy)void loadDepartments();};
    void loadDepartments();
  });
}
