import { publicationReward } from './publish-content-type.js?v=20261126-task-delivery';
import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';
import { uploadAcademyAsset } from './academy-upload.js';
import { bindCourseCover, renderCourseCover } from './academy-workspace-cover.js';
import { bindCoursePreview } from './village-course-preview.js?v=20261126-task-delivery';
import { bindFieldFeedback, showFieldError } from './field-feedback.js';
import { courseIssues, materialControl, saveErrorControl, sectionControl } from './academy-course-validation.js';

import { prepareChapters, currentChapter, currentSection, structureFields, captureStructure, bindStructure } from './academy-chapters.js?v=20261126-task-delivery';

export function createEditor(course,scope='academy') {
  const editor = {
    scope,
    course: course ? structuredClone(course) : {creationId:crypto.randomUUID(), title:'', summary:'', minutes:10, tags:[], materials:[], cover:null, contentText:'', rubric:'', rewardXp:20},
    linkDrafts:new Map(), issues:[], busy:false, progress:null,
  };
  if (scope === 'village' && editor.course.required == null) editor.course.required = true;
  prepareChapters(editor.course);
  return editor;
}

const field = (title,body) => `<label class="ac-field"><span>${title}</span>${body}</label>`;
const textInput = (name,value) => `<input type="text" name="${name}" value="${e(value)}">`;
const area = (name,value,hint) => `<textarea name="${name}" rows="4" placeholder="${e(hint)}">${e(value)}</textarea>`;
const numberInput = (name,value,min) => `<input type="number" name="${name}" min="${min}" step="1" value="${e(value)}">`;

function linkDraft(editor, section) {
  if (!editor.linkDrafts.has(section)) editor.linkDrafts.set(section, { linkKind:'link', linkTitle:'', linkUrl:'' });
  return editor.linkDrafts.get(section);
}

function progressStatus(progress) {
  return progress ? `<div class="ac-upload-progress" data-aw-progress role="status"><progress max="100" value="${progress.percent}"></progress><span>${e(progress.text)}</span></div>` : '';
}

function materialInput(editor, icon) {
  const section=currentSection(editor);
  const draft=linkDraft(editor,section);
  const kinds=[['link','学习链接'],['video','视频直链'],['image','图片地址'],['document','云文档或文档链接']];
  return `<div class="aw-series-upload">
    <label class="aw-drop" data-aw-drop tabindex="0">${icon('upload',22)}<strong>上传学习任务材料，或拖放到此处</strong><small>每份文件生成一个学习任务，可修改任务名称。每个视频最大 2 GB，文档和图片每份最大 100 MB。</small><input type="file" multiple data-aw-files aria-label="选择视频或学习资料" aria-describedby="aw-upload-error"></label>
    ${editor.progress?.upload ? progressStatus(editor.progress) : ''}
    <div class="ac-inline-error" id="aw-upload-error"></div>
    <details class="aw-series-links" ${draft.linkTitle || draft.linkUrl?'open':''}><summary>用链接添加学习任务</summary>
    <div class="aw-link-fields"><label class="ac-field"><span>链接类型</span><select name="linkKind">${kinds.map(([value,label])=>`<option value="${value}" ${draft.linkKind===value?'selected':''}>${label}</option>`).join('')}</select></label>
    ${field('材料名称',textInput('linkTitle',draft.linkTitle))}${field('内部或外部地址',textInput('linkUrl',draft.linkUrl))}<button type="button" class="ac-btn ac-btn-secondary" data-aw-add-link>添加链接</button></div>
    <small class="ac-muted">视频直链需能在浏览器中直接播放，以便记录观看进度。</small></details></div>`;
}

export function renderCourseActions(editor,isSuperAdmin,external = false) {
  const attr = external ? 'form="village-publication-form"' : '';
  const disabled = editor.busy ? 'disabled' : '';
  const buttonClass = external ? 'btn' : 'ac-btn';
  const buttons = `<button ${attr} class="${buttonClass} ${buttonClass}-secondary" type="submit" value="draft" ${disabled}>保存草稿</button><button ${attr} class="${buttonClass} ${buttonClass}-primary" type="submit" value="publish" ${disabled}>${isSuperAdmin?(editor.scope==='village'?'确认发布':'发布课程'):'提交发布审核'}</button>`;
  return external ? `<div class="editor-actionbar village-course-actions"><div class="action-buttons">${buttons}</div></div>` : `<div class="ac-form-footer">${buttons}</div>`;
}

export function renderEditor(editor,tags,isSuperAdmin,icon,externalControls = false) {
  const c=editor.course;
  const village=editor.scope==='village';
  const reward=publicationReward(editor.scope,c.required);
  const title=`${c.id?'编辑':'新增'}${village?(c.required?'必修课程':'普通任务'):'课程'}`;
  const heading=externalControls ? '' : `<header class="ac-heading"><h1>${title}</h1><button type="button" class="ac-btn ac-btn-secondary" data-aw-cancel ${editor.busy?'disabled':''}>返回课程管理</button></header>`;
  return `${heading}
    <section class="ac-form-card"><${externalControls ? 'div class="ac-form"' : 'form class="ac-form" data-aw-editor novalidate'}><fieldset class="ac-form-fields" ${editor.busy?'disabled':''}>
    ${c.status==='returned'?`<p class="ac-inline-error">退回原因 · ${e(c.returnReason)}</p>`:''}
    ${externalControls?'':field(village?'名称':'课程名称',textInput('title',c.title))+field(village?'简介':'课程简介',area('summary',c.summary,'介绍课程内容和学习目标'))}
    <div class="ac-form-grid">${field('预计学习时长（分钟）',numberInput('minutes',c.minutes,1))}
    <label class="ac-field"><span data-reward-label>${reward.label}经验值</span><input name="rewardXp" type="number" required min="0" max="1000000" step="1" value="${e(c.rewardXp ?? 20)}"><small data-reward-hint>${reward.hint}</small></label>
    ${village && c.required?`<label class="ac-field"><span>课程内容范围</span><select name="requiredTopic">${['公司通用常识','公司文化','公司制度',...(c.requiredTopic==='全员通识'?['全员通识']:[])].map(t=>`<option ${c.requiredTopic===t?'selected':''}>${t}</option>`).join('')}</select></label>`:''}</div>
    <fieldset class="ac-tag-options"><legend>课程标签</legend><div>${tags.map(tag=>`<label><input type="checkbox" name="tags" value="${e(tag)}" ${c.tags.includes(tag)?'checked':''}>${e(tag)}</label>`).join('')}
      ${isSuperAdmin?'<button type="button" class="ac-btn ac-btn-ghost" data-aw-tags aria-haspopup="dialog">管理标签</button>':''}</div></fieldset>
    ${structureFields(editor,materialInput(editor,icon))}
    ${renderCourseCover(editor)}
    <section class="aw-section"><h2>章节心得评审${village?' <small class="tag tag-neutral">暂未开放</small>':''}</h2><p>${village?'AI 评审开放后可配置讲义和评分细则。现有内容可查看，可直接发布。':'心得按章评审。以下讲义和评分细则适用于本课程各章。'}</p><fieldset class="ac-form-fields" aria-label="章节心得评审设置" ${village?'disabled':''}>${field('课程正文、讲义或视频字幕',area('contentText',c.contentText,village?'暂未开放填写':'填写课程要点，或导入讲义和字幕。AI 将结合这些内容与评分细则评审学员心得。'))}
    <label class="ac-field"><span>导入文字材料</span><input type="file" accept=".txt,.md,.vtt,.srt" data-aw-transcript><small>可将 TXT、Markdown、VTT 或 SRT 追加到上方文本框。已上传的 TXT、Markdown 和 DOCX 材料会自动提取正文。视频和网页课程请补充讲义或字幕。</small></label>
    ${field('评分细则与通过条件',area('rubric',c.rubric,village?'暂未开放填写':'列出心得需覆盖的关键点、评分标准和通过条件'))}</fieldset></section>
    </fieldset>${editor.progress?.upload ? '' : progressStatus(editor.progress)}
    ${externalControls ? '' : renderCourseActions(editor,isSuperAdmin)}</${externalControls?'div':'form'}></section>`;
}

function resourceUrl(value) {
  const raw=value.trim();
  if (!raw || (!/^https?:\/\//i.test(raw) && !/^\/(?!\/)/.test(raw))) throw new Error('请输入 http(s) 地址或以 / 开头的站内地址。');
  try {
    const url=new URL(raw,location.origin);
    if (!url.username && !url.password && !/[\s\\]/.test(raw) && url.href.length <= 4000) return url;
  } catch { /* Report an actionable validation message below. */ }
  throw new Error('请输入有效的材料地址，地址中不能含空格或账号密码。');
}

function videoDuration(url) {
  return new Promise((resolve,reject)=>{
    const player=document.createElement('video');
    const finish = seconds => {
      clearTimeout(timeout);
      player.onloadedmetadata=null;
      player.onerror=null;
      player.removeAttribute('src');
      player.load();
      if (Number.isFinite(seconds) && seconds>0) resolve(seconds);
      else reject(new Error('无法读取视频时长，请提供可直接播放的视频地址，或上传视频文件。'));
    };
    const timeout=setTimeout(()=>finish(0),15000);
    player.preload='metadata';
    player.onloadedmetadata=()=>finish(player.duration);
    player.onerror=()=>finish(0);
    player.src=url;
  });
}

function capture(editor,form) {
  for (const key of (editor.scope==='village' ? ['title','summary'] : ['title','summary','contentText','rubric'])) editor.course[key]=form.elements[key].value;
  captureStructure(editor,form);
  if(form.elements.requiredTopic)editor.course.requiredTopic=form.elements.requiredTopic.value;
  for (const key of ['minutes','rewardXp']) editor.course[key]=form.elements[key].value===''?'':Number(form.elements[key].value);
  editor.course.tags=[...form.querySelectorAll('[name=tags]:checked')].map(input=>input.value);
  const draft=linkDraft(editor,currentSection(editor));
  for (const key of ['linkTitle','linkKind','linkUrl']) draft[key]=form.elements[key].value;
}

export function bindEditor(root,editor,{refresh,save,cancel,manageTags,icon}) {
  const form=root.querySelector('[data-aw-editor]');
  if (!form) return;
  bindFieldFeedback(form);
  const sameField=(a,b)=>a.selector===b.selector && a.chapter===b.chapter && a.section===b.section;
  const clearIssue=field=>{ editor.issues=editor.issues.filter(issue=>!sameField(issue,field)); };
  const isVisibleIssue=issue=>(!issue.chapter || issue.chapter===currentChapter(editor).id) &&
    (!issue.section || issue.section===currentSection(editor).id);
  const targetFor=issue=>form.querySelector(issue.selector) || [...form.elements].find(el=>el.matches(issue.selector));
  if (!editor.busy) {
    for (const issue of editor.issues.filter(isVisibleIssue)) {
      const target=targetFor(issue);
      if (!target) continue;
      const container=issue.selector===materialControl ? form.querySelector('#aw-upload-error') :
        target.closest('.series-title-field, .aw-cover-settings, .ac-tag-options');
      showFieldError(target,issue.message,{container: container || undefined,focus:editor.focusIssue===issue});
    }
    editor.focusIssue=null;
  }
  const reveal=issue=>{
    editor.focusIssue=issue;
    if (issue.chapter) {editor.chapterId=issue.chapter;editor.sectionId=issue.section || null;}
  };
  const clearEditedIssue=event=>{
    editor.issues=editor.issues.filter(issue=>!isVisibleIssue(issue) || !event.target.matches(issue.selector));
  };
  form.addEventListener('input',clearEditedIssue);
  form.addEventListener('change',clearEditedIssue);
  form.addEventListener('change', event => {
    if (!event.target.matches('[data-publish-kind]:checked')) return;
    const reward = publicationReward(editor.scope,event.target.value === 'required');
    form.querySelector('[data-reward-label]').textContent = reward.label + '经验值';
    form.querySelector('[data-reward-hint]').textContent = reward.hint;
  });
  const work=async (task, initialProgress={percent:0,text:'正在处理…'}, field)=>{
    if (editor.busy) return;
    capture(editor,form);
    if (field && typeof field!=='function') clearIssue(field);
    editor.progress=initialProgress;
    editor.busy=true;
    refresh();
    try { await task(); }
    catch(error) {
      const message=error.message || '操作未完成，请重试。';
      const issue={...(typeof field==='function' ? field(message) : field),message};
      clearIssue(issue);
      editor.issues.push(issue);
      reveal(issue);
    }
    finally {editor.progress=null;editor.busy=false;refresh();}
  };
  form.oninput=event=>{
    const id=event.target.dataset?.taskName;
    if(id){
      const material=editor.course.materials.find(item=>item.id===id);
      if(material)material.taskTitle=event.target.value;
    }
    capture(editor,form);
    const counter=form.querySelector('#title-counter');
    if(counter) counter.textContent=editor.course.title.length+'/150';
  };
  if(editor.scope==='village') bindCoursePreview(root.querySelector('[data-village-course-preview]'),form,editor.course,icon);
  bindStructure(editor,form,refresh);
  bindCourseCover(form,editor,{work,redraw:()=>{capture(editor,form);refresh();}});
  const manageTagButton=form.querySelector('[data-aw-tags]');
  if(manageTagButton) manageTagButton.onclick=()=>{
    capture(editor,form);
    manageTags();
  };
  root.querySelector('[data-aw-cancel]')?.addEventListener('click',()=>{if(!editor.busy)cancel();});
  form.onsubmit=event=>{
    event.preventDefault();
    if(editor.busy)return;
    const intent=event.submitter?.value==='publish'?'publish':'draft';
    capture(editor,form);
    editor.issues=courseIssues(editor,intent==='publish');
    if(editor.issues.length){reveal(editor.issues[0]);refresh();return;}
    void work(()=>save(editor.course,intent),undefined,message=>({selector:saveErrorControl(message,intent)}));
  };
  form.querySelector('[data-aw-add-link]').onclick=()=>void work(async()=>{
    const section=currentSection(editor);
    const draft=linkDraft(editor,section);
    const url=resourceUrl(draft.linkUrl);
    const kind=draft.linkKind==='video' || /\.(mp4|m4v|webm|ogg|ogv|mov)$/i.test(url.pathname)?'video':draft.linkKind;
    const material={id:crypto.randomUUID(),title:draft.linkTitle.trim()||url.hostname,kind,url:url.href};
    if(kind==='video') material.durationSeconds=await videoDuration(url.href);
    editor.course.materials.push(material);
    section.materialIds.push(material.id);
    editor.linkDrafts.delete(section);
    clearIssue(sectionControl(editor,materialControl));
  },undefined,sectionControl(editor,'[name=linkUrl]'));
  form.querySelectorAll('[data-aw-remove]').forEach(button=>{button.onclick=()=>{
    capture(editor,form);
    const index=editor.course.materials.findIndex(material=>material.id===button.dataset.awRemove);
    if(index<0)return;
    const [removed]=editor.course.materials.splice(index,1);
    for (const chapter of editor.course.chapters) {
      for (const section of chapter.sections) section.materialIds=section.materialIds.filter(id=>id!==removed.id);
    }
    if(editor.course.cover?.materialId===removed.id)editor.course.cover=null;
    if(editor.coverVideoId===removed.id)editor.coverVideoId=null;
    refresh();
  };});
  form.querySelector('[data-aw-transcript]').onchange=event=>{
    if(editor.scope==='village')return;
    const file=event.target.files[0];
    if(!file)return;
    void work(async()=>{
      const sourceLimit=48000;
      if(file.size>sourceLimit*12)throw new Error('讲义内容较长，请摘取本课核心内容后导入。');
      let body=await file.text();
      if(/\.(vtt|srt)$/i.test(file.name)) {
        body=body.split(/\r?\n/).filter(line=>line.trim()&&line.trim()!=='WEBVTT'&&!/^\d+$/.test(line.trim())&&!line.includes('-->')).join('\n');
      }
      body=[editor.course.contentText.trim(),body.trim()].filter(Boolean).join('\n\n');
      if(body.length>sourceLimit)throw new Error('课程文字超过 48,000 字，请摘取本课核心内容后导入。');
      editor.course.contentText=body;
    },undefined,{selector:'[data-aw-transcript]'});
  };
  const acceptFiles=files=>void work(async()=>{
    const section=currentSection(editor);
    const failures=[];
    for (const [index,file] of files.entries()) {
      try {
        const material=await uploadAcademyAsset(file,percent=>{
          editor.progress={upload:true,percent,text:`第 ${index+1}/${files.length} 个文件 · ${file.name} · ${percent}%`};
          const el=document.querySelector('[data-aw-progress]');
          if(el){el.hidden=false;el.querySelector('progress').value=percent;el.querySelector('span').textContent=editor.progress.text;}
        });
        const attached=material.assetId && editor.course.materials.some(m=>m.assetId===material.assetId && section.materialIds.includes(m.id));
        if(!attached) {
          const entry=editor.course.materials.some(m=>m.id===material.id)?{...material,id:crypto.randomUUID()}:material;
          editor.course.materials.push(entry);
          section.materialIds.push(entry.id);
        }
      } catch(error){failures.push(`${file.name} · ${error.message}`);}
    }
    if(failures.length) throw new Error(failures.join('；'));
  },{upload:true,percent:0,text:`准备上传 ${files.length} 个文件…`},sectionControl(editor,materialControl));
  const drop=form.querySelector('[data-aw-drop]');
  drop.querySelector('input').onchange=event=>{const files=[...event.target.files];if(files.length)acceptFiles(files);};
  drop.onkeydown=event=>{if(event.target===drop && (event.key==='Enter'||event.key===' ')){event.preventDefault();drop.querySelector('input').click();}};
  drop.ondragover=event=>{event.preventDefault();drop.classList.add('dragging');};
  drop.ondragleave=()=>drop.classList.remove('dragging');
  drop.ondrop=event=>{event.preventDefault();drop.classList.remove('dragging');if(event.dataTransfer.files.length)acceptFiles([...event.dataTransfer.files]);};
  form.onpaste=event=>{if(event.clipboardData?.files.length){event.preventDefault();acceptFiles([...event.clipboardData.files]);}};
}
