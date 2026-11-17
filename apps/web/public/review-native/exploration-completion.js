import {isMaterialLink} from './material-validation.js';

export const EXPLORATION_COMPLETION_MODES = [
  {id:'learning',label:'阅读学习',description:'学员打开学习材料后即可完成，继续下一板块，无需填写作文或提交审核。'},
  {id:'assessment',label:'学习并做任务',description:'学员阅读学习材料，下载任务文件完成其中的题目，再提交成果供审核。'},
  {id:'checkin',label:'培训签退',description:'学员确认已进入项目群后完成签退，无需作文或审核。'},
];
export function explorationCompletionMode(task={}) {
  return task.camp==='exploration'&&EXPLORATION_COMPLETION_MODES.some(mode=>mode.id===task.completionMode)?task.completionMode:'assessment';
}
export function requiresTaskAssessment(task={}) {
  return task.camp!=='exploration'||explorationCompletionMode(task)==='assessment';
}
export function taskCompletionLabel(task={}) {
  if(task.camp!=='exploration')return task.reviewMode==='ai'?'AI 自测':'人工审核';
  return EXPLORATION_COMPLETION_MODES.find(mode=>mode.id===explorationCompletionMode(task)).label;
}
export function validAssessmentUrl(value) {
  if(!String(value||'').trim())return true;
  if(String(value).trim().length>2048)return false;
  try {const url=new URL(String(value).trim());return url.protocol==='https:'&&!url.username&&!url.password;} catch {return false;}
}
export function explorationTaskFiles(task = {}) {
  return task.camp === 'exploration' && requiresTaskAssessment(task) && Array.isArray(task.taskFiles) ? task.taskFiles : [];
}
export function hasExplorationTaskResource(task = {}) {
  return explorationTaskFiles(task).length > 0 || (!!String(task.assessmentUrl || '').trim() && validAssessmentUrl(task.assessmentUrl));
}
export function explorationTaskResourceErrors(task = {}) {
  if(task.camp !== 'exploration' || !requiresTaskAssessment(task))return [];
  const errors=[], files=explorationTaskFiles(task);
  if(!hasExplorationTaskResource(task))errors.push('请上传任务文件，或填写已有的测试链接');
  if(!validAssessmentUrl(task.assessmentUrl))errors.push('培训测试链接需为有效的 HTTPS 地址');
  if(files.length>20)errors.push('每个任务最多添加 20 份任务文件');
  files.forEach((file,index)=>{
    const name=String(file.name||'').trim(), nameLimit=file.type==='link'?160:240;
    if(!name)errors.push(`请填写任务文件 ${index+1} 的名称`);
    if(name.length>nameLimit)errors.push(`任务文件 ${index+1} 的名称不能超过 ${nameLimit} 字`);
    if(!['link','file','image','text'].includes(file.type))errors.push(`任务文件 ${index+1} 的类型无效`);
    if(file.type==='link'&&!isMaterialLink(file.url))errors.push(`任务文件 ${index+1} 需填写有效的 HTTPS 链接，不能包含账号或密码`);
    if(['file','image'].includes(file.type)&&(!Number.isSafeInteger(file.size)||file.size<1||file.size>100*1024*1024))errors.push(`任务文件 ${index+1} 需为非空且不超过 100 MB 的文件`);
  });
  return errors;
}
// Publishing review confirms every external resource, including legacy test links.
export function taskResourceLinks(task = {}) {
  return [...new Set([
    ...(task.materials || []).filter(item => item.type === 'link').map(item => item.url),
    ...explorationTaskFiles(task).filter(item => item.type === 'link').map(item => item.url),
    ...(task.camp === 'exploration' && requiresTaskAssessment(task) && String(task.assessmentUrl || '').trim() ? [String(task.assessmentUrl).trim()] : []),
  ])];
}
