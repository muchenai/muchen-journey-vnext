import { publicationReward } from './publish-content-type.js?v=20261126-task-delivery';
import {taskAction, taskNumber, taskMaterialType} from './academy-task-label.js?v=20261126-task-delivery';
import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';

function readiness(course) {
  const chapterReady = chapter => chapter.title.trim() && chapter.sections.some(section => section.materialIds.length) &&
    chapter.sections.every(section => section.title.trim() && (section.chapterLevel || section.materialIds.length));
  return [
    ['title', '名称', Boolean(course.title.trim())],
    ['minutes', '学习时长', Number.isInteger(course.minutes) && course.minutes >= 1 && course.minutes <= 100000],
    ['chapterTitle', '章节与学习材料', course.chapters.length > 0 && course.chapters.every(chapterReady)],
  ];
}

function overview(course, icon) {
  const kind = course.required ? '必修课程' : '普通任务';
  const minutes = course.minutes > 0 ? `预计 ${e(course.minutes)} 分钟` : '时长待填写';
  return `<div class="preview-meta-line"><span class="category-label">新手村 · ${kind}</span><span class="tag tag-neutral">实时预览</span></div>
    <h3>${e(course.title.trim() || '待填写名称')}</h3>${course.summary.trim() ? `<p>${e(course.summary)}</p>` : ''}
    <div class="overview-time">${icon('clock',14)} ${minutes}<span>${course.chapters.length} 章 · ${course.materials.length} 份材料</span></div>
    <div class="preview-task-access"><span>${publicationReward('village',course.required).label}</span><strong>${e(course.rewardXp ?? 20)} 经验</strong></div>
    <div class="preview-task-access"><span>学习条件</span><strong>${course.required ? '全员必修' : '完成全部必修后解锁'}</strong></div>
    ${course.tags.length ? `<div class="village-preview-tags">${course.tags.map(tag => `<span class="tag tag-neutral">${e(tag)}</span>`).join('')}</div>` : ''}`;
}

function outline(course) {
  const materials = new Map(course.materials.map(item => [item.id,item]));
  return course.chapters.map((chapter,i) => {
    let ordinal=0;
    return `<li><strong>第 ${i+1} 章 · ${e(chapter.title || '未命名章节')}</strong>
    ${chapter.sections.map(section => {
      const items = section.materialIds.map(id => materials.get(id)).filter(Boolean);
      return `${section.chapterLevel ? '' : `<div class="village-preview-section">${e(section.title || '未命名小节')}</div>`}
        ${items.length ? `<ul>${items.map(item => `<li>${taskNumber(++ordinal)} · ${e(item.taskTitle?.trim() || taskAction(item.kind))} · ${e(taskMaterialType(item))} · ${e(item.title || item.name)}</li>`).join('')}</ul>` : ''}`;
    }).join('')}</li>`;
  }).join('');
}

function checklist(course, icon) {
  const checks = readiness(course);
  return `<div class="checklist-heading"><h3>发布准备</h3><span>${checks.filter(([, , ready]) => ready).length}/${checks.length}</span></div>
    ${checks.map(([field,label,ready]) => `<button type="button" class="checklist-row ${ready ? 'complete' : 'incomplete'}" data-course-jump="${field}" aria-label="定位到${label}，${ready ? '已完成' : '待完成'}">
      ${icon(ready ? 'checkCircle' : 'alert',16)}<span>${label}</span><small>${ready ? '已完成' : '待完成'}</small>${icon('chevronRight',13)}</button>`).join('')}`;
}

export function renderCoursePreview(course,icon) {
  return `<section class="card overview-card compact-task-preview" aria-label="课程概览">
    <div class="overview-body" data-course-overview>${overview(course,icon)}</div>
    <details class="village-preview-outline"><summary>课程目录</summary><ol data-course-outline>${outline(course)}</ol></details>
    </section><section class="card checklist-card" aria-label="发布准备" data-course-checklist>${checklist(course,icon)}</section>`;
}

// Keep the form, the expanded directory and the focused radio intact during live edits.
export function bindCoursePreview(aside,form,course,icon) {
  if (!aside) return;
  const overviewNode = aside.querySelector('[data-course-overview]');
  const outlineNode = aside.querySelector('[data-course-outline]');
  const checklistNode = aside.querySelector('[data-course-checklist]');
  const lastMarkup = new Map();
  function update(node,markup) {
    if (lastMarkup.get(node) === markup) return;
    lastMarkup.set(node,markup);
    node.innerHTML = markup;
  }
  form.addEventListener('input', event => {
    update(overviewNode,overview(course,icon));
    update(checklistNode,checklist(course,icon));
    if (event.target.dataset?.taskName || ['rewardXp','chapterTitle','sectionTitle'].includes(event.target.name)) update(outlineNode,outline(course));
  });
  const group = aside.closest('.editor-layout').querySelector('.village-publish-options');
  group?.addEventListener('change', () => update(overviewNode,overview(course,icon)));
  aside.onclick = event => {
    const key = event.target.closest('[data-course-jump]')?.dataset.courseJump;
    const field = key && form.elements.namedItem(key);
    if (field && !field.disabled) {
      field.focus({preventScroll:true});
      field.scrollIntoView({block:'center'});
    }
  };
}
