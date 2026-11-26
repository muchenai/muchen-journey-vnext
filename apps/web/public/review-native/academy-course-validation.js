import { currentChapter, currentSection } from './academy-chapters.js?v=20261126-task-delivery';

const inRange = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;
const length = value => Array.from(value || '').length;
export const materialControl = '[data-aw-drop]';

export function sectionControl(editor, selector) {
  return {selector, chapter:currentChapter(editor).id, section:currentSection(editor).id};
}

export function courseIssues(editor, publish) {
  const c = editor.course, issues = [];
  const add = (selector,message,chapter,section) => issues.push({selector,message,chapter,section});
  if (!c.title.trim()) add('[name=title]', '请填写课程名称。');
  else if (length(c.title) > 150) add('[name=title]', '课程名称最多 150 字。');
  if (length(c.summary) > 2000) add('[name=summary]', '课程简介最多 2000 字。');
  if (!inRange(c.minutes,1,100000)) add('[name=minutes]', '预计学习时长须为 1 至 100000 的整数。');
  if (!inRange(c.rewardXp,0,1000000)) add('[name=rewardXp]', '奖励经验值须为 0 至 1000000 的整数。');
  for (const chapter of c.chapters) {
    const chapterId = chapter.id;
    if (!chapter.title.trim() || length(chapter.title) > 150) add('[name=chapterTitle]', '请填写 1 至 150 字的章节名称。', chapterId);
    const empty = chapter.sections.every(section => !section.materialIds.length);
    const needsChapterMaterial = empty && chapter.sections.every(section => section.chapterLevel);
    for (const section of chapter.sections) {
      if (!section.title.trim() || length(section.title) > 150) add('[name=sectionTitle]', '请填写 1 至 150 字的小节名称。', chapterId, section.id);
      if (editor.linkDrafts.get(section)?.linkUrl.trim()) {
        add('[name=linkUrl]', '请点击「添加链接」，或清空尚未添加的链接。', chapterId, section.id);
      } else if (publish && !section.materialIds.length && (!section.chapterLevel || needsChapterMaterial)) {
        add(materialControl, section.chapterLevel ? '请为本章添加学习材料。' : '请为本小节添加学习材料。', chapterId, section.id);
      }
    }
    if (chapter.homework.trim() && !inRange(chapter.homeworkXp,0,1000000)) {
      add('[name=homeworkXp]', '作业奖励经验值须为 0 至 1000000 的整数。', chapterId);
    }
  }
  if (editor.scope !== 'village') {
    const canExtract = c.materials.some(item => item.assetId && /\.(txt|md|docx)$/i.test(item.name || item.title || ''));
    if (length(c.contentText) > 48000) add('[name=contentText]', '课程正文最多 48000 字。');
    else if (publish && !c.contentText.trim() && !canExtract) add('[name=contentText]', '请补充课程正文、字幕或可提取正文的材料，再提交发布。');
    if (length(c.rubric) > 6000) add('[name=rubric]', '评分细则最多 6000 字。');
    else if (publish && !c.rubric.trim()) add('[name=rubric]', '请填写评分细则与通过条件，再提交发布。');
  }
  return issues;
}

// The API can discover stale or unreadable resources after local checks pass.
export function saveErrorControl(message, intent) {
  if (message.includes('课程标签')) return '[name=tags], [data-aw-tags], .ac-tag-options';
  if (message.includes('课程封面')) return '[data-aw-cover-upload]';
  if (message.includes('课程正文')) return '[name=contentText]';
  if (message.includes('课程内容范围')) return '[name=requiredTopic]';
  if (/材料|视频时长|章节|小节/.test(message)) return materialControl;
  return `button[type="submit"][value="${intent}"]`;
}
