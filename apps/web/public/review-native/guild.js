import { GUILD_CAPABILITIES, GUILD_LEVELS } from './guild-store.js?v=20261028-server';

const e = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char]));
const date = value => { const d=new Date(value); return Number.isNaN(d.getTime())?'—':d.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}); };
const abilityName = id => GUILD_CAPABILITIES.find(item=>item.id===id)?.name || id || '—';
const errorText = error => error?.message || '操作失败，请重试';
const statusNames = { active:'已认证',revoked:'已撤销',superseded:'已更新',draft:'草稿',published:'已开放',archived:'已下架',enabled:'已启用',disabled:'已停用' };
const statusTag = status => `<span class="gd-status ${e(status)}">${e(statusNames[status] || status)}</span>`;
function safeUrl(value) { try { const raw=String(value||'').trim(); if(!/^https?:\/\//i.test(raw)||/[\s\\]/.test(raw))return ''; const url=new URL(raw); return url.hostname&&!url.username&&!url.password?url.href:''; } catch { return ''; } }

export function createGuildController({ guild, ui }) {
  const state={tab:'certifications',query:'',status:'all',contributionView:'rules'};
  let active=false;
  const data=()=>guild.snapshot();
  const ic=(name,size=16)=>ui.icon(name,size);
  const guard=()=>{ if(guild.isAdmin())return true; ui.toast('仅管理员可管理交付线工会','error'); return false; };
  const refresh=()=>{if(active)ui.refresh();};
  const match=(...values)=>!state.query.trim()||values.some(value=>String(value||'').toLocaleLowerCase().includes(state.query.trim().toLocaleLowerCase()));
  const empty=(title,description)=>`<div class="gd-empty">${ic(state.tab==='labs'?'grid':state.tab==='contributions'?'star':'award',34)}<strong>${title}</strong><p>${description}</p></div>`;
  const abilityOptions=selected=>GUILD_CAPABILITIES.map(item=>`<option value="${e(item.id)}" ${selected===item.id?'selected':''}>${e(item.name)}</option>`).join('');
  const taskName=(id,snapshot)=>snapshot.tasks.find(task=>task.id===id)?.title || '未关联任务';

  function toolbar() {
    const placeholder=state.tab==='certifications'?'搜索学员或认证能力':state.tab==='labs'?'搜索实验室或关联任务':'搜索任务或学员';
    const options=state.tab==='certifications'?[['all','全部状态'],['active','已认证'],['revoked','已撤销'],['superseded','已更新']]:state.tab==='labs'?[['all','全部状态'],['draft','草稿'],['published','已开放'],['archived','已下架']]:[];
    return `<div class="gd-toolbar"><label class="gd-search">${ic('search')}<input type="search" data-gd-search value="${e(state.query)}" placeholder="${placeholder}" aria-label="${placeholder}"></label>${options.length?`<select data-gd-status aria-label="按状态筛选">${options.map(([value,label])=>`<option value="${value}" ${state.status===value?'selected':''}>${label}</option>`).join('')}</select>`:''}</div>`;
  }
  function certificationTable(snapshot) {
    const list=snapshot.certifications.filter(item=>(state.status==='all'||state.status===item.status)&&match(item.studentName,abilityName(item.ability),item.level));
    if(!list.length)return empty('暂无认证记录',snapshot.certifications.length?'调整搜索词或筛选条件。':'点击“新增认证”，为学员确认能力与等级。');
    return `<div class="gd-table-wrap"><table class="gd-table"><thead><tr><th>学员</th><th>认证能力</th><th>等级</th><th>状态</th><th>认证人 / 时间</th><th>操作</th></tr></thead><tbody>${list.map(item=>`<tr><td><strong>${e(item.studentName)}</strong><small>${e(item.studentId)}</small></td><td>${e(abilityName(item.ability))}</td><td>${e(item.level)}</td><td>${statusTag(item.status)}</td><td>${e(item.issuedBy?.name || '管理员')}<small>${date(item.issuedAt)}</small></td><td><div class="gd-row-actions"><button data-gd-cert-detail="${e(item.id)}">详情</button>${item.status==='active'?`<button data-gd-cert-revoke="${e(item.id)}">撤销</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>`;
  }
  function labTable(snapshot) {
    const list=snapshot.labs.filter(item=>(state.status==='all'||state.status===item.status)&&match(item.title,item.description,abilityName(item.ability),taskName(item.taskId,snapshot)));
    if(!list.length)return empty('暂无模拟实验室',snapshot.labs.length?'调整搜索词或筛选条件。':'新增实验室，配置练习场景、环境入口和关联任务。');
    return `<div class="gd-table-wrap"><table class="gd-table"><thead><tr><th>实验室</th><th>对应能力</th><th>关联任务</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${list.map(item=>`<tr><td><strong>${e(item.title)}</strong><small class="gd-truncate" title="${e(item.description)}">${e(item.description)}</small></td><td>${e(abilityName(item.ability))}</td><td><span class="gd-truncate" title="${e(taskName(item.taskId,snapshot))}">${e(taskName(item.taskId,snapshot))}</span></td><td>${statusTag(item.status)}</td><td>${date(item.updatedAt)}</td><td><div class="gd-row-actions"><button data-gd-lab-detail="${e(item.id)}">查看</button><button data-gd-lab-edit="${e(item.id)}">编辑</button><button data-gd-lab-toggle="${e(item.id)}" data-status="${item.status==='published'?'archived':'published'}">${item.status==='published'?'下架':'开放'}</button></div></td></tr>`).join('')}</tbody></table></div>`;
  }
  function contributionTable(snapshot) {
    if(state.contributionView==='rules') {
      const list=snapshot.rules.filter(item=>match(item.taskTitle,taskName(item.taskId,snapshot)));
      if(!list.length)return empty('暂无贡献任务',snapshot.rules.length?'调整搜索词再试试。':'点击“关联任务”，设置学员通过任务后为工会增加的贡献点。');
      return `<div class="gd-table-wrap"><table class="gd-table"><thead><tr><th>关联任务</th><th>贡献点 / 人</th><th>状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${list.map(item=>`<tr><td><strong>${e(taskName(item.taskId,snapshot)==='未关联任务'?item.taskTitle:taskName(item.taskId,snapshot))}</strong><small>${e(item.taskId)}</small></td><td><strong class="gd-positive">+${Number(item.points)}</strong></td><td>${statusTag(item.enabled?'enabled':'disabled')}</td><td>${date(item.updatedAt)}</td><td><div class="gd-row-actions"><button data-gd-rule-edit="${e(item.id)}">编辑</button><button data-gd-rule-toggle="${e(item.id)}">${item.enabled?'停用':'启用'}</button></div></td></tr>`).join('')}</tbody></table></div>`;
    }
    const list=snapshot.contributions.filter(item=>match(item.studentName,item.taskTitle,item.studentId));
    if(!list.length)return empty('暂无贡献记录',snapshot.contributions.length?'调整搜索词再试试。':'关联任务通过后自动入账，记录贡献学员、任务和点数。');
    return `<div class="gd-table-wrap"><table class="gd-table"><thead><tr><th>贡献学员</th><th>完成任务</th><th>工会贡献点</th><th>计入时间</th></tr></thead><tbody>${list.map(item=>`<tr><td><strong>${e(item.studentName)}</strong><small>${e(item.studentId)}</small></td><td>${e(item.taskTitle)}</td><td><strong class="gd-positive">+${Number(item.points)}</strong></td><td>${date(item.creditedAt)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function table() {const snapshot=data();return state.tab==='certifications'?certificationTable(snapshot):state.tab==='labs'?labTable(snapshot):contributionTable(snapshot);}
  function render() {
    if(!guild.isAdmin())return '<section class="guild-page"><div class="gd-empty">仅管理员可管理交付线工会。</div></section>';
    const snapshot=data(), stats=snapshot.stats;
    return `<section class="guild-page"><header class="gd-heading"><h1>交付线工会</h1><button class="gd-btn gd-btn-primary" data-gd-create>${ic('plus')} ${state.tab==='certifications'?'新增认证':state.tab==='labs'?'新增实验室':'关联任务'}</button></header><div class="gd-stats"><div><span>认证学员</span><strong>${Number(stats.certifiedLearners)}<small>人</small></strong></div><div><span>开放实验室</span><strong>${Number(stats.publishedLabs)}<small>个</small></strong></div><div><span>工会累计贡献</span><strong>${Number(stats.totalPoints).toLocaleString('zh-CN')}<small>点</small></strong></div></div><div class="gd-tabs" role="tablist" aria-label="工会管理">${[['certifications','能力认证'],['labs','模拟实验室'],['contributions','工会贡献']].map(([id,label])=>`<button role="tab" aria-selected="${state.tab===id}" class="${state.tab===id?'active':''}" data-gd-tab="${id}">${label}</button>`).join('')}</div>${state.tab==='labs'?'<div class="gd-note">配置实验场景与环境入口，实际实验在对应环境中进行。</div>':state.tab==='contributions'?`<div class="gd-note">关联任务通过后计入工会贡献，每人每个任务仅计一次；历史已完成任务不补记。</div><div class="gd-subtabs">${[['rules','任务规则'],['records','贡献记录']].map(([id,label])=>`<button class="${state.contributionView===id?'active':''}" data-gd-contribution-view="${id}">${label}<span>${id==='rules'?snapshot.rules.length:snapshot.contributions.length}</span></button>`).join('')}</div>`:''}${toolbar()}<div data-gd-results>${table()}</div><p class="gd-storage-note">认证、实验室配置与贡献记录由后台保存。</p></section>`;
  }
  function bind(root) {
    active=true;if(!guild.isAdmin())return;
    const paint=()=>{const node=root.querySelector('[data-gd-results]');if(node)node.innerHTML=table();};
    root.querySelector('[data-gd-search]')?.addEventListener('input',event=>{state.query=event.target.value;paint();});
    root.querySelector('[data-gd-status]')?.addEventListener('change',event=>{state.status=event.target.value;paint();});
    root.addEventListener('click',event=>{
      const button=event.target.closest('button');if(!button||!root.contains(button)||button.disabled)return;
      const ds=button.dataset,snapshot=data();
      if(ds.gdTab){state.tab=ds.gdTab;state.query='';state.status='all';refresh();}
      else if(ds.gdContributionView){state.contributionView=ds.gdContributionView;state.query='';refresh();}
      else if(button.hasAttribute('data-gd-create')){if(state.tab==='certifications')certificationForm();else if(state.tab==='labs')labForm();else ruleForm();}
      else if(ds.gdCertDetail)certificationDetail(snapshot.certifications.find(item=>item.id===ds.gdCertDetail));
      else if(ds.gdCertRevoke)revokeForm(snapshot.certifications.find(item=>item.id===ds.gdCertRevoke));
      else if(ds.gdLabDetail)labDetail(snapshot.labs.find(item=>item.id===ds.gdLabDetail));
      else if(ds.gdLabEdit)labForm(snapshot.labs.find(item=>item.id===ds.gdLabEdit));
      else if(ds.gdLabToggle)runButton(button,()=>guild.setLabStatus(ds.gdLabToggle,ds.status),ds.status==='published'?'实验室已开放':'实验室已下架');
      else if(ds.gdRuleEdit)ruleForm(snapshot.rules.find(item=>item.id===ds.gdRuleEdit));
      else if(ds.gdRuleToggle){const rule=snapshot.rules.find(item=>item.id===ds.gdRuleToggle);if(rule)runButton(button,()=>guild.setRuleEnabled(rule.id,!rule.enabled),rule.enabled?'贡献规则已停用':'贡献规则已启用');}
    });
  }
  function modal(title,body,ready) {
    if(!guard())return;
    ui.openModal(`<div class="gd-modal-heading"><h2>${e(title)}</h2></div>${body}`,node=>{
      node.classList.add('gd-modal');node.querySelectorAll('[data-gd-cancel]').forEach(button=>button.onclick=()=>ui.closeModal());ready?.(node);
    });
  }
  const error=(node,message)=>{const target=node.querySelector('[data-gd-error]');if(target)target.textContent=message;};
  const formFooter=label=>`<p class="gd-error" data-gd-error role="alert"></p><footer class="gd-form-actions"><button class="gd-btn gd-btn-secondary" type="button" data-gd-cancel>取消</button><button class="gd-btn gd-btn-primary" type="submit">${label}</button></footer>`;
  async function perform(node,operation,message) {
    if(node.dataset.gdBusy==='true'||!guard())return;node.dataset.gdBusy='true';node.dataset.operationPending='true';error(node,'');
    const controls=[...node.querySelectorAll('button,input,select,textarea')].map(control=>[control,control.disabled]);controls.forEach(([control])=>control.disabled=true);
    try{await operation();delete node.dataset.operationPending;if(node.isConnected)ui.closeModal();refresh();ui.toast(message);}
    catch(err){if(node.isConnected)error(node,errorText(err));else ui.toast(errorText(err),'error');}
    finally{node.dataset.gdBusy='false';delete node.dataset.operationPending;controls.forEach(([control,disabled])=>control.disabled=disabled);}
  }
  async function runButton(button,operation,message) {
    if(!guard()||button.disabled)return;button.disabled=true;
    try{await operation();refresh();ui.toast(message);}catch(err){ui.toast(errorText(err),'error');}finally{button.disabled=false;}
  }
  function certificationForm() {
    const snapshot=data();
    modal('新增能力认证',`<form class="gd-form"><label class="gd-field"><span>选择学员 <i>*</i></span><select name="studentId" required><option value="">请选择学员</option>${snapshot.learners.map(item=>`<option value="${e(item.id)}">${e(item.name)} · ${e(item.cohort || item.id)}</option>`).join('')}</select></label><div class="gd-form-grid"><label class="gd-field"><span>认证能力 <i>*</i></span><select name="ability">${abilityOptions('data')}</select></label><label class="gd-field"><span>认证等级 <i>*</i></span><select name="level">${GUILD_LEVELS.map(level=>`<option>${e(level)}</option>`).join('')}</select></label></div><label class="gd-field"><span>认证依据 <i>*</i></span><textarea name="evidence" required maxlength="1000" rows="4" placeholder="填写能力评估结果、完成的实践或交付表现"></textarea></label><p class="gd-muted">同一能力再次认证后，旧记录会保留为历史。</p>${formFooter('确认认证')}</form>`,node=>{
      node.querySelector('form').onsubmit=event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));perform(node,()=>guild.grantCertification(values),'能力认证已完成');};
    });
  }
  function certificationDetail(item) {
    if(!item)return;
    modal('能力认证详情',`<dl class="gd-details"><div><dt>学员</dt><dd>${e(item.studentName)} · ${e(item.studentId)}</dd></div><div><dt>认证能力</dt><dd>${e(abilityName(item.ability))} · ${e(item.level)}</dd></div><div><dt>状态</dt><dd>${statusTag(item.status)}</dd></div><div><dt>认证人</dt><dd>${e(item.issuedBy?.name || '管理员')}</dd></div><div><dt>认证时间</dt><dd>${date(item.issuedAt)}</dd></div><div><dt>认证依据</dt><dd class="gd-copy">${e(item.evidence)}</dd></div>${item.status==='revoked'?`<div><dt>撤销原因</dt><dd class="gd-copy">${e(item.revokeReason || item.revocationReason || item.reason || '—')}</dd></div><div><dt>撤销时间</dt><dd>${date(item.revokedAt)}</dd></div>`:''}${item.status==='superseded'?`<div><dt>更新时间</dt><dd>${date(item.supersededAt)}</dd></div>`:''}</dl>`);
  }
  function revokeForm(item) {
    if(!item)return;
    modal('撤销能力认证',`<form class="gd-form"><p class="gd-copy">${e(item.studentName)} · ${e(abilityName(item.ability))} · ${e(item.level)}</p><label class="gd-field"><span>撤销原因 <i>*</i></span><textarea name="reason" required maxlength="1000" rows="4" placeholder="说明撤销原因，原认证记录会保留"></textarea></label>${formFooter('确认撤销')}</form>`,node=>{
      node.querySelector('form').onsubmit=event=>{event.preventDefault();const reason=new FormData(event.currentTarget).get('reason');perform(node,()=>guild.revokeCertification(item.id,reason),'认证已撤销');};
    });
  }
  function labForm(item=null) {
    const snapshot=data();const tasks=snapshot.tasks.filter(task=>task.status==='published'||task.id===item?.taskId);
    modal(item?'编辑模拟实验室':'新增模拟实验室',`<form class="gd-form"><label class="gd-field"><span>实验室名称 <i>*</i></span><input name="title" required maxlength="100" value="${e(item?.title||'')}" placeholder="例如：数据交付全流程模拟"></label><label class="gd-field"><span>对应能力</span><select name="ability">${abilityOptions(item?.ability||'data')}</select></label><label class="gd-field"><span>实验说明 <i>*</i></span><textarea name="description" required maxlength="2000" rows="4" placeholder="填写模拟场景、操作目标及提交要求">${e(item?.description||'')}</textarea></label><label class="gd-field"><span>实验环境链接</span><input name="url" type="url" maxlength="4000" value="${e(item?.url||'')}" placeholder="https://"><small>开放实验室前需配置可访问的环境链接。</small></label><label class="gd-field"><span>关联任务 <small>选填</small></span><select name="taskId"><option value="">暂不关联</option>${tasks.map(task=>`<option value="${e(task.id)}" ${task.id===item?.taskId?'selected':''}>${e(task.title)}${task.status!=='published'?'（未上架）':''}</option>`).join('')}</select></label><label class="gd-field"><span>状态</span><select name="status">${[['draft','保存为草稿'],['published','开放实验室'],...(item?.status==='archived'?[['archived','已下架']]:[])].map(([id,label])=>`<option value="${id}" ${id===(item?.status||'draft')?'selected':''}>${label}</option>`).join('')}</select></label>${formFooter('保存实验室')}</form>`,node=>{
      node.querySelector('form').onsubmit=event=>{
        event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));if(item)values.id=item.id;
        if(values.url&&!safeUrl(values.url)){error(node,'请填写有效的 HTTP 或 HTTPS 链接，链接不能包含账号密码');return;}
        if(values.status==='published'&&!values.url.trim()){error(node,'开放实验室前请填写实验环境链接');return;}
        perform(node,()=>guild.saveLab(values),'实验室已保存');
      };
    });
  }
  function labDetail(item) {
    if(!item)return;const snapshot=data(),task=snapshot.tasks.find(task=>task.id===item.taskId),url=safeUrl(item.url);
    modal(item.title,`<dl class="gd-details"><div><dt>对应能力</dt><dd>${e(abilityName(item.ability))}</dd></div><div><dt>状态</dt><dd>${statusTag(item.status)}</dd></div><div><dt>实验说明</dt><dd class="gd-copy">${e(item.description)}</dd></div><div><dt>关联任务</dt><dd>${e(task?.title||'未关联任务')}${task?`<p class="gd-muted gd-copy">${e(task.summary)}</p>`:''}</dd></div><div><dt>环境链接</dt><dd class="gd-copy">${e(item.url||'尚未配置')}</dd></div></dl>${url?`<footer class="gd-form-actions"><a class="gd-btn gd-btn-primary" href="${e(url)}" target="_blank" rel="noopener noreferrer">${ic('external')} 预览实验环境</a></footer>`:''}`);
  }
  function ruleForm(item=null) {
    const snapshot=data();const tasks=snapshot.tasks.filter(task=>(task.status==='published'||task.id===item?.taskId)&&(!snapshot.rules.some(rule=>rule.taskId===task.id)||task.id===item?.taskId));
    modal(item?'编辑贡献规则':'关联贡献任务',`<form class="gd-form"><label class="gd-field"><span>关联任务 <i>*</i></span><select name="taskId" required ${item?'disabled':''}><option value="">请选择已发布的任务</option>${tasks.map(task=>`<option value="${e(task.id)}" ${task.id===item?.taskId?'selected':''}>${e(task.title)}${task.status!=='published'?'（未上架）':''}</option>`).join('')}</select></label><label class="gd-field"><span>每位学员通过后增加 <i>*</i></span><div class="gd-points-input"><input name="points" type="number" min="1" max="10000" step="1" required value="${Number(item?.points||10)}"><span>贡献点</span></div></label><label class="gd-toggle"><input name="enabled" type="checkbox" ${item?.enabled===false?'':'checked'}><span>启用此贡献规则</span></label><p class="gd-muted">同一学员同一任务仅计一次。修改点数只影响后续入账，已计入的贡献保留。</p>${formFooter('保存规则')}</form>`,node=>{
      node.querySelector('form').onsubmit=event=>{
        event.preventDefault();const fields=new FormData(event.currentTarget);const values={taskId:item?.taskId||fields.get('taskId'),points:Number(fields.get('points')),enabled:fields.has('enabled')};
        if(!Number.isInteger(values.points)||values.points<1||values.points>10000){error(node,'贡献点请输入 1～10000 的整数');return;}
        perform(node,()=>guild.saveRule(values),'贡献规则已保存');
      };
    });
  }
  function deactivate(){active=false;}
  function reset(){deactivate();Object.assign(state,{tab:'certifications',query:'',status:'all',contributionView:'rules'});}
  return {render,bind,reset,deactivate};
}
