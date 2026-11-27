export function canEditTask(task, store) {
  return Boolean(task && store.operatorId && (store.capabilities?.isSuperAdmin === true || task.authorId === store.operatorId));
}

export function taskAvailabilityError(task, store) {
  if (!task) return '任务不存在，请刷新任务库。';
  if (task.camp === 'exploration' && !store.capabilities?.isSuperAdmin) return '探索营任务仅限超级管理员归档、恢复或删除。';
  if (!canEditTask(task, store)) return '当前账号没有管理此任务的权限。';
  return '';
}
