export const validExplorationOrder = value => Number.isInteger(value) && value >= 1 && value <= 9999;

export const isPinnedExplorationTask = task => task?.camp === 'exploration'
  && (task.pinnedLast === true || task.stableKey === 'EXPLORATION-DYNAMIC-20261117-08');

const publishedExplorationTasks = tasks => tasks.filter(task => task.camp === 'exploration'
  && task.status !== 'archived' && (task.status === 'published' || validExplorationOrder(task.publishedOrder)));

export function nextExplorationOrder(tasks = []) {
  const published = publishedExplorationTasks(tasks);
  // The fixed sign-out task follows every ordinary task, including older tasks
  // whose stored positions were once after it. New tasks insert before sign-out.
  if (published.some(isPinnedExplorationTask)) return Math.min(9999, published.length);
  const highest = published
    .reduce((maximum, task) => validExplorationOrder(task.publishedOrder ?? task.order) ? Math.max(maximum, task.publishedOrder ?? task.order) : maximum, 0);
  return Math.min(9999, highest + 1);
}

export function explorationDisplayOrder(task, tasks = []) {
  const requested = task.order ?? 1;
  if (!validExplorationOrder(requested)) return null;
  const others = publishedExplorationTasks(tasks).filter(row => row.id !== task.id);
  return others.some(isPinnedExplorationTask) ? Math.min(requested, nextExplorationOrder(others)) : requested;
}
