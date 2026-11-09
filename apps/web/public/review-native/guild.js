import { GUILD_CAPABILITIES, GUILD_LEVELS } from './guild-store.js?v=20261028-server';

const e = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char]));
const date = value => { const d=new Date(value); return Number.isNaN(d.getTime())?'—':d.toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}); };
const abilityName = id => GUILD_CAPABILITIES.find(item=>item.id===id)?.name || id || '—';
const errorText = error => error?.message || '操作失败，请重试';
const statusNames = { active:'已认证',revoked:'已撤销',superseded:'已更新',draft:'草稿',published:'已开放',archived:'已下架',enabled:'已启用',disabled:'已停用',pending:'待审核',approved:'已通过',returned:'已退回' };
const gradeName=grade=>({1:'一级 · 蓝色',2:'二级 · 紫色',3:'三级 · 金色'}[grade]||'未知等级');
const rankName=level=>({1:'基础实践者',2:'进阶协作者',3:'综合交付者'}[level]||'待确认');
const stageName=level=>({1:'规范实践',2:'协同攻坚',3:'复杂交付'}[level]||'待确认');
const requestGuildName=item=>item.guildId?(item.guildTitle||item.guildId):'旧版全局认证';
const statusTag = status => `<span class="gd-status ${e(status)}">${e(statusNames[status] || status)}</span>`;
function safeUrl(value) { try { const raw=String(value||'').trim(); if(!/^https?:\/\//i.test(raw)||/[\s\\]/.test(raw))return ''; const url=new URL(raw); return url.hostname&&!url.username&&!url.password?url.href:''; } catch { return ''; } }

export function createGuildController({ guild, ui }) {
  const state={tab:'requests',query:'',status:'pending',contributionView:'rules'};
  let active=false,requestTimer=null;
  const data=()=>guild.snapshot();
  const ic=(name,size=16)=>ui.icon(name,size);
  const guard=()=>{ if(guild.isAdmin())return true; ui.toast('仅管理员可管理交付线工会','error'); return false; };
  const refresh=()=>{if(active)ui.refresh();};
  const match=(...values)=>!state.query.trim()||values.some(value=>String(value||'').toLocaleLowerCase().includes(state.query.trim().toLocaleLowerCase()));
  const empty=(title,description)=>`<div class="gd-empty">${ic(state.tab==='labs'?'grid':state.tab==='contributions'?'star':'award',34)}<strong>${title}</strong><p>${description}</p></div>`;
  const abilityOptions=selected=>GUILD_CAPABILITIES.map(item=>`<option value="${e(item.id)}" ${selected===item.id?'selected':''}>${e(item.name)}</option>`).join('');
  const taskName=(id,snapshot)=>snapshot.tasks.find(task=>task.id===id)?.title || '未关联任务';

  function toolbar() {
    const placeholder=state.tab==='requests'?'搜索学员、所属工会、阶段或任务':state.tab==='certifications'?'搜索学员或认证能力':state.tab==='labs'?'搜索实验室或关联任务':'搜索任务或学员';
    const options=state.tab==='requests'?[['pending','待审核'],['approved','已通过'],['returned','已退回'],['all','全部状态']]:state.tab==='certifications'?[['all','全部状态'],['active','已认证'],['revoked','已撤销'],['superseded','已更新']]:state.tab==='labs'?[['all','全部状态'],['draft','草稿'],['published','已开放'],['archived','已下架']]:[];
    return `<div class="gd-toolbar"><label class="gd-search">${ic('search')}<input type="search" data-gd-search value="${e(state.query)}" placeholder="${placeholder}" aria-label="${placeholder}"></label>${options.length?`<select data-gd-status aria-label="按状态筛选">${options.map(([value,label])=>`<option value="${value}" ${state.status===value?'selected':''}>${label}</option>`).join('')}</select>`:''}</div>`;
  }
  function requestTable() {
    if(guild.requestsError)return `<div class="gd-empty" role="alert"><strong>晋级申请读取失败</strong><p>${e(guild.requestsError)}</p><button class="gd-btn gd-btn-secondary" data-gd-reload-requests>重新加载</button></div>`;
    if(!guild.requestsLoaded)return '<div class="gd-empty" role="status">正在读取学员晋级申请…</div>';
    const requests=guild.requestSnapshot().requests;
    const list=requests.filter(item=>(state.status==='all'||state.status===item.status)&&match(item.studentName,item.studentId,requestGuildName(item),item.guildId,`L${item.level}`,stageName(item.level),rankName(item.level),item.task?.title,...item.evidence.map(badge=>badge.name)));
    if(!list.length)return empty('暂无符合条件的晋级申请',requests.length?'调整搜索词或状态筛选。':'学员在公会提交认证申请后，会在这里显示。');
    return `<div class="gd-table-wrap"><table class="gd-table gd-requests-table"><thead><tr><th>学员</th><th>所属工会</th><th>申请阶段 / 任务</th><th>徽章凭证</th><th>状态</th><th>申请 / 审核时间</th><th>操作</th></tr></thead><tbody>${list.map(item=>`<tr><td><strong>${e(item.studentName)}</strong><small>${e(item.studentId)}</small></td><td class="gd-request-guild"><strong>${e(requestGuildName(item))}</strong>${item.guildId?`<small>${e(item.guildId)}</small>`:'<small>独立保留，不计入具体工会阶段</small>'}</td><td class="gd-request-stage"><strong>${e(stageName(item.level))}</strong><small>L${Number(item.level)} · ${e(rankName(item.level))}</small>${item.task?.title?`<small class="gd-request-task-title">${e(item.task.title)}</small>`:''}</td><td><div class="gd-request-evidence-summary">${item.evidence.map(badge=>`<span><b class="gd-badge-grade" data-grade="${Number(badge.grade)}">${e(gradeName(badge.grade))}</b>${e(badge.name)}</span>`).join('')}</div></td><td>${statusTag(item.status)}${item.status==='returned'?`<small class="gd-truncate" title="${e(item.reason)}">${e(item.reason)}</small>`:''}</td><td>${date(item.submittedAt)}${item.reviewedAt?`<small>${e(item.reviewerName||'管理员')} · ${date(item.reviewedAt)}</small>`:''}</td><td><div class="gd-row-actions"><button data-gd-request-detail="${e(item.id)}">${item.status==='pending'&&item.studentId!==guild.currentUserId()?'查看并审核':'查看详情'}</button></div>${item.status==='pending'&&item.studentId===guild.currentUserId()?'<small>需由其他管理员审核</small>':''}</td></tr>`).join('')}</tbody></table></div>`;
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
  function table() {const snapshot=data();return state.tab==='requests'?requestTable():state.tab==='certifications'?certificationTable(snapshot):state.tab==='labs'?labTable(snapshot):contributionTable(snapshot);}
  function render() {
    if(!guild.isAdmin())return '<section class="guild-page"><div class="gd-empty">仅管理员可管理交付线工会。</div></section>';
    const snapshot=data(),stats=snapshot.stats,requests=guild.requestSnapshot().requests;
    const pending=requests.filter(item=>item.status==='pending').length;
    return `<section class="guild-page"><header class="gd-heading"><h1>交付线工会</h1>${state.tab==='requests'?`<button class="gd-btn gd-btn-secondary" data-gd-reload-requests ${guild.requestsLoading?'disabled':''}>${ic('refresh')} 刷新申请</button>`:`<button class="gd-btn gd-btn-primary" data-gd-create>${ic('plus')} ${state.tab==='certifications'?'新增认证':state.tab==='labs'?'新增实验室':'关联任务'}</button>`}</header>
      <div class="gd-stats"><div><span>能力认证学员</span><strong>${Number(stats.certifiedLearners)}<small>人</small></strong></div><div><span>开放实验室</span><strong>${Number(stats.publishedLabs)}<small>个</small></strong></div><div><span>工会累计贡献</span><strong>${Number(stats.totalPoints).toLocaleString('zh-CN')}<small>点</small></strong></div></div>
      <div class="gd-tabs" role="tablist" aria-label="工会管理">${[['requests','晋级审核'],['certifications','能力认证'],['labs','模拟实验室'],['contributions','工会贡献']].map(([id,label])=>`<button role="tab" aria-selected="${state.tab===id}" class="${state.tab===id?'active':''}" data-gd-tab="${id}">${label}${id==='requests'&&pending?`<span class="gd-pending-count">${pending}</span>`:''}</button>`).join('')}</div>
      ${state.tab==='requests'?'<div class="gd-note">学员按所属工会提交规范实践、协同攻坚、复杂交付的认证任务，由管理员核对任务成果、自查记录与徽章凭证。审核通过只更新该工会的阶段；退回需填写原因，历史记录保留。旧版全局认证独立保留。此认证不扣点、不发放奖励。</div>':state.tab==='labs'?'<div class="gd-note">配置实验场景与环境入口，实际实验在对应环境中进行。</div>':state.tab==='contributions'?`<div class="gd-note">关联任务通过后计入工会贡献，每人每个任务仅计一次；历史已完成任务不补记。</div><div class="gd-subtabs">${[['rules','任务规则'],['records','贡献记录']].map(([id,label])=>`<button class="${state.contributionView===id?'active':''}" data-gd-contribution-view="${id}">${label}<span>${id==='rules'?snapshot.rules.length:snapshot.contributions.length}</span></button>`).join('')}</div>`:''}
      ${toolbar()}<div data-gd-results>${table()}</div><p class="gd-storage-note">晋级申请、审核结果、能力认证、实验室配置与贡献记录由后台保存。</p></section>`;
  }
  function bind(root) {
    active=true;if(!guild.isAdmin())return;
    if(requestTimer)clearInterval(requestTimer);
    requestTimer=setInterval(()=>{if(active&&state.tab==='requests'&&!guild.requestsLoading&&(typeof document==='undefined'||document.visibilityState==='visible'))void guild.refreshRequests().then(refresh,refresh);},30000);
    const paint=()=>{const node=root.querySelector('[data-gd-results]');if(node)node.innerHTML=table();};
    root.querySelector('[data-gd-search]')?.addEventListener('input',event=>{state.query=event.target.value;paint();});
    root.querySelector('[data-gd-status]')?.addEventListener('change',event=>{state.status=event.target.value;paint();});
    root.addEventListener('click',event=>{
      const button=event.target.closest('button');if(!button||!root.contains(button)||button.disabled)return;
      const ds=button.dataset,snapshot=data();
      if(ds.gdTab){state.tab=ds.gdTab;state.query='';state.status=ds.gdTab==='requests'?'pending':'all';refresh();if(ds.gdTab==='requests')void guild.refreshRequests().then(refresh,refresh);}
      else if(ds.gdContributionView){state.contributionView=ds.gdContributionView;state.query='';refresh();}
      else if(button.hasAttribute('data-gd-reload-requests'))runButton(button,()=>guild.refreshRequests(),'晋级申请已刷新');
      else if(button.hasAttribute('data-gd-create')){if(state.tab==='certifications')certificationForm();else if(state.tab==='labs')labForm();else ruleForm();}
      else if(ds.gdRequestDetail)requestDetail(guild.requestSnapshot().requests.find(item=>item.id===ds.gdRequestDetail));
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
  function requestEvidence(item) {
    return `<ul class="gd-review-evidence">${item.evidence.map(badge=>`<li><span class="gd-badge-grade" data-grade="${Number(badge.grade)}">${e(gradeName(badge.grade))}</span><strong>${e(badge.name)}</strong><small>徽章编号：${e(badge.id)}</small></li>`).join('')}</ul>`;
  }
  function requestTask(item) {
    const task=item.task;
    if(!task)return `<div class="gd-note">${item.guildId?'此申请未提供认证任务成果，请核实后处理。':'该记录属于旧版全局认证，提交时未要求认证任务成果。'}</div>`;
    const checks=Array.isArray(task.checks)?task.checks:[];
    return `<section class="gd-review-task"><h3>认证任务与阶段成果</h3><dl class="gd-details"><div><dt>任务名称</dt><dd><strong>${e(task.title||task.taskId||task.id||'认证任务')}</strong></dd></div>${task.brief?`<div><dt>任务描述</dt><dd class="gd-copy">${e(task.brief)}</dd></div>`:''}${task.deliverable?`<div><dt>交付要求</dt><dd class="gd-copy">${e(task.deliverable)}</dd></div>`:''}${task.mentor?`<div><dt>任务指导</dt><dd>${e(task.mentor)}</dd></div>`:''}<div><dt>成果提交时间</dt><dd>${date(task.submittedAt||item.submittedAt)}</dd></div><div><dt>自查记录</dt><dd>${checks.length?`<ul class="gd-review-checks">${checks.map(check=>`<li><span aria-hidden="true">✓</span>${e(check)}</li>`).join('')}</ul>`:'未提供自查记录'}</dd></div></dl><h4>学员提交的完整成果</h4><div class="gd-review-artifact">${e(task.artifact||'未提供成果')}</div></section>`;
  }
  function requestDetail(item) {
    if(!item)return;
    const self=item.studentId===guild.currentUserId();
    modal('公会晋级申请详情',`<dl class="gd-details"><div><dt>申请学员</dt><dd>${e(item.studentName)}<small class="gd-muted"> · ${e(item.studentId)}</small></dd></div><div><dt>所属工会</dt><dd>${e(requestGuildName(item))}</dd></div><div><dt>申请阶段</dt><dd>${e(stageName(item.level))}<small class="gd-muted"> · L${Number(item.level)} ${e(rankName(item.level))}</small></dd></div><div><dt>申请状态</dt><dd>${statusTag(item.status)}</dd></div><div><dt>申请时间</dt><dd>${date(item.submittedAt)}</dd></div><div><dt>徽章凭证</dt><dd>${requestEvidence(item)}</dd></div>${item.reviewedAt?`<div><dt>审核人 / 时间</dt><dd>${e(item.reviewerName||'管理员')} · ${date(item.reviewedAt)}</dd></div><div><dt>审核意见</dt><dd class="gd-copy">${e(item.reason||'—')}</dd></div>`:''}</dl>${requestTask(item)}<p class="gd-muted">以上内容为提交时保存的凭证；审核通过前，后台会再次核对该工会的阶段顺序及徽章所有权。</p>${item.status==='pending'?(self?'<p class="gd-note">不能审核自己的晋级申请，请由其他管理员处理。</p>':'<footer class="gd-form-actions"><button class="gd-btn gd-btn-secondary" data-gd-return-request>退回申请</button><button class="gd-btn gd-btn-primary" data-gd-approve-request>审核通过</button></footer>'):''}`,node=>{
      node.classList.add('gd-request-modal');
      node.querySelector('[data-gd-approve-request]')?.addEventListener('click',()=>requestReviewForm(item,'approved'));
      node.querySelector('[data-gd-return-request]')?.addEventListener('click',()=>requestReviewForm(item,'returned'));
    });
  }
  function requestReviewForm(item,decision) {
    if(!item||item.status!=='pending')return;
    const returned=decision==='returned';
    const approvalNote=item.guildId?`通过后将该学员在“${requestGuildName(item)}”的阶段更新为“${stageName(item.level)}”，其他工会的进度不变。`:`通过后更新该学员的旧版全局认证等级为 L${Number(item.level)}，不计入具体工会阶段。`;
    modal(returned?'退回公会晋级申请':'确认通过公会晋级申请',`<form class="gd-form"><p class="gd-copy">${e(item.studentName)} · ${e(requestGuildName(item))}
${e(stageName(item.level))} · L${Number(item.level)} ${e(rankName(item.level))}${item.task?.title?`
认证任务：${e(item.task.title)}`:''}</p>${requestEvidence(item)}<p class="gd-note">${returned?'退回后保留任务成果、申请与审核记录，学员可查看原因、补充成果并重新申请。':`${e(approvalNote)}保存审核人与审核时间；不扣点、不发放奖励。`}</p><label class="gd-field"><span>${returned?'退回原因 <i>*</i>':'审核意见（选填）'}</span><textarea name="reason" ${returned?'required':''} maxlength="1000" rows="4" placeholder="${returned?'请说明需要补充或调整的内容，学员可见':'可补充本次审核说明'}"></textarea></label>${formFooter(returned?'确认退回':'确认审核通过')}</form>`,node=>{
      node.querySelector('form').onsubmit=event=>{
        event.preventDefault();const reason=String(new FormData(event.currentTarget).get('reason')||'').trim();
        if(returned&&!reason){error(node,'请填写退回原因。');return;}
        perform(node,()=>guild.reviewRequest(item.id,decision,reason),returned?'申请已退回，学员可查看原因':'审核已通过，认证记录已保存');
      };
    });
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
  function deactivate(){active=false;if(requestTimer)clearInterval(requestTimer);requestTimer=null;}
  function reset(){deactivate();Object.assign(state,{tab:'requests',query:'',status:'pending',contributionView:'rules'});}
  return {render,bind,reset,deactivate};
}
