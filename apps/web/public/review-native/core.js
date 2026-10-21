/** JOURNEY prototype domain model. All persistence stays in this browser. */
export const BADGES = Object.freeze([
  { id: 'data', name: '数据交付徽章', category: '数据交付', color: '#648b83' },
  { id: 'dev', name: '技术开发徽章', category: '技术开发', color: '#6b83a0' },
  { id: 'product', name: '产品开发徽章', category: '产品开发', color: '#b68c58' },
  { id: 'pmo', name: 'PMO勋徽章', category: 'PMO', color: '#9988ad' },
  { id: 'evaluation', name: 'AI评测徽章', category: 'AI评测', color: '#748b9a' },
  { id: 'quality', name: '质量检测徽章', category: '质量检测', color: '#a58b74' },
  { id: 'project', name: '项目管理徽章', category: '项目管理', color: '#7d9172' },
  { id: 'ai', name: 'AI 能力徽章', category: 'AI 能力', color: '#8d85a9' },
]);

export const DIFFICULTY_PRESETS = Object.freeze([
  Object.freeze({ name: '入门', xp: 50, minutes: 30, taskPoints: 5 }),
  Object.freeze({ name: '进阶', xp: 100, minutes: 60, taskPoints: 10 }),
  Object.freeze({ name: '挑战', xp: 200, minutes: 90, taskPoints: 20 }),
]);

export const FAILURE_REASONS = Object.freeze([
  { id: 'materials_incomplete', label: '提交材料不完整' },
  { id: 'incorrect_answer', label: '答案错误' },
  { id: 'requirements_not_met', label: '未达到任务要求' },
  { id: 'insufficient_evidence', label: '依据或论证不足' },
  { id: 'other', label: '其他' },
]);

export const REVIEW_CAMPS = Object.freeze([
  { id: 'exploration', label: '探索营' },
  { id: 'novice', label: '新手村' },
]);

export const CERTIFICATION_LEVELS = Object.freeze([
  { value: 1, name: '初级', difficulty: '入门' },
  { value: 2, name: '中级', difficulty: '进阶' },
  { value: 3, name: '高级', difficulty: '挑战' },
]);

export function normalizeCertificationRole(role) {
  const value = String(role ?? '').trim();
  return value === '导师' ? '管理系统的管理员' : (value || 'NPC');
}

export function getCertificationLevel(value) {
  const raw = String(value ?? '').trim();
  const numeric = raw.match(/^L?([123])$/i);
  return CERTIFICATION_LEVELS.find(level => numeric ? level.value === Number(numeric[1]) : level.name === raw) || null;
}

const RULES_VERSION = 'difficulty-v1';

/** Difficulty is the only configurable source of time and reward values. */
export function applyDifficultyPreset(task = {}) {
  const preset = DIFFICULTY_PRESETS.find(item => item.name === task.difficulty);
  return preset
    ? { ...task, minutes: preset.minutes, xp: preset.xp, taskPoints: preset.taskPoints, rulesVersion: RULES_VERSION }
    : { ...task };
}

const STORAGE_KEY = 'journey_admin_v1';
const clone = value => JSON.parse(JSON.stringify(value));
const now = () => new Date().toISOString();
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const round = value => Math.round((value + Number.EPSILON) * 1e8) / 1e8;
const uid = prefix => `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
const text = value => String(value ?? '').trim();
const isNumeric = value => value !== null && value !== undefined && text(value) !== '' && Number.isFinite(Number(value));

export function getReviewCamp(submission = {}, task = {}) {
  const value = text(submission.camp) || text(task.camp);
  return REVIEW_CAMPS.find(camp => camp.id === value || camp.label === value)?.id || 'novice';
}

/** Derive display state without migrating or guessing missing historical data. */
export function getSubmissionStatus(submission = {}, task = {}) {
  if (submission.status === 'passed' || submission.rewarded) return 'passed';
  const mode = submission.reviewMode || task.reviewMode;
  if (mode !== 'ai') return submission.status === 'returned' ? 'returned' : 'pending';
  const actualScore = value => (typeof value === 'number' || typeof value === 'string') && isNumeric(value);
  const rawScore = actualScore(submission.ai?.score) ? submission.ai.score : submission.finalScore;
  if (!actualScore(rawScore)) return 'evaluating';
  if (['ai_failed', 'returned'].includes(submission.status)) return 'ai_failed';
  if (typeof submission.ai?.passed === 'boolean') return submission.ai.passed ? 'passed' : 'ai_failed';
  const passScore = isNumeric(task.passScore) ? Number(task.passScore) : 60;
  return Number(rawScore) >= passScore ? 'passed' : 'ai_failed';
}

export function getSubmissionFailureReasons(submission = {}, task = {}) {
  const saved = Array.isArray(submission.failureReasons) ? submission.failureReasons : submission.ai?.failureReasons;
  if (!Array.isArray(saved)) return [];
  return [...new Set(saved.filter(code => FAILURE_REASONS.some(reason => reason.id === code)))];
}

function validateFailureReasons(reasonCodes) {
  if (!Array.isArray(reasonCodes) || !reasonCodes.length) throw new Error('请至少选择一个不通过原因');
  if (reasonCodes.some(code => !FAILURE_REASONS.some(reason => reason.id === code))) throw new Error('请选择有效的不通过原因');
  return [...new Set(reasonCodes)];
}

function fieldLimits(task = {}) {
  const errors = [];
  if (text(task.title).length > 80) errors.push('任务标题不能超过 80 字');
  if (text(task.summary).length > 500) errors.push('任务简述不能超过 500 字');
  return errors;
}

export function escapeHtml(value = '') {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

export function rewardBreakdown(task = {}) {
  if (Object.hasOwn(task, 'difficulty') && !DIFFICULTY_PRESETS.some(item => item.name === task.difficulty)) {
    throw new Error('请选择入门、进阶或挑战难度');
  }
  // Ledger snapshots without difficulty retain the values originally awarded.
  const effective = applyDifficultyPreset(task);
  const xp = Math.max(0, number(effective.xp));
  if (!Object.hasOwn(task, 'difficulty') && Array.isArray(task.allocations)) {
    return {
      xp,
      taskPoints: Math.max(0, number(task.taskPoints)),
      totalPoints: isNumeric(task.totalPoints) ? Math.max(0, number(task.totalPoints)) : round(task.allocations.reduce((sum, item) => sum + number(item.points), 0)),
      allocations: clone(task.allocations),
    };
  }
  const totalPoints = round(xp / 10);
  return {
    xp,
    taskPoints: Math.max(0, number(effective.taskPoints)),
    totalPoints,
    allocations: (task.badges || []).map(item => ({
      id: item.id,
      name: BADGES.find(badge => badge.id === item.id)?.name || item.id,
      weight: number(item.weight),
      points: round(totalPoints * number(item.weight) / 100),
    })),
  };
}

export function validateTask(task = {}) {
  const errors = fieldLimits(task);
  if (!text(task.title)) errors.push('请填写任务标题');
  if (!text(task.summary)) errors.push('请填写任务简述');
  if (!text(task.domain)) errors.push('请选择任务方向');
  if (!DIFFICULTY_PRESETS.some(item => item.name === task.difficulty)) errors.push('请选择入门、进阶或挑战难度');

  const badges = Array.isArray(task.badges) ? task.badges : [];
  if (badges.length < 1 || badges.length > 2) errors.push('每个任务需选择 1～2 个徽章');
  if (new Set(badges.map(badge => badge.id)).size !== badges.length) errors.push('不能重复选择同一徽章');
  if (badges.some(badge => !BADGES.some(option => option.id === badge.id))) errors.push('请选择系统已有的徽章');
  if (badges.some(badge => !Number.isFinite(Number(badge.weight)) || Number(badge.weight) <= 0 || Number(badge.weight) > 100)) errors.push('每个徽章的占比需大于 0% 且不超过 100%');
  if (Math.abs(badges.reduce((sum, badge) => sum + number(badge.weight), 0) - 100) > 0.000001) errors.push('徽章占比合计需为 100%');

  const materials = Array.isArray(task.materials) ? task.materials : [];
  if (!materials.length) errors.push('请至少添加一份学习材料');
  materials.forEach((material, index) => {
    if (!text(material.name)) errors.push(`请填写材料 ${index + 1} 的名称`);
    if (!['link', 'file', 'image'].includes(material.type)) errors.push(`材料 ${index + 1} 的类型无效`);
    if (material.type === 'link') {
      try {
        const url = new URL(material.url);
        if (!['http:', 'https:'].includes(url.protocol)) throw new Error();
      } catch { errors.push(`材料 ${index + 1} 需填写有效的 http 或 https 链接`); }
    }
  });
  if (!['manual', 'ai'].includes(task.reviewMode)) errors.push('请选择人工审核或 AI 自测');
  if (task.reviewMode === 'ai') {
    const rubric = Array.isArray(task.rubric) ? task.rubric : [];
    if (!rubric.length) errors.push('请至少配置一个评分维度');
    rubric.forEach((dimension, index) => {
      if (!text(dimension.name)) errors.push(`请填写评分维度 ${index + 1} 的名称`);
      if (!Number.isFinite(Number(dimension.points)) || Number(dimension.points) <= 0) errors.push(`评分维度 ${index + 1} 的分值需大于 0`);
      if (!text(dimension.description)) errors.push(`请填写评分维度 ${index + 1} 的评分描述`);
    });
    if (Math.abs(rubric.reduce((sum, dimension) => sum + number(dimension.points), 0) - 100) > 0.000001) errors.push('评分维度总分需为 100 分');
    if (!isNumeric(task.passScore) || Number(task.passScore) < 0 || Number(task.passScore) > 100) errors.push('通过分数需在 0～100 分之间');
  }
  return errors;
}

/** A deterministic UI demonstration, never a live model evaluation. */
export function gradeAnswer(task = {}, answer = '') {
  if (task.reviewMode !== 'ai') throw new Error('无固定答案的任务采用人工审核，不进行 AI 评测');
  const value = text(answer);
  const rubric = Array.isArray(task.rubric) ? task.rubric : [];
  const length = value.replace(/\s/g, '').length;
  const structure = (value.match(/\n|[一二三四五六七八九][、.]|\d+[、.．)]|首先|其次|最后|结论|建议/g) || []).length;
  const evidence = (value.match(/数据|用户|反馈|指标|验证|测试|原因|分析|方案|风险|目标|优先级|需求|实现|质量|计划/g) || []).length;
  const base = length === 0 ? 0 : Math.min(97, 28 + Math.min(45, length / 7) + Math.min(12, structure * 3) + Math.min(12, evidence * 2));
  const dimensions = rubric.map((dimension, index) => {
    const max = number(dimension.points);
    const adjustment = length ? [0, 2, -2, 1][index % 4] : 0;
    const score = Math.round(max * Math.max(0, Math.min(100, base + adjustment)) / 100 * 10) / 10;
    const ratio = max ? score / max : 0;
    return {
      name: dimension.name,
      score,
      max,
      comment: ratio >= 0.8 ? '回答较完整，有清晰的结构和支撑信息。' : ratio >= 0.6 ? '已覆盖部分要求，可补充依据、执行步骤与验证方式。' : '内容较少，请结合材料补充分析与具体产出。',
    };
  });
  const score = Math.round(dimensions.reduce((sum, dimension) => sum + dimension.score, 0) * 10) / 10;
  const passed = score >= number(task.passScore ?? 60);
  const lowDimensions = dimensions.filter(dimension => dimension.max > 0 && dimension.score / dimension.max < 0.8);
  const suggestions = (lowDimensions.length ? lowDimensions : dimensions).slice().sort((a, b) => a.score / (a.max || 1) - b.score / (b.max || 1)).slice(0, 3).map(dimension => {
    const criterion = rubric.find(item => item.name === dimension.name)?.description;
    return `「${dimension.name}」${dimension.score}/${dimension.max} 分：请按以下要求补充交付：${text(criterion) || '补充材料依据、分析过程和可执行的验证方式。'}`;
  });
  const improvementSuggestions = passed ? '' : suggestions.join('\n') || '请对照任务要求补充完整产出，并说明材料依据、执行步骤和验证方式。';
  return {
    score,
    passed,
    comment: `演示评分：根据回答完整度、结构与关键词生成可复现结果，未调用真实 AI。${passed ? '本次达到通过分数。' : '建议补充材料依据、执行方案和验收指标后再试。'}`,
    dimensions,
    failureReasons: passed ? [] : ['requirements_not_met'],
    improvementSuggestions,
    source: 'demo',
  };
}

function standardRubric(prefix = 'rubric') {
  return [
    { id: `${prefix}-1`, name: '问题理解', points: 25, description: '准确理解任务目标，清晰界定问题、对象与约束。' },
    { id: `${prefix}-2`, name: '分析与依据', points: 30, description: '结合给定材料和数据展开分析，论据具体且结论合理。' },
    { id: `${prefix}-3`, name: '方案可行性', points: 30, description: '方案可执行，包含具体步骤、验收标准与风险考虑。' },
    { id: `${prefix}-4`, name: '表达与交付', points: 15, description: '内容结构清晰，交付完整，表达简洁且便于阅读。' },
  ];
}

function createSeed() {
  const feedbackUrl = new URL('./samples/user-feedback.html', globalThis.location?.href || 'http://localhost/').href;
  const guideUrl = new URL('./samples/task-guide.html', globalThis.location?.href || 'http://localhost/').href;
  const draft = {
    id: 'draft-current',
    title: '从用户反馈到产品改进方案',
    summary: '阅读一组真实场景的用户反馈，识别核心问题，完成一份有依据、可落地的产品改进方案。',
    domain: '产品开发', difficulty: '进阶',
    badges: [{ id: 'product', weight: 60 }, { id: 'data', weight: 40 }],
    materials: [
      { id: 'draft-material-1', name: '用户访谈与反馈记录', type: 'link', url: feedbackUrl },
      { id: 'draft-material-2', name: '产品使用数据与转化漏斗.pdf', type: 'file', url: '', size: 1245184 },
      { id: 'draft-material-3', name: '当前产品关键页面.png', type: 'image', url: '', size: 348160 },
    ],
    questions: [
      { id: 'draft-question-1', title: '识别用户的核心问题', description: '结合用户反馈和使用数据，提炼 3 个核心问题。为每个问题列出材料依据，并说明你的优先级判断。', submission: 'text', required: true },
      { id: 'draft-question-2', title: '设计产品改进方案', description: '选择一个优先解决的问题，提交改进方案。需包含目标用户、解决思路、关键流程、验收指标和风险；可附流程图或低保真原型。', submission: 'both', required: true },
    ],
    rubric: [
      { id: 'draft-rubric-1', name: '问题洞察', points: 30, description: '能从反馈和数据中识别真实用户问题，区分现象与原因，优先级有明确依据。' },
      { id: 'draft-rubric-2', name: '方案设计', points: 35, description: '方案与核心问题对应，关键流程完整，兼顾用户价值与实现成本。' },
      { id: 'draft-rubric-3', name: '数据与验证', points: 20, description: '引用具体材料，提出可量化的成功指标与可执行的验证计划。' },
      { id: 'draft-rubric-4', name: '交付表达', points: 15, description: '产出结构清晰，逻辑连贯，图文表达准确且便于团队理解。' },
    ],
    rubricAttachments: [], reviewMode: 'manual', passScore: 60, status: 'draft',
    author: '林若晴', updatedAt: '2026-10-19T01:20:00.000Z', participants: 0, completions: 0,
  };
  const taskSpecs = [
    ['task-001', '用户访谈：找到真正的问题', '从访谈记录中提炼需求，区分用户描述与真实问题，完成洞察卡片。', '产品开发', '入门', [{ id: 'product', weight: 70 }, { id: 'data', weight: 30 }], 'manual', '林若晴', 36, 28],
    ['task-002', '搭建你的第一个 REST API', '实现一个任务列表接口，完成参数校验、错误处理与接口文档。', '技术开发', '进阶', [{ id: 'dev', weight: 80 }, { id: 'quality', weight: 20 }], 'manual', '陈知远', 24, 16],
    ['task-003', '数据清洗与交付检查', '清洗一份销售数据，输出质量报告，并按照交付清单完成验收。', '数据交付', '入门', [{ id: 'data', weight: 60 }, { id: 'quality', weight: 40 }], 'ai', '周予安', 58, 47],
    ['task-004', '为项目制定一份风险清单', '识别项目中的关键风险，为风险设定责任人、触发条件和应对措施。', 'PMO', '进阶', [{ id: 'pmo', weight: 60 }, { id: 'project', weight: 40 }], 'manual', '许嘉宁', 19, 12],
    ['task-005', '让 AI 回答有据可依', '改写提示词，设计对照测试，并用评测标准验证回答质量的提升。', 'AI评测', '进阶', [{ id: 'evaluation', weight: 60 }, { id: 'ai', weight: 40 }], 'ai', '宋一禾', 42, 35],
    ['task-006', '从需求到测试用例', '从产品需求提取测试点，覆盖主流程、边界条件与异常路径。', '质量检测', '入门', [{ id: 'quality', weight: 100 }], 'ai', '陈知远', 31, 22],
    ['task-007', '设计一个可执行的里程碑计划', '拆解项目目标，建立工作依赖与里程碑，完成资源和进度安排。', '项目管理', '挑战', [{ id: 'project', weight: 70 }, { id: 'pmo', weight: 30 }], 'manual', '许嘉宁', 16, 9],
    ['task-008', '构建你的 AI 工作流', '把一个重复工作拆成可复用流程，明确 AI、人和工具的协作边界。', 'AI 能力', '进阶', [{ id: 'ai', weight: 70 }, { id: 'dev', weight: 30 }], 'ai', '宋一禾', 27, 21],
  ];
  const tasks = taskSpecs.map((spec, index) => {
    const [id, title, summary, domain, difficulty, badges, reviewMode, author, participants, completions] = spec;
    return {
      id, title, summary, domain, difficulty, badges, reviewMode, author, participants, completions,
      materials: [
        { id: `${id}-material-1`, name: `${domain} · 任务背景与案例`, type: 'link', url: guideUrl },
        { id: `${id}-material-2`, name: `${domain}学习资料.pdf`, type: 'file', url: '', size: 860160 + index * 61440 },
      ],
      questions: [{ id: `${id}-question-1`, title: '完成任务并提交你的产出', description: `${summary}请说明分析过程、关键决策和验证方法；可附交付文件。`, submission: 'both', required: true }],
      rubric: standardRubric(id), rubricAttachments: [], passScore: 60, status: 'published',
      updatedAt: `2026-10-${String(18 - index).padStart(2, '0')}T02:30:00.000Z`,
    };
  });
  Object.assign(draft, applyDifficultyPreset(draft));
  tasks.forEach(task => Object.assign(task, applyDifficultyPreset(task)));
  const learners = [
    { id: 'student-001', name: '张晓雨', avatar: '晓', cohort: '第 08 期 · 产品方向', xp: 1280, taskPoints: 240, badges: { data: 86.4, dev: 12, product: 138.6, pmo: 0, evaluation: 25, quality: 35, project: 10, ai: 48 } },
    { id: 'student-002', name: '李明哲', avatar: '明', cohort: '第 08 期 · 开发方向', xp: 980, taskPoints: 180, badges: { data: 24, dev: 116, product: 18, pmo: 0, evaluation: 32, quality: 76, project: 12, ai: 64 } },
    { id: 'student-003', name: '王可欣', avatar: '可', cohort: '第 08 期 · 数据方向', xp: 1560, taskPoints: 320, badges: { data: 214, dev: 18, product: 56, pmo: 12, evaluation: 88, quality: 104, project: 24, ai: 92 } },
    { id: 'student-004', name: '赵子涵', avatar: '涵', cohort: '第 08 期 · PMO 方向', xp: 760, taskPoints: 160, badges: { data: 10, dev: 0, product: 24, pmo: 94, evaluation: 12, quality: 18, project: 112, ai: 30 } },
    { id: 'student-005', name: '刘思远', avatar: '远', cohort: '第 08 期 · AI 方向', xp: 2100, taskPoints: 410, badges: { data: 60, dev: 82, product: 34, pmo: 0, evaluation: 126, quality: 70, project: 26, ai: 308 } },
    { id: 'student-006', name: '陈安然', avatar: '安', cohort: '第 08 期 · 产品方向', xp: 640, taskPoints: 120, badges: { data: 28, dev: 0, product: 74, pmo: 8, evaluation: 24, quality: 12, project: 16, ai: 18 } },
  ];
  learners.forEach(learner => { learner.badgeLevels = Object.fromEntries(BADGES.map(badge => [badge.id, Math.min(3, Math.floor(number(learner.badges[badge.id]) / 100))])); });
  const submissionSpecs = [
    ['submission-001', 'task-001', 'student-001', 86, 'pending', '2026-10-19T02:42:00.000Z'],
    ['submission-002', 'task-002', 'student-002', 78, 'pending', '2026-10-19T02:18:00.000Z'],
    ['submission-003', 'task-004', 'student-004', 91, 'pending', '2026-10-19T01:56:00.000Z'],
    ['submission-004', 'task-001', 'student-006', 62, 'pending', '2026-10-19T01:25:00.000Z'],
    ['submission-005', 'task-003', 'student-003', 92, 'passed', '2026-10-18T09:36:00.000Z'],
    ['submission-006', 'task-005', 'student-005', 88, 'passed', '2026-10-18T08:20:00.000Z'],
    ['submission-007', 'task-006', 'student-002', 48, 'returned', '2026-10-18T07:48:00.000Z'],
    ['submission-008', 'task-007', 'student-004', 84, 'passed', '2026-10-17T06:30:00.000Z'],
  ];
  const submissions = submissionSpecs.map(spec => {
    const [id, taskId, studentId, score, status, submittedAt] = spec;
    const task = tasks.find(item => item.id === taskId);
    const learner = learners.find(item => item.id === studentId);
    const answer = taskId === 'task-001'
      ? '一、核心问题\n用户在首次使用时难以找到关键功能。访谈中 8 位用户有 5 位提到入口不清晰；使用数据也显示新用户在首页到目标页的转化率偏低。\n\n二、问题优先级\n将首次使用的导航理解成本列为 P0，其次处理反馈状态不透明和表单填写成本。优先级结合影响人数、问题频率与实现成本判断。\n\n三、改进方案\n为新用户提供清晰的场景入口和三步引导，在关键操作后显示进度与反馈；保留跳过引导的选项。先以低保真原型验证，再进行小流量测试。\n\n四、验收与风险\n以首日关键任务完成率为主指标，目标提升 15%；同时观察完成时间和引导跳过率。风险是引导干扰老用户，方案按首次访问触发，并保留对照组。'
      : `一、任务理解\n本次围绕“${task.title}”完成分析与交付。先梳理任务材料、目标用户和验收标准，再确定执行优先级。\n\n二、分析过程\n结合材料中的案例和数据，识别主要问题及其原因，并记录关键假设。将高影响、高频问题优先处理，为每个判断补充依据。\n\n三、执行方案\n按照准备、实施、检查和交付四个阶段推进。明确各阶段的输入、产出和责任人，对异常路径补充测试和应对措施。\n\n四、验证计划\n通过可量化指标与对照测试验证结果，持续追踪完成率、质量和用户反馈。发现偏差时复查假设并调整方案。`;
    return {
      id, taskId, studentId, studentName: learner.name, submittedAt, answer, camp: getReviewCamp({}, task),
      attachments: id === 'submission-002' ? [{ name: 'API实现与接口说明.zip', size: 2850816, url: '' }] : [],
      ai: {
        score,
        comment: score >= 80 ? '整体完成度较高，分析与方案对应清晰。建议进一步补充边界场景和验证样本，以提升交付的可验证性。' : score >= 60 ? '已覆盖主要任务要求，但部分结论的材料依据不足，建议补充具体数据与验收指标。' : '当前产出未完整覆盖任务要求，缺少关键异常场景和可执行的验证方法，建议补充后重新提交。',
        dimensions: task.rubric.map((dimension, index) => ({ name: dimension.name, score: round(dimension.points * score / 100), max: dimension.points, comment: ['问题定义清晰，目标理解准确。', '主要依据较充分，可补充量化分析。', '方案具有可执行性，建议细化边界场景。', '内容结构清晰，交付格式完整。'][index % 4] })),
        source: 'demo',
      },
      status: task.reviewMode === 'ai' && status === 'returned' ? 'ai_failed' : status, reviewMode: task.reviewMode,
      finalScore: status === 'pending' ? null : score,
      reviewComment: status === 'passed' ? (task.reviewMode === 'ai' ? 'AI 自测通过，奖励已自动发放。' : '方案完整，审核通过。') : status === 'returned' ? '请补充异常路径测试与验收指标后再次提交。' : '',
      rewarded: status === 'passed',
      failureReasons: status === 'returned' ? ['requirements_not_met'] : [],
      improvementSuggestions: status === 'returned' ? '请补充异常路径测试与验收指标后再次提交。' : '',
    };
  });
  const claims = Object.fromEntries(submissions.filter(item => item.rewarded).map(item => [
    `${item.studentId}:${item.taskId}`,
    { studentId: item.studentId, taskId: item.taskId, submissionId: item.id, claimedAt: item.submittedAt, ...rewardBreakdown(tasks.find(task => task.id === item.taskId)) },
  ]));
  const certifications = [
    { id: 'cert-001', name: '林若晴', role: '管理系统的管理员', domain: '产品开发', domains: ['产品开发', '数据交付'], level: 3, status: 'verified', method: 'admin', certifiedAt: '2026-09-18T02:00:00.000Z', bio: '负责产品思维与需求分析方向的任务设计。' },
    { id: 'cert-002', name: '陈知远', role: '管理系统的管理员', domain: '技术开发', domains: ['技术开发', '质量检测'], level: 3, status: 'verified', method: 'application', certifiedAt: '2026-09-20T03:00:00.000Z', bio: '专注工程实践、代码质量与测试。' },
    { id: 'cert-003', name: '周予安', role: 'NPC', domain: '数据交付', domains: ['数据交付'], level: 2, status: 'verified', method: 'admin', certifiedAt: '2026-09-22T01:00:00.000Z', bio: '数据清洗、交付与质量检查。' },
    { id: 'cert-004', name: '许嘉宁', role: '管理系统的管理员', domain: 'PMO', domains: ['PMO', '项目管理'], level: 3, status: 'verified', method: 'admin', certifiedAt: '2026-09-24T04:00:00.000Z', bio: '项目协作与 PMO 方法实践。' },
    { id: 'cert-005', name: '宋一禾', role: 'NPC', domain: 'AI评测', domains: ['AI评测', 'AI能力'], level: 2, status: 'verified', method: 'admin', certifiedAt: '2026-10-01T02:00:00.000Z', bio: 'AI 工作流与评测方向。' },
  ];
  certifications.forEach(certification => {
    const level = getCertificationLevel(certification.level);
    certification.levelName = level.name;
    certification.taskDifficulty = level.difficulty;
  });
  return { draft, tasks, submissions, learners, certifications, claims };
}

export class Store {
  constructor(options = {}) {
    this.key = options.key || STORAGE_KEY;
    try { this.storage = options.storage || globalThis.localStorage; } catch { this.storage = null; }
    const seed = createSeed();
    let stored;
    try { stored = JSON.parse(this.storage?.getItem(this.key) || 'null'); } catch { stored = null; }
    this.data = stored && Array.isArray(stored.tasks) && Array.isArray(stored.submissions)
      ? { ...seed, ...stored, claims: stored.claims && typeof stored.claims === 'object' ? stored.claims : {} }
      : seed;
    this.save();
  }

  save() {
    // Migrate task definitions, never issued claims or learner account balances.
    if (this.data.draft) Object.assign(this.data.draft, applyDifficultyPreset(this.data.draft));
    this.data.tasks.forEach(task => Object.assign(task, applyDifficultyPreset(task)));
    try { this.storage?.setItem(this.key, JSON.stringify(this.data)); this.persistenceError = null; }
    catch (error) {
      this.persistenceError = error;
      const failure = new Error('浏览器存储空间不足或不可用，请减少附件大小后重试。');
      failure.cause = error;
      throw failure;
    }
    return this.data;
  }

  getTask(id) {
    return this.data.tasks.find(task => task.id === id) || (this.data.draft?.id === id ? this.data.draft : null);
  }

  saveTask(task) {
    if (!task || typeof task !== 'object') throw new Error('任务数据无效');
    task = applyDifficultyPreset(task);
    const errors = fieldLimits(task);
    if (!DIFFICULTY_PRESETS.some(item => item.name === task.difficulty)) errors.push('请选择入门、进阶或挑战难度');
    if (task.reviewMode === 'ai') {
      if (task.passScore !== undefined && task.passScore !== '' && !isNumeric(task.passScore)) errors.push('任务数值需为有限数字');
      if (isNumeric(task.passScore) && Number(task.passScore) < 0) errors.push('任务数值不能为负数');
      if (isNumeric(task.passScore) && Number(task.passScore) > 100) errors.push('通过分数需在 0～100 分之间');
    }
    if (task.status === 'published') errors.push(...validateTask(task));
    if (errors.length) {
      const error = new Error([...new Set(errors)].join('；'));
      error.errors = [...new Set(errors)];
      throw error;
    }
    const snapshot = clone(this.data);
    const isCurrentDraft = task.id === this.data.draft?.id;
    const saved = { ...clone(task), id: task.id || uid('task'), camp: getReviewCamp({}, task), updatedAt: now() };
    if (saved.status === 'published' && saved.reviewMode === 'manual') {
      saved.rubric = [];
      saved.rubricAttachments = [];
      saved.passScore = null;
    }
    const currentVersion = this.data.tasks.find(item => item.id === saved.id);
    const sourceId = saved.sourceTaskId || (saved.status === 'draft' && ['published', 'archived'].includes(currentVersion?.status) ? currentVersion.id : null);
    if (saved.status === 'draft' && sourceId) {
      if (!this.data.tasks.some(item => item.id === sourceId)) throw new Error('待编辑的原任务不存在');
      saved.id = `draft-${sourceId}`;
      saved.sourceTaskId = sourceId;
    }
    saved.author ||= '林若晴';
    saved.participants ??= 0;
    saved.completions ??= 0;
    const index = this.data.tasks.findIndex(item => item.id === saved.id);
    if (index >= 0) this.data.tasks[index] = saved;
    else this.data.tasks.unshift(saved);
    if (saved.status === 'draft' && isCurrentDraft) this.data.draft = clone(saved);
    try { this.save(); } catch (error) { this.data = snapshot; throw error; }
    return saved;
  }

  publishDraft() {
    const errors = validateTask(this.data.draft);
    if (errors.length) {
      const error = new Error(errors.join('；'));
      error.errors = errors;
      throw error;
    }
    const current = applyDifficultyPreset(this.data.draft);
    const existing = this.data.tasks.find(task => task.id === (current.sourceTaskId || current.id));
    if (current.sourceTaskId && !existing) throw new Error('待发布的原任务不存在');
    const content = clone(current);
    content.camp = getReviewCamp({}, current);
    delete content.sourceTaskId;
    if (content.reviewMode === 'manual') {
      content.rubric = [];
      content.rubricAttachments = [];
      content.passScore = null;
    }
    const published = {
      ...content, id: existing?.id || uid('task'), status: 'published', updatedAt: now(),
      participants: existing?.participants || 0, completions: existing?.completions || 0,
    };
    const snapshot = clone(this.data);
    const index = this.data.tasks.findIndex(task => task.id === published.id);
    if (index >= 0) this.data.tasks[index] = published;
    else this.data.tasks.unshift(published);
    if (current.sourceTaskId) this.data.tasks = this.data.tasks.filter(task => task.id === published.id || !(task.status === 'draft' && task.sourceTaskId === published.id));
    // Keep temporary AI settings only in the editor, so switching mode restores them.
    this.data.draft = { ...clone(current), id: published.id, camp: published.camp, status: 'draft', updatedAt: published.updatedAt, participants: published.participants, completions: published.completions };
    delete this.data.draft.sourceTaskId;
    try { this.save(); } catch (error) { this.data = snapshot; throw error; }
    return published;
  }

  reviewSubmission(id, { decision, score, comment = '', reasonCodes = [] } = {}) {
    const submission = this.data.submissions.find(item => item.id === id);
    if (!submission) throw new Error('未找到这份提交');
    if (!['passed', 'returned'].includes(decision)) throw new Error('请选择通过或退回');
    const hasReturnReason = Array.isArray(reasonCodes) ? reasonCodes.some(code => text(code) !== '') : text(reasonCodes) !== '';
    if (decision === 'passed' && hasReturnReason) throw new Error('已选择退回原因，请取消勾选后再确认通过');
    if (submission.reviewMode !== 'manual') throw new Error('AI 自测记录不能进行人工审核');
    if (submission.supersededBy) throw new Error('这份提交已重新提交，请审核最新记录');
    const reviewComment = text(comment);
    if (decision === 'returned' && !reviewComment) throw new Error('退回任务时请填写修改建议');
    const failureReasons = decision === 'returned' ? validateFailureReasons(reasonCodes) : [];
    const task = this.getTask(submission.taskId);
    if (!task) throw new Error('未找到对应任务');
    if (!DIFFICULTY_PRESETS.some(item => item.name === task.difficulty)) throw new Error('请选择入门、进阶或挑战难度');
    const key = `${submission.studentId}:${submission.taskId}`;
    const alreadyRewarded = Boolean(this.data.claims[key] || submission.rewarded);
    if (submission.status !== 'pending') {
      if (submission.status === 'passed' && decision === 'passed' && this.data.claims[key]) {
        return { rewarded: false, alreadyRewarded: true, submission, reward: this.data.claims[key] || rewardBreakdown(task) };
      }
      if (submission.status === 'returned' && decision === 'returned') {
        return { rewarded: false, alreadyRewarded, submission, reward: null };
      }
      if (submission.status === 'passed') throw new Error('这份任务已通过审核，不能退回或重复修改');
      throw new Error('仅待人工审核的提交可以进行审核');
    }
    const hasScore = score !== null && score !== undefined && text(score) !== '';
    const finalScore = hasScore ? Number(score) : null;
    if (hasScore && (!isNumeric(score) || finalScore < 0 || finalScore > 100)) throw new Error('最终评分需在 0～100 分之间');
    let rewarded = false;
    let reward = null;
    const snapshot = clone(this.data);
    // Rewarded records cannot be returned, which would imply a silent clawback.
    if (alreadyRewarded && decision === 'returned') throw new Error('这份任务已发放奖励，不能退回');
    if (decision === 'passed') {
      const result = this._awardSubmission(submission, task);
      rewarded = result.rewarded;
      reward = result.reward;
    }
    submission.status = decision;
    submission.finalScore = finalScore;
    submission.reviewComment = reviewComment;
    submission.failureReasons = failureReasons;
    submission.improvementSuggestions = decision === 'returned' ? reviewComment : '';
    submission.reviewedAt = now();
    try { this.save(); } catch (error) { this.data = snapshot; throw error; }
    return { rewarded, alreadyRewarded, submission, reward };
  }

  _awardSubmission(submission, task) {
    const key = `${submission.studentId}:${submission.taskId}`;
    if (this.data.claims[key] || submission.rewarded) {
      submission.rewarded = true;
      return { rewarded: false, alreadyRewarded: true, reward: this.data.claims[key] || rewardBreakdown(task) };
    }
    const learner = this.data.learners.find(item => item.id === submission.studentId);
    if (!learner) throw new Error('未找到对应学员');
    const reward = rewardBreakdown(task);
    learner.xp = round(number(learner.xp) + reward.xp);
    learner.taskPoints = round(number(learner.taskPoints) + reward.taskPoints);
    learner.badges ||= {};
    learner.badgeLevels ||= {};
    reward.allocations.forEach(allocation => {
      learner.badges[allocation.id] = round(number(learner.badges[allocation.id]) + allocation.points);
      learner.badgeLevels[allocation.id] = Math.min(3, Math.floor(learner.badges[allocation.id] / 100));
    });
    this.data.claims[key] = { studentId: submission.studentId, taskId: task.id, submissionId: submission.id, claimedAt: now(), ...reward };
    task.completions = number(task.completions) + 1;
    submission.rewarded = true;
    return { rewarded: true, alreadyRewarded: false, reward };
  }

  resubmitSubmission(id, { answer = '', attachments = [] } = {}) {
    const previous = this.data.submissions.find(item => item.id === id);
    if (!previous) throw new Error('未找到原提交记录');
    const task = this.getTask(previous.taskId);
    if (!task) throw new Error('未找到对应任务');
    const key = `${previous.studentId}:${previous.taskId}`;
    if (previous.supersededBy) throw new Error('这份记录已重新提交，请使用最新记录');
    if (previous.rewarded || this.data.claims[key] || getSubmissionStatus(previous, task) === 'passed') throw new Error('已通过或已领取奖励的任务不能重新提交');
    if (!['returned', 'ai_failed'].includes(getSubmissionStatus(previous, task))) throw new Error('仅不通过的记录可以重新提交');
    if (!Array.isArray(attachments)) throw new Error('提交附件格式无效');
    if (!text(answer) && !attachments.length) throw new Error('请填写修改后的答案或上传附件');
    const reviewMode = previous.reviewMode || task.reviewMode;
    if (!['manual', 'ai'].includes(reviewMode)) throw new Error('任务审核方式无效');
    const submission = {
      id: uid('submission'), taskId: previous.taskId, studentId: previous.studentId, studentName: previous.studentName, camp: getReviewCamp(previous, task),
      submittedAt: now(), answer: String(answer ?? ''), attachments: clone(attachments), reviewMode,
      attempt: Math.max(1, Math.floor(number(previous.attempt) || 1)) + 1,
      previousSubmissionId: previous.id, status: 'pending', ai: null, finalScore: null,
      reviewComment: '', failureReasons: [], improvementSuggestions: '', rewarded: false,
    };
    if (reviewMode === 'ai') {
      submission.ai = gradeAnswer({ ...task, reviewMode: 'ai' }, submission.answer);
      submission.status = submission.ai.passed ? 'passed' : 'ai_failed';
      submission.finalScore = submission.ai.score;
      submission.failureReasons = clone(submission.ai.failureReasons);
      submission.improvementSuggestions = submission.ai.improvementSuggestions;
    }
    const snapshot = clone(this.data);
    let result = { rewarded: false, alreadyRewarded: false, reward: null };
    try {
      if (submission.status === 'passed') result = this._awardSubmission(submission, task);
      previous.supersededBy = submission.id;
      this.data.submissions.unshift(submission);
      this.save();
    } catch (error) { this.data = snapshot; throw error; }
    return { submission, previousSubmissionId: previous.id, ...result };
  }
}

const ICONS = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  send: '<path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  library: '<path d="M4 4v16M9 4v16M14 4v16M18 4l3 16"/>',
  shield: '<path d="m12 3 8 3v6c0 4-3.5 7-8 9-4.5-2-8-5-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  chevronRight: '<path d="m9 5 7 7-7 7"/>',
  chevronDown: '<path d="m5 9 7 7 7-7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4h16v-4"/>',
  link: '<path d="m10 13 4-4M8 16l-1 1a4.2 4.2 0 0 1-6-6l4-4a4.2 4.2 0 0 1 6 0m2 1 1-1a4.2 4.2 0 0 1 6 6l-4 4a4.2 4.2 0 0 1-6 0" transform="translate(1 1)"/>',
  file: '<path d="M14 2H5v20h14V7l-5-5Z"/><path d="M14 2v5h5M8 12h8M8 16h6"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5L5 21"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  star: '<path d="m12 3 2.8 5.6 6.2.9-4.5 4.4 1.1 6.1-5.6-2.9L6.4 20l1.1-6.1L3 9.5l6.2-.9L12 3Z"/>',
  award: '<circle cx="12" cy="8" r="5"/><path d="m8 12-2 9 6-3 6 3-2-9"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  filter: '<path d="M4 5h16l-6 7v6l-4 2v-8L4 5Z"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  arrowRight: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  arrowLeft: '<path d="M20 12H4m6-6-6 6 6 6"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
  edit: '<path d="m16 3 5 5-12 12-6 1 1-6L16 3Zm-3 3 5 5"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1 .7-1.5 1-1.5 3M12 17h.01"/>',
  logout: '<path d="M9 4H4v16h5M9 12h12m-5-5 5 5-5 5"/>',
  sparkles: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  alert: '<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5M12 17h.01"/>',
  user: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 1M5 17a8 8 0 0 0 13 1"/>',
  external: '<path d="M14 3h7v7M21 3 10 14M10 3H3v18h18v-7"/>',
  book: '<path d="M12 5C8 2 4 3 2 4v15c3-1.5 6-1 10 1 4-2 7-2.5 10-1V4c-2-1-6-2-10 1Zm0 0v15"/>',
};

export function icon(name, size = 20) {
  const pixels = Math.max(8, Math.min(96, number(size) || 20));
  return `<svg width="${pixels}" height="${pixels}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.grid}</svg>`;
}
