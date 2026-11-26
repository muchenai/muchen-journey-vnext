export type AcademySection = { id: string; title: string; chapterLevel?: boolean; materialIds: string[] };
export type AcademyChapter = {
  id: string;
  title: string;
  sections: AcademySection[];
  exam: string;
  homework: string;
  homeworkXp: number;
};
export type ChapterSubmission = { text: string; time: string; awardedXp: number };
export const DEFAULT_SERIES_XP = 20;
export const EXAM_XP = 10;
export function defaultChapter(materials: { id: string }[]): AcademyChapter {
  return { id: "chapter-1", title: "课程学习", sections: [{ id: "section-1", title: "学习材料", materialIds: materials.map(m => m.id) }], exam: "", homework: "", homeworkXp: 0 };
}
type ChapterStatus = { reflection?: { status: string } | null; exam?: ChapterSubmission; homework?: ChapterSubmission };
export function chapterCompleted(chapter: AcademyChapter, row?: ChapterStatus) {
  return row?.reflection?.status === "passed" && (!chapter.exam || !!row.exam) && (!chapter.homework || !!row.homework);
}

export function academyOverallPercent(materialCount: number, materialPercent: number, chapters: AcademyChapter[], states: Record<string, ChapterStatus>) {
  let total = materialCount;
  let earned = materialCount * materialPercent / 100;
  for (const chapter of chapters) {
    const row = states[chapter.id];
    total += 1 + Number(!!chapter.exam) + Number(!!chapter.homework);
    earned += Number(row?.reflection?.status === "passed") + Number(!!chapter.exam && !!row?.exam) + Number(!!chapter.homework && !!row?.homework);
  }
  return total ? Math.floor(100 * earned / total + 1e-9) : 0;
}
