import { publicationReward } from './publish-content-type.js?v=20261126-task-delivery';
import {taskAction, taskNumber, taskMaterialType} from './academy-task-label.js?v=20261126-task-delivery';
import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';
import { memberIdentity } from './member-access.js?v=20261126-progress-profile';

const courseStates = { draft: '草稿', pending: '待审核', returned: '已退回', published: '已上架', unpublished: '已下架' };
const studyStates = { not_started:'未开始', learning:'学习中', ready:'待提交心得', assessment:'待交章末考核', pending:'评审中', retry:'待重新提交', passed:'已通过' };
export const kindLabel = kind => ({ video:'视频', image:'图片', document:'文档', link:'学习链接' }[kind] || '材料');
const pill = (label, css='') => `<span class="ac-status ac-status-${e(css)}">${e(label)}</span>`;
const statusBadge = value => pill(courseStates[value] || value || '草稿', value === 'returned' ? 'rejected' : value);
const action = (name, value, label, css='ghost') => `<button type="button" class="ac-btn ac-btn-${css}" data-aw-${name}="${e(value)}">${e(label)}</button>`;
const selectOption = (value, name, current) => `<option value="${e(value)}" ${value === current ? 'selected' : ''}>${e(name)}</option>`;
const formatTime = timestamp => timestamp && Number.isFinite(Date.parse(timestamp)) ? new Date(timestamp).toLocaleString('zh-CN',{hour12:false}) : '—';
const tagsOf = tags => (tags || []).map(tag => `<span class="ac-badge">${e(tag)}</span>`).join('');
const table = (headings, rows) => `<div class="ac-table-wrap"><table class="ac-table aw-table"><thead><tr>${headings.map(h=>`<th scope="col">${e(h)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
const empty = message => `<div class="ac-empty"><strong>${e(message)}</strong></div>`;

export function permissions(data) {
  const { actorId, isSuperAdmin, canPublish } = data;
  return { isSuperAdmin, canPublish,
    editable: course => isSuperAdmin || (canPublish && course.author?.id === actorId),
    canReview: course => isSuperAdmin && course.status === 'pending',
  };
}

export function renderWorkspace(data, state, icon, scope='academy') {
  const village=scope==='village';
  const title=village?'新手村任务管理':'AI 学院';
  const rights = permissions(data);
  const tabs = [['courses',village?'任务管理':'课程管理'], ['reviews',rights.isSuperAdmin?'发布审核':'我的提交'], ['progress','学习情况']];
  const count = data.courses.filter(rights.canReview).length;
  const actor = `<span class="aw-actor">${e(data.actorName||'当前账号')}</span> <span class="aw-role-label">${rights.isSuperAdmin?'超级管理员':'普通管理员'}</span>`;
  const tools = rights.canPublish ? `<button type="button" class="ac-btn ac-btn-primary" data-aw-new>${icon('plus',15)} ${village?'新建发布':'新增课程'}</button>` : '';
  return `<header class="ac-heading"><div><h1>${title}</h1><p>${actor}</p></div><div class="ac-actions">${tools}</div></header>
    <nav class="ac-admin-tabs" aria-label="${title}管理">${tabs.map(([key,label]) => `<button type="button" data-aw-tab="${key}" aria-current="${key===state.tab?'page':'false'}" class="${key===state.tab?'active':''}">${label}${key==='reviews' && count ? ` <span class="ac-badge">${count}</span>` : ''}</button>`).join('')}</nav>
    ${state.tab==='progress' ? progressView(data,state,village) : catalogView(data,state,rights,village)}
    ${!village && data.canManageLegacy ? '<button type="button" class="ac-btn ac-btn-ghost aw-history" data-aw-legacy>原有课程与员工分享记录</button>' : ''}`;
}

function catalogView(data,state,rights,village) {
  const reviewing = state.tab==='reviews';
  const list = data.courses.filter(c=>(!reviewing || (c.status==='pending' && (rights.isSuperAdmin || c.author?.id===data.actorId))) && (!state.tag || c.tags?.includes(state.tag)) && (!state.status || c.status===state.status));
  const rows = list.map(c=>{
    const reward = publicationReward(village?'village':'academy',c.required);
    const actions = [action('detail',c.id,'查看')];
    if (rights.canReview(c)) actions.push(action('decide',c.id,'审核'));
    if (rights.editable(c) && c.status!=='pending') actions.push(action('edit',c.id,'编辑'));
    const live=c.liveRevision || (c.status==='published'?c.revision:null);
    const hasPrevious=Boolean(live && live!==c.revision);
    if (rights.editable(c) && live) actions.push(action('unpublish',c.id,hasPrevious?'下架在架版本':'下架'));
    return `<tr data-aw-searchable="${e([c.title,c.summary,c.author?.name,...(c.tags||[])].join(' ').toLowerCase())}"><td><button type="button" class="ac-row-title" data-aw-detail="${e(c.id)}">${e(c.title)}</button><span class="ac-row-summary">${village?(c.required?'必修课程 · ':'普通任务 · '):''}${c.chapters?.length || 1} 章 · ${e(c.summary)}</span></td><td>${tagsOf(c.tags)||'—'}</td><td>${e(c.author?.name||'—')}</td><td>${statusBadge(c.status)}${hasPrevious ? `<small class="ac-row-summary">版本 ${Number(live)} 仍在架</small>` : ''}${c.returnReason && c.status==='returned' ? `<span class="ac-inline-error">${e(c.returnReason)}</span>` : ''}</td><td>${(c.rewardXp ?? 20)} 经验 / ${reward.unit}</td><td><div class="ac-row-actions">${actions.join('')}</div></td></tr>`;
  }).join('');
  const filters = `<div class="ac-toolbar aw-filters"><input aria-label="搜索课程" type="search" data-aw-search value="${e(state.search)}" placeholder="搜索课程、标签或发布人"><select aria-label="筛选课程标签" data-aw-filter="tag">${selectOption('','全部标签',state.tag)}${data.tags.map(tag=>selectOption(tag,tag,state.tag)).join('')}</select>${reviewing?'':`<select aria-label="筛选课程状态" data-aw-filter="status">${selectOption('','全部状态',state.status)}${Object.entries(courseStates).map(([v,n])=>selectOption(v,n,state.status)).join('')}</select>`}</div>`;
  return filters + (list.length ? table([village?'名称':'课程名称','标签','发布人','状态',village?'奖励经验值':'整套课程奖励','操作'],rows) + '<p data-aw-no-match hidden class="ac-empty">暂无匹配的课程</p>' : empty(reviewing?'暂无待审核的课程':'暂无符合条件的课程'));
}

function progressView(data,state,village) {
  const profiles = new Map();
  if (village) {
    for (const person of data.learners) {
      if (person.memberProfile) profiles.set(person.id,person.memberProfile);
    }
  }
  const options = new Map((data.progressCourses || []).map(course => [course.id,course.title]));
  const selectedCourse = options.has(state.progressCourse) ? state.progressCourse : '';
  const records = data.progress.filter(row => options.has(row.courseId) && (!selectedCourse || row.courseId===selectedCourse));
  const rows = records.map(row=>{
    const percent = Math.max(0,Math.min(100,Math.round(Number(row.percent)||0)));
    const watched = Math.max(0,Math.floor(Number(row.watchedSeconds)||0));
    const title = row.courseTitle||options.get(row.courseId)||'—';
    const profile = profiles.get(row.learnerId);
    const name = profile?.name || row.learnerName || '—';
    const person = profile ? `<div class="aw-progress-person" data-initial="${e(name.slice(0,1))}">${memberIdentity({
      name, avatar:profile.avatar, employee_no:profile.employeeNo, job_title:profile.jobTitle,
      department_paths:profile.departmentPaths, departments:profile.departments,
    })}</div>` : e(name);
    const search = [row.learnerName,profile?.name,profile?.employeeNo,title].filter(Boolean).join(' ').toLowerCase();
    const detail = village ? `<td><button type="button" class="ac-btn ac-btn-ghost" data-aw-reflections="${e(row.courseId)}" data-learner-id="${e(row.learnerId)}" data-course-revision="${e(row.courseRevision)}">查看心得</button></td>` : '';
    return `<tr data-aw-searchable="${e(search)}"><td>${person}</td><td>${e(title)}${row.courseRevision ? `<small class="ac-row-summary">在架版本 ${Number(row.courseRevision)}</small>` : ''}</td><td><progress max="100" value="${percent}" aria-label="课程进度"></progress> ${percent}%<small class="ac-row-summary">${Number(row.completedChapters)||0} / ${Number(row.chapterCount)||1} 章已完成</small></td><td>${Math.floor(watched/60)} 分 ${watched%60} 秒</td><td>${e(studyStates[row.status] || row.status || '未开始')}</td><td>${e(formatTime(row.updatedAt))}</td>${detail}</tr>`;
  }).join('');
  const columns = ['学员','课程','学习进度','有效观看','学习状态','最近学习'];
  if (village) columns.push('操作');
  const rosterButton = !village && permissions(data).canPublish ? action('learners','','学员名单','secondary') : '';
  return `<div class="ac-toolbar aw-filters"><input type="search" data-aw-search value="${e(state.search)}" aria-label="搜索学员或课程" placeholder="搜索学员或课程"><select aria-label="选择进度课程" data-aw-filter="progressCourse">${selectOption('','全部课程',selectedCourse)}${[...options].map(([id,title])=>selectOption(id,title,selectedCourse)).join('')}</select>${action('reload','','刷新','secondary')}${rosterButton}</div>
    ${records.length ? table(columns,rows) + '<p data-aw-no-match hidden class="ac-empty">暂无匹配的学习记录</p>' : empty('暂无学员学习记录')}`;
}

export function chapterReflections({ courseTitle, learnerName, chapters }) {
  const sections = chapters.map((chapter, index) => `<section>
    <h3>第 ${index+1} 章 · ${e(chapter.title)}</h3>
    ${chapter.text == null ? '<p class="ac-muted">未提交心得</p>' : `${chapter.submittedAt ? `<small class="ac-muted">提交于 ${e(formatTime(chapter.submittedAt))}</small>` : ''}<p class="aw-preserve">${e(chapter.text)}</p>`}
  </section>`).join('');
  return `<p>${e(learnerName)} · ${e(courseTitle)}</p>${sections}`;
}

export function learnerRoster(data) {
  const rows=data.learners.map(person=>`<tr><td>${e(person.memberProfile?.name || person.name)}</td></tr>`).join('');
  return `<h2>学员名单</h2><div class="ac-modal-body">${rows ? table(['学员'],rows) : empty('暂无学员')}</div>`;
}

export function courseDetail(course,scope='academy') {
  const reward = publicationReward(scope,course.required);
  const labels=[...(scope==='village'?[['发布类型',course.required?'必修课程':'普通任务']]:[]),['发布人',course.author?.name],['学习时长',`${course.minutes} 分钟`],[reward.label,`${course.rewardXp ?? 20} 经验 / ${reward.unit}`],...(scope==='village'?[['课程内容范围',course.requiredTopic||'公司通用常识']]:[]),['标签',course.tags?.join('、')||'—']];
  const byId=new Map((course.materials||[]).map(m=>[m.id,m]));
  function taskRow(m,index) {
    let href='';
    try {const u=new URL(m.url,location.origin); if (['http:','https:'].includes(u.protocol) && !u.username && !u.password) href=u.href;} catch {}
    return `<li><strong>${taskNumber(index+1)} · ${e(m.taskTitle || taskAction(m.kind))}</strong> · ${e(taskMaterialType(m))} · ${href ? `<a href="${e(href)}" rel="noopener noreferrer" target="_blank">${e(m.title||m.name)}</a>` : e(m.title||m.name)}</li>`;
  }
  return `<div class="ac-modal-heading"><h2>${e(course.title)}</h2></div><div class="ac-modal-body"><p>${e(course.summary)}</p><dl class="ac-detail-list">${labels.map(([k,v])=>`<div><dt>${k}</dt><dd>${e(v)}</dd></div>`).join('')}</dl><h3>课程目录</h3>${(course.chapters||[]).map((ch,i)=>`<p><strong>第 ${i+1} 章 · ${e(ch.title)}</strong></p><ol>${ch.sections.flatMap(sec=>sec.materialIds).map(id=>byId.get(id)).filter(Boolean).map(taskRow).join('')}</ol>${ch.exam?`<p>考试 · ${e(ch.exam)}（10 经验）</p>`:''}${ch.homework?`<p>作业 · ${e(ch.homework)}（${ch.homeworkXp} 经验）</p>`:''}`).join('')}${course.chapters?.length?'':`<ul class="aw-detail-materials">${(course.materials||[]).map(taskRow).join('')}</ul>`}<h3>课程正文或讲义</h3><p class="aw-preserve">${e(course.contentText||'尚未填写')}</p><h3>心得评审标准</h3><p class="aw-preserve">${e(course.rubric||'尚未填写')}</p>${course.returnReason?`<p class="ac-inline-error">退回原因 · ${e(course.returnReason)}</p>`:''}</div>`;
}
