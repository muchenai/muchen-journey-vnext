import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';
import { bindEditor, createEditor, renderCourseActions, renderEditor } from './academy-workspace-editor.js?v=20261126-task-delivery';
import { renderCoursePreview } from './village-course-preview.js?v=20261126-task-delivery';
import { chapterReflections, courseDetail, learnerRoster, permissions, renderWorkspace } from './academy-workspace-views.js?v=20261126-village-progress-toolbar';
import { bindFieldFeedback, showFieldError } from './field-feedback.js';

const initialFilters=()=>({tab:'courses',tag:'',status:'',search:'',progressCourse:''});

export async function requestCourseWorkspace(endpoint,body,signal) {
  const response=await fetch(endpoint,{
    method:body?'POST':'GET',cache:'no-store',credentials:'same-origin',signal,
    ...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),
  });
  const result=await response.json().catch(()=>({}));
  if(!response.ok || !result.ok || !result.data) {
    const error = new Error(result.error?.message||result.error||'无法读取课程，请检查本地服务连接后重试。');
    error.status = response.status;
    throw error;
  }
  return result.data;
}

export function createAcademyWorkspace({ui,legacy,scope='academy',onNewPublication}) {
  const village=scope==='village';
  const title=village?'新手村任务管理':'AI 学院';
  const endpoint='/api/review-native/course-workspace'+(village?'?camp=village':'');
  let data=null, editor=null, historyView=false, active=false, loading=false, writing=false, error='', epoch=0;
  let requestedRequired=null;
  let permissionsStale=false;
  let reflectionModal=null;
  const suspendedEditors=new Map();
  let state=initialFilters();
  const refresh=()=>ui.refresh();
  function takeEditor(course){
    const key=course?.id || '';
    const saved=suspendedEditors.get(key);
    suspendedEditors.delete(key);
    return saved || createEditor(course,scope);
  }
  async function activate() {
    active=true;
    if(historyView && !permissionsStale){await legacy.activate();return;}
    if(loading||writing||(editor && !permissionsStale))return;
    const key=epoch;
    permissionsStale=false;
    loading=true;
    try{
      const result=await requestCourseWorkspace(endpoint);
      if(key!==epoch)return;
      if(data && data.actorId!==result.actorId){suspendedEditors.clear();editor=null;}
      data=result;error='';
      const rights=permissions(data);
      const canEdit=id=>{
        if(!id)return rights.admin;
        const course=data.courses.find(item=>item.id===id);
        return course && course.status!=='pending' && rights.editable(course);
      };
      if(editor && !canEdit(editor.course.id))editor=null;
      for(const id of suspendedEditors.keys())if(!canEdit(id))suspendedEditors.delete(id);
      if(historyView && !data.canManageLegacy){historyView=false;legacy.deactivate();}
      if(requestedRequired!==null){
        if(rights.admin) {
          editor=takeEditor(null);
          editor.course.required=requestedRequired;
        }
        requestedRequired=null;
      }
    }
    catch(err){
      if(key===epoch){
        error=err.message;
        if(err.status===401 || err.status===403){
          data=null;
          editor=null;
          suspendedEditors.clear();
          historyView=false;
        }
      }
    }
    finally{loading=false;if(active && permissionsStale)void activate();else if(active)refresh();}
  }
  function refreshPermissions(){
    closeReflections();
    permissionsStale=true;
    if(active)return activate();
  }
  function startPublishing(required=true){
    if(isBusy())return;
    active=true;
    if(editor){
      editor.course.required=required;
      return;
    }
    requestedRequired=required;
    return activate();
  }
  function showCourseList(){
    if(isBusy())return;
    requestedRequired=null;
    if(editor)suspendedEditors.set(editor.course.id || '', editor);
    editor=null;
    state=initialFilters();
    return activate();
  }
  function resumePublishing(){
    if (editor) { active=true; return; }
    return startPublishing(suspendedEditors.get('')?.course.required ?? true);
  }
  async function mutate(body) {
    if(writing)throw new Error('正在保存，请稍候。');
    writing=true;epoch++;
    try{data=await requestCourseWorkspace(endpoint,body);error='';}
    finally{writing=false;if(active && permissionsStale)void activate();}
  }
  function edit(course) {
    editor=takeEditor(course);
    refresh();
    window.scrollTo({top:0});
  }
  function cancel(){
    if(village)void showCourseList();
    else editor=null;
    refresh();
  }
  function render({externalControls = false} = {}) {
    if(historyView) return `<div class="aw-legacy"><button type="button" class="ac-btn ac-btn-secondary" data-aw-current>返回学院工作台</button>${legacy.render()}</div>`;
    const warning=error?`<div class="ac-notice ac-notice-warning" role="alert">${e(error)} <button type="button" class="ac-btn ac-btn-secondary" data-aw-reload>重试</button></div>`:'';
    const content=!data || requestedRequired!==null?(!error?`<div class="ac-empty" role="status">正在加载${title}…</div>`:''):editor?renderEditor(editor,data.tags,permissions(data).owner,ui.icon,externalControls):renderWorkspace(data,state,ui.icon,scope);
    return `<div class="academy-page">${warning}${content}</div>`;
  }
  function dialog(html,onReady){
    ui.openModal(html,modal=>{
      modal.classList.add('aw-modal');
      bindFieldFeedback(modal);
      modal.querySelector('[data-aw-close]')?.addEventListener('click',ui.closeModal);
      onReady?.(modal);
    });
  }
  function closeReflections() {
    if (reflectionModal?.isConnected) ui.closeModal();
  }
  function showReflections(button) {
    const query=new URLSearchParams({courseId:button.dataset.awReflections,learnerId:button.dataset.learnerId});
    if (button.dataset.courseRevision) query.set('courseRevision',button.dataset.courseRevision);
    dialog('<h2 id="aw-reflections-title">章节心得</h2><div class="ac-modal-body" data-aw-reflection-body><p role="status">正在读取心得…</p></div>',async modal=>{
      reflectionModal=modal;
      modal.setAttribute('aria-labelledby','aw-reflections-title');
      const controller=new AbortController();
      modal.addEventListener('review-close',()=>{
        controller.abort();
        if (reflectionModal===modal) reflectionModal=null;
      },{once:true});
      const body=modal.querySelector('[data-aw-reflection-body]');
      try {
        const detail=await requestCourseWorkspace('/api/review-native/course-workspace/village-reflections?'+query,undefined,controller.signal);
        if (!controller.signal.aborted) body.innerHTML=chapterReflections(detail);
      } catch (err) {
        if (!controller.signal.aborted) {
          body.setAttribute('role','alert');
          body.textContent=err.status===409?'课程版本已更新，请关闭并刷新学习情况后再查看。':err.message;
        }
      }
    });
  }
  async function dialogAction(modal,target,action,onSuccess) {
    if(modal.dataset.operationPending==='true')return;
    modal.dataset.operationPending='true';
    modal.setAttribute('aria-busy','true');
    const notice=modal.querySelector('[data-aw-error]');
    if(notice)notice.textContent='';
    try{
      await action();
      delete modal.dataset.operationPending;
      onSuccess();
    }catch(err){showFieldError(target,err.message);}
    finally {delete modal.dataset.operationPending;modal.removeAttribute('aria-busy');}
  }
  function finish(message){ui.closeModal();refresh();ui.toast(message);}
  function tagsDialog(tags=[...data.tags]) {
    dialog(`<h2>课程标签</h2><div class="ac-modal-body"><form class="aw-inline-form" data-aw-new-tag><label>新标签<input name="tag" required placeholder="标签名称"></label><button class="ac-btn ac-btn-secondary">添加</button></form><div class="aw-tags">${tags.map((t,i)=>`<span>${e(t)}<button type="button" aria-label="移除 ${e(t)}" data-aw-drop-tag="${i}">×</button></span>`).join('')||'<p class="ac-muted">尚未设置课程标签</p>'}</div><p class="ac-inline-error" role="alert" data-aw-error></p></div><footer class="ac-modal-footer"><button type="button" class="ac-btn ac-btn-secondary" data-aw-close>取消</button><button type="button" class="ac-btn ac-btn-primary" data-aw-save-tags>保存标签</button></footer>`,modal=>{
      modal.querySelector('form').onsubmit=event=>{
        event.preventDefault();
        if(modal.dataset.operationPending)return;
        const tag=event.currentTarget.elements.tag.value.trim();
        if(!tag || tags.includes(tag) || Array.from(tag).length>50){showFieldError(event.currentTarget.elements.tag,'请填写 1 至 50 字且尚未添加的标签名称。');return;}
        tagsDialog([...tags,tag]);
      };
      modal.querySelectorAll('[data-aw-drop-tag]').forEach(b=>{b.onclick=()=>{if(!modal.dataset.operationPending)tagsDialog(tags.filter((_,i)=>i!==Number(b.dataset.awDropTag)));};});
      modal.querySelector('[data-aw-save-tags]').onclick=event=>dialogAction(modal,event.currentTarget,()=>mutate({action:'saveTags',tags}),()=>{
        editor.course.tags=editor.course.tags.filter(tag=>data.tags.includes(tag));
        finish('课程标签已保存');
        document.querySelector('[data-aw-tags]')?.focus({preventScroll:true});
      });
    });
  }
  function courseDialog(c,mode) {
    const reviewing=mode==='decide', remove=mode==='unpublish';
    const contents=remove?`<div class="ac-modal-heading"><h2>下架课程</h2><p>${e(c.liveTitle || c.title)} · 在架版本 ${Number(c.liveRevision||c.revision)}</p></div>`:courseDetail(c,scope);
    const controls=reviewing?`<label class="ac-field"><span>退回原因（退回时必填）</span><textarea name="reason" maxlength="1200" placeholder="指出需要修改的材料或评审规则"></textarea></label><footer class="ac-modal-footer"><button class="ac-btn ac-btn-secondary" data-aw-choice="return">退回修改</button><button class="ac-btn ac-btn-primary" data-aw-choice="approve">通过并上架</button></footer>`:remove?'<p class="ac-muted">下架后，学员将无法继续打开这门课程。</p><footer class="ac-modal-footer"><button class="ac-btn ac-btn-secondary" data-aw-close>取消</button><button class="ac-btn ac-btn-primary" data-aw-choice="unpublish">确认下架</button></footer>':'';
    dialog(contents+controls+'<p class="ac-inline-error" role="alert" data-aw-error></p>',modal=>{
      modal.querySelectorAll('[data-aw-choice]').forEach(b=>{b.onclick=()=>{
        const decision=b.dataset.awChoice,reason=modal.querySelector('[name=reason]')?.value.trim()||'';
        if(decision==='return'&&!reason){showFieldError(modal.querySelector('[name=reason]'),'请填写退回原因。');return;}
        const body={action:remove?'unpublish':'reviewCourse',id:c.id,revision:c.revision,decision,reason};
        void dialogAction(modal,b,()=>mutate(body),()=>finish(remove?'课程已下架':decision==='return'?'课程已退回':'课程已通过并上架'));
      };});
    });
  }
  function bind(root) {
    if(!root)return;
    active=true;
    if(historyView){
      legacy.bind(root);
      root.querySelector('[data-aw-current]').onclick=()=>{legacy.deactivate();historyView=false;refresh();void activate();};
      return;
    }
    root.querySelectorAll('[data-aw-reload]').forEach(b=>{b.onclick=activate;});
    if(!data){if(!loading&&!error)void activate();return;}
    if(editor){
      bindEditor(root,editor,{refresh,cancel,icon:ui.icon,manageTags:()=>tagsDialog(),save:async(course,intent)=>{
        await mutate({action:'saveCourse',course,intent});
        editor=null;state=initialFilters();
        ui.toast(intent==='draft'?'草稿已保存':permissions(data).owner?(village?(course.required?'必修课程已发布':'普通任务已发布'):'课程已发布'):'已提交发布审核');
        window.scrollTo({top:0});
      }});return;
    }
    root.querySelectorAll('.aw-progress-person > img').forEach(image=>{
      const showInitial=()=>{
        image.onerror=null;
        const fallback=document.createElement('span');
        fallback.className='avatar avatar-small';
        fallback.setAttribute('aria-hidden','true');
        fallback.textContent=image.parentElement.dataset.initial;
        image.replaceWith(fallback);
      };
      image.onerror=showInitial;
      if(image.complete && image.naturalWidth===0)showInitial();
    });
    const listen=(selector,callback)=>root.querySelectorAll(selector).forEach(button=>{button.onclick=()=>callback(button);});
    listen('[data-aw-new]',village ? onNewPublication : ()=>edit(null));
    listen('[data-aw-learners]',()=>dialog(learnerRoster(data)));
    if(village)listen('[data-aw-reflections]',showReflections);
    listen('[data-aw-legacy]',()=>{historyView=true;refresh();void legacy.activate();});
    listen('[data-aw-tab]',b=>{state={...initialFilters(),tab:b.dataset.awTab};refresh();});
    for(const key of ['detail','edit','decide','unpublish']){
      listen(`[data-aw-${key}]`,b=>{
        const c=data.courses.find(c=>c.id===b.getAttribute('data-aw-'+key));
        if(c){if(key==='edit')edit(c);else courseDialog(c,key);}
      });
    }
    root.querySelectorAll('[data-aw-filter]').forEach(select=>{select.onchange=()=>{state[select.dataset.awFilter]=select.value;refresh();};});
    const search=root.querySelector('[data-aw-search]');
    const filterRows=()=>{
      const rows=[...root.querySelectorAll('[data-aw-searchable]')];
      const query=state.search.trim().toLowerCase();
      rows.forEach(row=>{row.hidden=!row.dataset.awSearchable.includes(query);});
      const noMatch=root.querySelector('[data-aw-no-match]');
      if(noMatch)noMatch.hidden=rows.some(row=>!row.hidden);
    };
    if(search){search.oninput=()=>{state.search=search.value;filterRows();};filterRows();}
  }
  function reset(){closeReflections();epoch++;data=null;historyView=false;active=false;error='';editor=null;requestedRequired=null;permissionsStale=false;suspendedEditors.clear();state=initialFilters();if(!village)legacy.reset();}
  function deactivate(){closeReflections();active=false;if(historyView)legacy.deactivate();}
  function canRefresh(){return historyView?legacy.canRefresh():!editor&&!writing&&!loading;}
  function isBusy(){return Boolean(editor?.busy||writing);}
  function publishingCourse(){return Boolean(editor) || requestedRequired!==null;}
  function currentCourseKind(){
    if(!village || !publishingCourse()) return null;
    return (editor ? editor.course.required : requestedRequired) ? 'required' : 'elective';
  }
  function renderPublishPreview(){return editor ? renderCoursePreview(editor.course,ui.icon) : '';}
  function renderPublishActions(){return editor && data ? renderCourseActions(editor,permissions(data).owner,true) : '';}
  return {publicationCourse:()=>editor?.course,render,bind,activate,refreshPermissions,startPublishing,resumePublishing,showCourseList,publishingCourse,currentCourseKind,renderPublishPreview,renderPublishActions,deactivate,reset,canRefresh,isBusy};
}
