import {canConfigureTask, EXPLORATION_CONFIGURATION_NOTICE} from './task-publication-access.js';
// Compare editable content only, excluding versions, statistics and browser timestamps.
import { nextExplorationOrder } from './exploration-order.js';
const fields = ['title','summary','camp','domain','publishingDepartment','difficulty','unlockTaskPoints','badges','materials','reviewMode','passScore','rubric','rubricAttachments'];
export function editableContent(task) {
  const editable = task.camp === 'exploration' ? [...fields, 'order','completionMode','assessmentUrl','taskFiles'] : fields;
  return Object.fromEntries(editable.map(key => [key, task[key] ?? (key==='completionMode'?'assessment':key==='unlockTaskPoints' ? 0 : ['badges','materials','rubric','rubricAttachments','taskFiles'].includes(key) ? [] : '')]));
}
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key,canonical(value[key])]));
  return value;
}
export function hasUnsavedChanges(task, saved, empty) {
  return JSON.stringify(canonical(editableContent(task))) !== JSON.stringify(canonical(editableContent(saved || empty)));
}
export function isTaskUpdate(task) {
  if (!task) return false;
  // A saved draft also has a versionId. Only publication evidence makes it an update.
  return Number(task.version || 0) > 0 || Number(task.publishedVersion || 0) > 0
    || !!String(task.publishedVersionId || '').trim() || task.status === 'published'
    || !!String(task.publishedAt || '').trim();
}
function unpublishedDraft(task) {
  const draft = {...structuredClone(task), revision:0, version:0, status:'draft', participants:0, completions:0};
  for (const field of ['versionId','publishedVersionId','publishedVersion','publishedAt','publishedOrder','publication','sourceTaskId','stableKey']) delete draft[field];
  return draft;
}
export function copyAsNewTask(task, empty) {
  const copy = unpublishedDraft({...empty, ...structuredClone(editableContent(task)), id:empty.id});
  for(const field of ['version','participants','completions','authorId']) delete copy[field];
  if (task.camp === 'exploration') copy.order = empty.order ?? 1;
  return copy;
}
export function createTaskWorkflow({store,newDraft,openModal,closeModal,showEditor,toast}) {
  let transitionPending = false;
  function freshDraft() {
    const empty=unpublishedDraft(newDraft());
    if (!empty.id || empty.id===store.data.draft?.id || store.getTask(empty.id)?.id===empty.id) empty.id=crypto.randomUUID();
    return empty;
  }
  async function replace(next, ready) {
    const before = store.data.draft;
    store.data.draft = next;
    try { const pending=store.save(); if(pending?.then)await pending; }
    catch (error) { if(store.data.draft===next)store.data.draft=before; throw error; }
    ready?.();
    closeModal(); showEditor();
  }
  async function start(copy) {
    if (transitionPending) return;
    if (!canConfigureTask(copy, store.capabilities?.isSuperAdmin)) { toast(EXPLORATION_CONFIGURATION_NOTICE, 'error'); return; }
    const draft=store.data.draft;
    const empty=freshDraft();
    const next=copy ? copyAsNewTask(copy,copy.camp==='exploration'?{...empty,order:nextExplorationOrder(store.data.tasks)}:empty) : empty;
    const proceed=async modal=>{
      if(transitionPending)return;
      transitionPending=true;
      try { await replace(next,()=>{if(modal)modal.dataset.operationPending='false';});toast(copy ? '已复制为新任务，请编辑后发布' : '已打开新任务表单'); }
      finally { transitionPending=false; }
    };
    if (!canConfigureTask(draft, store.capabilities?.isSuperAdmin) || !hasUnsavedChanges(draft,store.getTask(draft.id),empty)) {
      try {await proceed();} catch(error) {toast(error.message,'error');}
      return;
    }
    openModal(`<div class="modal-heading"><h2>${copy ? '复制为新任务' : '新建任务'}</h2><p>当前编辑内容尚未保存到任务库。是否保存草稿后继续？已发布版本会继续供学员查看。</p></div><p class="inline-error" data-new-error hidden role="alert"></p><div class="modal-actions"><button class="btn btn-secondary" data-new-cancel>继续编辑</button><button class="btn btn-secondary" data-new-discard>放弃修改并新建</button><button class="btn btn-primary" data-new-save>保存草稿并新建</button></div>`,modal=>{
      modal.querySelector('[data-new-cancel]').onclick=closeModal;
      modal.querySelector('[data-new-discard]').onclick=async()=>{
        if(modal.dataset.operationPending==='true')return;
        modal.dataset.operationPending='true';modal.querySelectorAll('button').forEach(button=>button.disabled=true);
        try {await proceed(modal);}
        catch(error){modal.dataset.operationPending='false';modal.querySelectorAll('button').forEach(button=>button.disabled=false);const message=modal.querySelector('[data-new-error]');message.textContent=error.message;message.hidden=false;}
      };
      modal.querySelector('[data-new-save]').onclick=async()=>{
        if(modal.dataset.operationPending==='true')return;
        modal.dataset.operationPending='true';
        modal.querySelectorAll('button').forEach(button=>button.disabled=true);
        try {await store.saveTask(structuredClone(draft));await proceed(modal);}
        catch(error){
          modal.dataset.operationPending='false';modal.querySelectorAll('button').forEach(button=>button.disabled=false);
          const message=modal.querySelector('[data-new-error]');message.textContent=error.message;message.hidden=false;
        }
      };
    });
  }
  async function resetAfterPublish() {
    // The committed task stays in the library; the editor starts a separate task.
    store.data.draft=freshDraft();
    const pending=store.save();
    if(pending?.then)await pending;
  }
  return {start,resetAfterPublish};
}
