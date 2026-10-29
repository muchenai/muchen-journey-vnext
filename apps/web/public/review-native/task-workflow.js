// Compare editable content only, excluding versions, statistics and browser timestamps.
const fields = ['title','summary','camp','domain','difficulty','unlockTaskPoints','badges','materials','reviewMode','passScore','rubric','rubricAttachments'];
export function editableContent(task) {
  return Object.fromEntries(fields.map(key => [key, task[key] ?? (key==='unlockTaskPoints' ? 0 : ['badges','materials','rubric','rubricAttachments'].includes(key) ? [] : '')]));
}
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key,canonical(value[key])]));
  return value;
}
export function hasUnsavedChanges(task, saved, empty) {
  return JSON.stringify(canonical(editableContent(task))) !== JSON.stringify(canonical(editableContent(saved || empty)));
}
export function isTaskUpdate(task) { return Number(task.version || 0) > 0 || !!task.versionId; }
export function copyAsNewTask(task, empty) {
  return {...empty, ...structuredClone(editableContent(task)), id:empty.id, revision:0, status:'draft'};
}
export function createTaskWorkflow({store,newDraft,openModal,closeModal,showEditor,toast}) {
  function replace(next) {
    const before = store.data.draft;
    store.data.draft = next;
    try { store.save(); } catch (error) { store.data.draft=before; throw error; }
    closeModal(); showEditor();
  }
  function start(copy) {
    const draft=store.data.draft;
    const empty=newDraft();
    const next=copy ? copyAsNewTask(copy,empty) : empty;
    const proceed=()=>{replace(next);toast(copy ? '已复制为新任务，请编辑后发布' : '已打开新任务表单');};
    if (!hasUnsavedChanges(draft,store.getTask(draft.id),empty)) {
      try {proceed();} catch(error) {toast(error.message,'error');}
      return;
    }
    openModal(`<div class="modal-heading"><h2>${copy ? '复制为新任务' : '新建任务'}</h2><p>当前编辑内容尚未保存到任务库。是否保存草稿后继续？已发布版本会继续供学员查看。</p></div><p class="inline-error" data-new-error hidden role="alert"></p><div class="modal-actions"><button class="btn btn-secondary" data-new-cancel>继续编辑</button><button class="btn btn-secondary" data-new-discard>放弃修改并新建</button><button class="btn btn-primary" data-new-save>保存草稿并新建</button></div>`,modal=>{
      modal.querySelector('[data-new-cancel]').onclick=closeModal;
      modal.querySelector('[data-new-discard]').onclick=()=>{try{proceed();}catch(error){toast(error.message,'error');}};
      modal.querySelector('[data-new-save]').onclick=async()=>{
        if(modal.dataset.operationPending==='true')return;
        modal.dataset.operationPending='true';
        modal.querySelectorAll('button').forEach(button=>button.disabled=true);
        try {await store.saveTask(structuredClone(draft));modal.dataset.operationPending='false';proceed();}
        catch(error){
          modal.dataset.operationPending='false';modal.querySelectorAll('button').forEach(button=>button.disabled=false);
          const message=modal.querySelector('[data-new-error]');message.textContent=error.message;message.hidden=false;
        }
      };
    });
  }
  return {start};
}
