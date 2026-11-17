export const EXPLORATION_CONFIGURATION_NOTICE = '探索营任务仅限超级管理员填写和发布。';

export function canConfigureTask(task, isSuperAdmin) {
  return task?.camp !== 'exploration' || isSuperAdmin === true;
}

export function requireTaskConfiguration(task, isSuperAdmin, savedTask) {
  if (!canConfigureTask(task, isSuperAdmin) || !canConfigureTask(savedTask, isSuperAdmin)) {
    throw new Error(EXPLORATION_CONFIGURATION_NOTICE);
  }
}
