import { taskDepartments, type TaskDepartmentFilter } from "./taskDepartments";

/** Map landmarks to publishing departments, never task direction or badge type. */
export function worldMapTaskDepartment(name: unknown): TaskDepartmentFilter | null {
  if (name === "交付线") return "delivery";
  return taskDepartments.find(item => !item.delivery && item.name === name)?.id ?? null;
}

// Added only to the novice village's map document. The original map geometry
// and its close/back interactions remain untouched for the other modules.
export const worldMapTaskBridge = `(()=>{
  const selector='.planet-detail .detail-return';
  const label='查看相关任务 →';
  let village=true;
  const sync=()=>{
    const button=document.querySelector(selector);
    const text=village?label:'返回地图';
    if(button && button.textContent!==text)button.textContent=text;
  };
  addEventListener('message',event=>{
    if(event.source!==parent||event.data?.type!=='journey-world-map-context')return;
    village=event.data.village===true;sync();
  });
  new MutationObserver(sync).observe(document.body,{childList:true,subtree:true});
  sync();
  document.addEventListener('click',event=>{
    if(!village)return;
    if(!(event.target instanceof Element)||!event.target.closest(selector))return;
    const department=document.querySelector('#planet-detail-title')?.textContent?.trim();
    if(!department)return;
    event.preventDefault();event.stopImmediatePropagation();
    const navigate=()=>parent.postMessage({type:'journey-world-map-tasks',department},'*');
    if(document.fullscreenElement)document.exitFullscreen().then(navigate,navigate);
    else navigate();
  },true);
})();`;

export const worldMapSharedTaskBridge = worldMapTaskBridge.replace('let village=true', 'let village=false');
