import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';
import { taskAction, taskNumber, taskMaterialType } from './academy-task-label.js?v=20261126-task-delivery';
import { kindLabel } from './academy-workspace-views.js?v=20261126-task-delivery';

const newSection = title => ({id:crypto.randomUUID(), title, materialIds:[]});
const chapterSection = () => ({...newSection('整章材料'), chapterLevel:true});
const newChapter = title => ({id:crypto.randomUUID(), title, sections:[chapterSection()], exam:'', homework:'', homeworkXp:0});

export function prepareChapters(course) {
  if (course.chapters?.length) return;
  const chapter = newChapter('课程学习');
  chapter.id = 'chapter-1';
  chapter.sections[0] = {
    id:'section-1', title:course.id ? '学习材料' : '整章材料',
    materialIds:course.materials.map(material => material.id), ...(course.id ? {} : {chapterLevel:true}),
  };
  course.chapters = [chapter];
}

export function currentChapter(editor) {
  return editor.course.chapters.find(ch => ch.id === editor.chapterId) || editor.course.chapters[0];
}

export function isChapterSection(chapter, section) {
  if (!section) return false;
  return Boolean(section.chapterLevel) || (chapter.id === 'chapter-1' && section.id === 'section-1' &&
    section.title === '学习材料' && !chapter.sections.some(item => item.chapterLevel));
}

export function currentSection(editor) {
  const chapter = currentChapter(editor);
  return chapter.sections.find(item => item.id === editor.sectionId) ||
    chapter.sections.find(item => isChapterSection(chapter, item)) || chapter.sections[0];
}

function selectChapterMaterials(editor, chapter) {
  let section = chapter.sections.find(item => isChapterSection(chapter, item));
  if (!section) {
    section = chapterSection();
    chapter.sections.unshift(section);
  }
  editor.chapterId = chapter.id;
  editor.sectionId = section.id;
}

const moveButtons = (kind, index, count, label) =>
  [['up','上移','↑',index === 0], ['down','下移','↓',index === count - 1]].map(([direction,action,arrow,disabled]) =>
    `<button type="button" class="series-step" data-series-action="${kind}-${direction}" aria-label="${e(action + label)}" title="${action}" ${disabled ? 'disabled' : ''}>${arrow}</button>`).join('');



function mediaList(section, materials, offset) {
  return section.materialIds.map((id, index, ids) => {
    const item = materials.get(id);
    if (!item) return '';
    const title = item.title || item.name || kindLabel(item.kind);
    const seconds = Math.ceil(Number(item.durationSeconds));
    const time = item.kind === 'video' && seconds > 0 ?
      `<span class="series-duration">${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}</span>` : '';
    return `<li class="series-media" data-series-material="${e(id)}">
      <span class="series-ordinal">${taskNumber(offset + index + 1)}</span>
      <span class="series-kind ${item.kind === 'video' ? 'is-video' : ''}">${e(taskMaterialType(item))}</span>
      <label class="series-media-title series-task-field"><input type="text" data-task-name="${e(id)}" maxlength="150" aria-label="${taskNumber(offset + index + 1)}名称" placeholder="${e(taskAction(item.kind))}" value="${e(item.taskTitle || '')}"><small>${e(title)}</small></label>${time}
      <span class="series-media-actions">${moveButtons('material', index, ids.length, title)}
      <button class="series-text" type="button" data-aw-remove="${e(id)}" aria-label="移除${e(title)}">移除</button></span></li>`;
  }).join('');
}

function assessmentFields(chapter) {
  return `<details class="aw-assessments series-assessments" ${chapter.exam || chapter.homework ? 'open' : ''}><summary>本章课后作业与考试（选填）</summary>
    <label class="ac-field"><span>考试题目 · 首次提交另发 10 经验</span><textarea name="chapterExam" rows="2" maxlength="4000">${e(chapter.exam)}</textarea></label>
    <label class="ac-field"><span>作业要求</span><textarea name="chapterHomework" rows="2" maxlength="4000">${e(chapter.homework)}</textarea></label>
    <label class="ac-field"><span>作业首次提交奖励（经验，单独发放）</span><input name="homeworkXp" type="number" min="0" max="1000000" value="${Number(chapter.homeworkXp) || 0}"></label></details>`;
}

function removableChapter(chapter) {
  return !chapter.sections.some(section => section.materialIds.length) && !chapter.exam && !chapter.homework;
}

function renderChapter(chapter, index, chapters, selectedChapter, selectedSection, materials, uploadHtml) {
  const active = chapter.id === selectedChapter.id;
  const number = `第 ${index + 1} 章`;
  const count = chapter.sections.reduce((n,section)=>n+section.materialIds.length,0);
  let offset = 0;
  let subsectionNumber = 0;
  const sections = chapter.sections.map(section => {
    const direct = isChapterSection(chapter, section);
    const selected = active && section.id === selectedSection?.id;
    const rows = mediaList(section, materials, offset);
    offset += section.materialIds.length;
    if (!direct) subsectionNumber++;
    const directHeading = chapter.sections.length > 1 && (rows || selected) ? '<span class="series-group-caption">章内材料</span>' : '';
    const sectionHeading = direct ? directHeading : `<div class="series-subhead">
      <span class="series-sub-index">小节 ${subsectionNumber}</span>
      ${selected ? `<label class="series-title-field"><input class="series-title-input" aria-label="小节名称" name="sectionTitle" maxlength="150" value="${e(section.title)}"></label>` :
        `<button class="series-title" type="button" data-series-action="select-section" aria-label="编辑小节 ${e(section.title)}">${e(section.title || '未命名小节')}</button>`}
      <button class="series-text" type="button" data-series-action="add-video">添加学习任务</button>
      ${!section.materialIds.length ? '<button type="button" class="series-text" data-series-action="remove-section">删除空小节</button>' : ''}
      </div>`;
    return `<div class="${direct ? 'series-direct' : 'series-subsection'}" data-series-section="${e(section.id)}">
      ${sectionHeading}${rows ? `<ol class="series-media-list" aria-label="${e(direct ? chapter.title : section.title)}的学习材料">${rows}</ol>` : ''}
      ${selected ? uploadHtml : ''}</div>`;
  }).join('');
  return `<article class="series-chapter ${active ? 'is-active' : ''}" data-series-chapter="${e(chapter.id)}" aria-label="${number} ${e(chapter.title)}">
    <div class="series-chapter-head"><span class="series-index">${number}</span>
    ${active ? `<label class="series-title-field"><input class="series-title-input" name="chapterTitle" maxlength="150" value="${e(chapter.title)}" aria-label="章节名称"></label>` :
      `<button type="button" class="series-title" data-series-action="select-chapter" aria-label="编辑章节 ${e(chapter.title)}">${e(chapter.title || '未命名章节')}</button>`}
    <span class="series-count">${count} 个任务</span>
    <span class="series-chapter-actions">${moveButtons('chapter', index, chapters.length, number)}
    <button type="button" class="series-add-video" data-series-action="add-video">添加学习任务</button></span></div>
    <div class="series-chapter-body">${sections}
      ${active ? `<div class="series-chapter-tools">${!isChapterSection(chapter, selectedSection) ? '<button type="button" class="series-text" data-series-action="select-direct">编辑章内材料</button>' : ''}<button type="button" class="series-text" data-series-action="add-section">添加小节</button>
        ${chapters.length > 1 && removableChapter(chapter) ? '<button type="button" class="series-text" data-series-action="remove-chapter">删除空章节</button>' : ''}
      </div>${assessmentFields(chapter)}` : ''}</div></article>`;
}

export function structureFields(editor, uploadHtml = '') {
  const {chapters, materials} = editor.course;
  const byId = new Map(materials.map(item => [item.id, item]));
  const active = currentChapter(editor), section = currentSection(editor);
  return `<section class="aw-section series-directory" data-series-directory>
    <header class="series-heading"><div><h2>课程目录</h2><p>${chapters.length} 个章节 · ${materials.length} 个学习任务</p></div>
      <button type="button" class="ac-btn ac-btn-secondary" data-series-action="add-chapter">＋ 新增章节</button></header>
    <div class="series-chapters">${chapters.map((chapter, i) => renderChapter(chapter, i, chapters, active, section, byId, uploadHtml)).join('')}</div></section>`;
}

export function captureStructure(editor, form) {
  const chapter = currentChapter(editor), fields = form.elements;
  chapter.title = fields.chapterTitle.value;
  if (fields.sectionTitle) currentSection(editor).title = fields.sectionTitle.value;
  chapter.exam = fields.chapterExam.value;
  chapter.homework = fields.chapterHomework.value;
  chapter.homeworkXp = Number(fields.homeworkXp.value);
}

function move(items, item, direction) {
  const index = items.indexOf(item);
  const next = index + (direction === 'up' ? -1 : 1);
  if (index < 0 || next < 0 || next >= items.length) return;
  [items[index], items[next]] = [items[next], items[index]];
}

export function bindStructure(editor, form, refresh) {
  const directory = form.querySelector('[data-series-directory]');
  if (!directory) return;
  directory.addEventListener('click', event => {
    const control = event.target.closest('[data-series-action]');
    if (!control || control.disabled || editor.busy) return;
    const action = control.dataset.seriesAction;
    const chapters = editor.course.chapters;
    const chapterId = control.closest('[data-series-chapter]')?.dataset.seriesChapter;
    const sectionId = control.closest('[data-series-section]')?.dataset.seriesSection;
    const mediaId = control.closest('[data-series-material]')?.dataset.seriesMaterial;
    const chapter = chapters.find(item => item.id === chapterId);
    const section = chapter?.sections.find(item => item.id === sectionId);
    let focus = '';
    switch (action) {
      case 'add-chapter': {
        const next = newChapter('未命名章节');
        chapters.push(next);
        selectChapterMaterials(editor, next);
        focus = '[name=chapterTitle]';
        break;
      }
      case 'select-chapter':
        editor.chapterId = chapter.id;
        editor.sectionId = null;
        focus = '[name=chapterTitle]';
        break;
      case 'add-section': {
        const legacy = chapter.sections.find(section => isChapterSection(chapter, section) && !section.chapterLevel);
        if (legacy) legacy.chapterLevel = true;
        const next = newSection('未命名小节');
        chapter.sections.push(next);
        editor.chapterId = chapter.id;
        editor.sectionId = next.id;
        focus = '[name=sectionTitle]';
        break;
      }
      case 'select-section':
        editor.chapterId = chapter.id;
        editor.sectionId = section.id;
        focus = '[name=sectionTitle]';
        break;
      case 'select-direct':
        selectChapterMaterials(editor, chapter);
        focus = '[data-aw-drop]';
        break;
      case 'add-video':
        if (section) {
          editor.chapterId = chapter.id;
          editor.sectionId = section.id;
        } else {
          selectChapterMaterials(editor, chapter);
        }
        focus = '[data-aw-drop]';
        break;
      case 'remove-section':
        if (!section || section.materialIds.length || isChapterSection(chapter, section)) return;
        chapter.sections.splice(chapter.sections.indexOf(section), 1);
        selectChapterMaterials(editor, chapter);
        focus = '[name=chapterTitle]';
        break;
      case 'remove-chapter':
        if (chapters.length < 2 || !removableChapter(chapter)) return;
        chapters.splice(chapters.indexOf(chapter), 1);
        editor.chapterId = null;
        editor.sectionId = null;
        focus = '[name=chapterTitle]';
        break;
      case 'chapter-up': case 'chapter-down':
        editor.chapterId = currentChapter(editor).id;
        move(chapters, chapter, action.slice(8));
        break;
      case 'material-up': case 'material-down':
        move(section.materialIds, mediaId, action.slice(9));
        break;
      default: return;
    }
    refresh();
    const nextForm = form.ownerDocument.querySelector('[data-aw-editor]');
    if (focus) {
      const target = nextForm?.querySelector(focus);
      target?.focus(); target?.select?.();
    } else {
      const card = Array.from(nextForm?.querySelectorAll('[data-series-chapter]') || []).find(row => row.dataset.seriesChapter === chapterId);
      const row = mediaId ? Array.from(card?.querySelectorAll('[data-series-material]') || []).find(row => row.dataset.seriesMaterial === mediaId) : card;
      (row?.querySelector(`[data-series-action="${action}"]:enabled`) || row?.querySelector('.series-step:enabled'))?.focus();
    }
  });
}
