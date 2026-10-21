// Shared display names for learner stages and review views. Stable keys remain unchanged.
export const learnerTaskTitles = Object.freeze({
  'DAY-0': 'Day 1｜启程-公司基础介绍材料',
  'TRE-001-COMPANY-VALUES': '宝藏一｜公司价值',
  'TRE-002-AI-DATA-BASICS': '宝藏二/AI与数据基础',
  'TRE-003-PROJECT-AWARENESS': '宝藏三/项目认知',
  'TRE-004-DELIVERY-FIT': '宝藏四/交付边界',
  'ASM-001-RULE-BREAKDOWN': '评测一/规则拆解',
  'ASM-002-MODEL-JUDGEMENT': '评测二/模型判断',
  'ASM-003-DATA-CONSTRUCTION': '评测三/数据构造',
});
export function learnerTaskTitle(stableKey, fallback) {
  return Object.hasOwn(learnerTaskTitles, stableKey) ? learnerTaskTitles[stableKey] : fallback;
}
