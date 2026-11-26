"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { academyMaterialProgressPercent, academyMediaSource, academyVideoProgressPercent, type AcademyMedia, type AcademyWatchSnapshot } from "@/lib/academy-learning-media";
import { EXAM_XP, chapterCompleted, academyOverallPercent, defaultChapter, type AcademyChapter, type ChapterSubmission } from "@/lib/academy-chapters";
import { taskNumber, taskMaterialType } from "../../../public/review-native/academy-task-label.js";
import { AcademyStudyLayout, goToSection } from "./AcademyStudyLayout";
import { AcademyTrackedVideo } from "./AcademyTrackedVideo";
import { LearnerBack } from "./LearnerBack";
import type { AcademyItem, AcademyReflection } from "./useAcademy";

const failureMessage = (failure: unknown) => failure instanceof Error ? failure.message : "操作失败，请重试。";

const overviewId = "academy-course-overview";
const materialId = "academy-course-materials";
const reflectionId = "academy-course-reflection";
const tabIds = [overviewId, materialId, reflectionId];
const taskName = (item: AcademyMedia) => item.taskTitle?.trim() || ({document:"阅读文档",image:"查看图片",video:"观看视频",link:"学习链接"}[item.kind]);

function ReadingMaterial({ material, onRead }: { material: AcademyMedia; onRead: () => void }) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const source = academyMediaSource(material.url);
  if (!source) return <p role="alert" className="academy-error">材料地址无效，请联系课程管理员重新发布。</p>;
  if (material.kind !== "image") {
    return <a href={source} className="module-secondary" target="_blank" rel="noopener noreferrer" onClick={onRead}>
      {material.kind === "document" ? "打开文档" : "打开学习链接"} ↗
    </a>;
  }
  if (failed) return <p role="alert" className="academy-error">图片暂时无法加载。
    <button type="button" className="module-secondary" onClick={() => { setAttempt(value => value + 1); setFailed(false); }}>重新加载</button>
  </p>;
  // Uploaded course images can require the current session and can have arbitrary dimensions.
  // eslint-disable-next-line @next/next/no-img-element
  return <img key={attempt} className="academy-study-image" src={source} alt={material.title}
    onLoad={onRead} onError={() => setFailed(true)} />;
}

function ReflectionResult({ reflection }: { reflection: AcademyReflection }) {
  const reviews = { passed: "心得已通过", retry: "请修改后重新提交", pending: "心得等待评审" };
  return <div className="academy-study-result" data-result={reflection.status} aria-live="polite">
    <div><strong>{reviews[reflection.status]}</strong>
      {reflection.status !== "pending" && typeof reflection.score === "number" && <span>{reflection.score} 分</span>}
      {reflection.status === "passed" && typeof reflection.awardedXp === "number" && reflection.awardedXp > 0 &&
        <span className="academy-study-award">已获得 {reflection.awardedXp} 经验</span>}
    </div>
    {reflection.feedback && <p>{reflection.feedback}</p>}
    {reflection.status === "passed" && <details><summary>查看已提交的心得</summary><p>{reflection.text}</p></details>}
  </div>;
}

function ChapterAssessment({ title, prompt, xp, submission, unlocked, onSubmit }: {
  title: string; prompt: string; xp: number; submission?: ChapterSubmission; unlocked: boolean;
  onSubmit: (answer: string) => Promise<unknown>;
}) {
  const [answer, setAnswer] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!answer.trim() || !unlocked || saving || submission) return;
    setSaving(true); setError("");
    try { await onSubmit(answer.trim()); }
    catch (e) { setError(failureMessage(e)); }
    finally { setSaving(false); }
  }
  return <div className="academy-study-result"><h3>{title} {xp > 0 && <small>· {xp} 经验</small>}</h3>
    <p className="academy-study-content">{prompt}</p>
    {submission ? <details><summary>已提交{(submission.awardedXp > 0) && ` · 已获得 ${submission.awardedXp} 经验`}</summary><p>{submission.text}</p></details>
      : <form onSubmit={submit}><label className="module-field"><span>{unlocked ? "填写答案" : "学完本章材料后可作答"}</span>
        <textarea disabled={!unlocked || saving} value={answer} onChange={e => setAnswer(e.target.value)} maxLength={8000} rows={3} required />
      </label><button className="module-secondary" type="submit" disabled={saving || !unlocked || !answer.trim()}>{saving ? "提交中…" : "提交"+title}</button></form>}
    {error && <p role="alert" className="academy-error">{error}</p>}
  </div>;
}

type StudyProps = {
  villageCourse?: boolean;
  course: AcademyItem;
  favoriteBusy: boolean;
  onFavorite: (course: AcademyItem) => Promise<void>;
  learn: (command: Record<string, unknown>) => Promise<AcademyItem>;
  refresh: () => Promise<void>;
  onClose: () => void;
};

function recentlyWatched(ids: string[], watches: Record<string, AcademyWatchSnapshot>) {
  let latest: string | undefined;
  for (const id of ids) {
    const watch = watches[id];
    if (watch && !watch.completed && watch.watchedSeconds > 0 &&
        (!latest || (watch.updatedAt ?? "") > (watches[latest].updatedAt ?? ""))) latest = id;
  }
  return latest;
}

export function AcademyStudyPage({ villageCourse, course, favoriteBusy, onFavorite, learn, refresh, onClose }: StudyProps) {
  const materials = course.materials ?? [];
  const chapters = course.chapters?.length ? course.chapters : [defaultChapter(materials)];
  const chapterStates: NonNullable<AcademyItem["chapterProgress"]> = course.chapterProgress ?? { [chapters[0].id]: { reflection:course.reflection ?? null } };
  const chapterRecord = (ch: AcademyChapter) => chapterStates[ch.id];
  const isChapterDone = (ch: AcademyChapter) => chapterCompleted(ch, chapterRecord(ch));
  const [chapterId, setChapterId] = useState(() => {
    const unfinished = chapters.filter(ch => !isChapterDone(ch));
    const ids = unfinished.flatMap(ch => ch.sections.flatMap(section => section.materialIds));
    const lastVideo = recentlyWatched(ids, course.videoProgressById ?? {});
    const resumed = lastVideo && unfinished.find(ch => ch.sections.some(section => section.materialIds.includes(lastVideo)));
    return (resumed || unfinished[0] || chapters[0]).id;
  });
  const chapter = chapters.find(ch => ch.id === chapterId) ?? chapters[0];
  const [tab,setTab] = useState(overviewId);
  const [reading,setReading] = useState(false);
  useEffect(() => {
    const restore = () => {
      const url = new URL(window.location.href);
      const selected = url.searchParams.get("studyTab") || overviewId;
      setTab(tabIds.includes(selected) ? selected : overviewId);
      setReading(false);
      const ch = url.searchParams.get("studyChapter");
      if(ch) setChapterId(ch);
    };
    restore();
    window.addEventListener("popstate",restore);
    return () => window.removeEventListener("popstate",restore);
  }, [course.id]);
  function showTab(id:string, target=id, ch=chapter.id, openReader=false) {
    setTab(id);
    setReading(openReader);
    const url = new URL(window.location.href);
    url.searchParams.set("studyTab",id);
    url.searchParams.set("studyChapter",ch);
    if(url.href!==window.location.href) window.history.pushState({...window.history.state,journeyStudyCourse:course.id},"",url);
    requestAnimationFrame(()=>goToSection(target===id ? "go-"+id : target));
  }
  const [expanded, setExpanded] = useState(() => new Set([chapter.id]));
  const record = chapterRecord(chapter) ?? { reflection:null }, reflection = record.reflection;
  const materialMap = new Map(materials.map(m => [m.id, m]));
  const sectionMaterials = (ids: string[]) => ids.flatMap(id => { const m = materialMap.get(id); return m ? [m] : []; });
  const items = sectionMaterials(chapter.sections.flatMap(s => s.materialIds));
  const opened = new Set(course.openedMaterialIds ?? []);
  const [liveWatches, setLiveWatches] = useState<Record<string, AcademyWatchSnapshot>>({});
  const watches = { ...course.videoProgressById };
  for (const [id, live] of Object.entries(liveWatches)) {
    const saved = watches[id];
    if (!saved || (!saved.completed && (live.completed || live.watchedSeconds >= saved.watchedSeconds))) watches[id] = live;
  }
  const completedVideos = new Set(course.completedVideoIds);
  for (const [id, watch] of Object.entries(watches)) {
    if (watch.completed) completedVideos.add(id);
  }
  const isRead = (item: AcademyMedia) => item.kind === "video" ? completedVideos.has(item.id) : opened.has(item.id);
  function resumeItem(list: AcademyMedia[]) {
    const unread = list.filter(item => !isRead(item));
    const recent = recentlyWatched(unread.map(item => item.id), watches);
    return unread.find(item => item.id === recent) ?? unread[0];
  }
  const readCount = materials.filter(isRead).length;
  const [selection, setSelection] = useState(() => ({
    id: (resumeItem(items) ?? items[0])?.id,
    play: false,
    request: 0,
  }));
  const current = items.find(item => item.id === selection.id) ?? items[0];
  const currentIndex = current ? items.indexOf(current) : -1;
  const following = items[currentIndex + 1];
  const [drafts, setDrafts] = useState<Record<string,string>>({});
  const text = drafts[chapter.id] ?? reflection?.text ?? "";
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [favoriting, setFavoriting] = useState(false);
  const [favoriteError, setFavoriteError] = useState("");
  const [readError, setReadError] = useState<{id: string; message: string} | null>(null);
  const queued = useRef(new Set<string>());
  const queue = useRef<Promise<void>>(Promise.resolve());
  const submitting = useRef(false);
  const refreshedVideo = useRef(new Set<string>());

  function recordOpen(materialId: string) {
    if (opened.has(materialId) || queued.current.has(materialId)) return;
    queued.current.add(materialId);
    queue.current = queue.current.then(async () => {
      try {
        await learn({ command: "readMaterial", id: course.id, revision: course.revision, materialId });
        setReadError(previous => previous?.id === materialId ? null : previous);
      } catch (e) {
        setReadError({ id: materialId, message: failureMessage(e) });
      } finally {
        queued.current.delete(materialId);
      }
    });
  }

  const onWatchProgress = useCallback((snapshot: AcademyWatchSnapshot, materialId: string) => {
    setLiveWatches(previous => {
      const last = previous[materialId];
      if (last && last.watchedSeconds === snapshot.watchedSeconds && last.durationSeconds === snapshot.durationSeconds &&
          last.completed === snapshot.completed) return previous;
      return { ...previous, [materialId]: snapshot };
    });
    if (snapshot.completed && !course.completedVideoIds?.includes(materialId) && !refreshedVideo.current.has(materialId)) {
      refreshedVideo.current.add(materialId);
      void refresh();
    }
  }, [course.completedVideoIds, refresh]);

  const videoRemaining = items.filter(item => item.kind === "video" && !isRead(item)).length;
  const otherRemaining = items.filter(item => item.kind !== "video" && !isRead(item)).length;
  const passed = reflection?.status === "passed";
  const allowed = !passed && items.every(isRead);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current || !allowed || !text.trim()) return;
    submitting.current = true;
    setSaving(true);
    setError("");
    try {
      await learn({ command: "reflection", id: course.id, revision: course.revision, chapterId: chapter.id, text: text.trim() });
      await refresh();
    } catch (e) {
      setError(failureMessage(e));
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  }

  async function favoriteCourse() {
    if (favoriting) return;
    setFavoriting(true);
    setFavoriteError("");
    try { await onFavorite(course); }
    catch (e) { setFavoriteError(failureMessage(e)); }
    finally { setFavoriting(false); }
  }

  const materialSection = { id: "academy-course-materials", label: "课程目录" };
  const reflectionSection = { id: "academy-course-reflection", label: "章节心得与考核" };
  const nextMaterial = resumeItem(items);
  const previewVideo = items.find(item => item.kind === "video" && !isRead(item)) ?? items.find(item => item.kind === "video");
  const featuredVideo = current?.kind === "video" ? current : previewVideo;
  const featuredWatch = featuredVideo && watches[featuredVideo.id];
  const featuredDuration = featuredWatch?.durationSeconds ?? featuredVideo?.durationSeconds ?? 0;
  const featuredComplete = !!featuredVideo && completedVideos.has(featuredVideo.id);
  const videoLearning = featuredVideo && {
    title: featuredVideo.title,
    watchedSeconds: featuredComplete ? featuredDuration : Math.min(featuredDuration, featuredWatch?.watchedSeconds ?? 0),
    durationSeconds: featuredDuration,
    completed: featuredComplete,
  };
  const liveMaterialPercent = academyMaterialProgressPercent(materials, course.openedMaterialIds ?? [], watches);
  const overallPercent = course.completed ? 100 : Math.max(course.progress, academyOverallPercent(materials.length, liveMaterialPercent, chapters, chapterStates));
  const writing = !passed && (reflection || !nextMaterial);
  const assessmentDue = items.every(isRead) && ((chapter.exam && !record.exam) || (chapter.homework && !record.homework));
  const actionLabel = assessmentDue ? "完成章末考核" : writing
    ? reflection?.status === "pending" ? "查看评审状态" : reflection?.status === "retry" ? "修改章节心得" : "写章节心得"
    : passed ? "回顾章节" : overallPercent > 0 || readCount || course.seconds || (videoLearning?.watchedSeconds ?? 0) > 0 ? "继续学习" : "开始学习";
  function selectChapter(ch: AcademyChapter, material?: AcademyMedia) {
    setChapterId(ch.id);
    setExpanded(previous => previous.has(ch.id) ? previous : new Set([...previous, ch.id]));
    const list = sectionMaterials(ch.sections.flatMap(sec=>sec.materialIds));
    setSelection({id:(material ?? resumeItem(list) ?? list[0])?.id, play:false, request:0});
    setError("");
  }
  function openMaterial(material: AcademyMedia, startVideo = false, ch=chapter.id) {
    const play = startVideo && material.kind === "video";
    setSelection(previous => ({ id: material.id, play, request: previous.request + (play ? 1 : 0) }));
    showTab(materialId,"academy-active-material",ch,true);
  }
  function toggleChapter(id: string) {
    setExpanded(previous => {
      const updated = new Set(previous);
      if (updated.has(id)) updated.delete(id);
      else updated.add(id);
      return updated;
    });
  }
  function startLearning() {
    if (writing || assessmentDue || (!items.length && !course.contentText && !course.summary)) {
      showTab(reflectionId);
    } else if (items.length) {
      openMaterial(current && !isRead(current) ? current : nextMaterial ?? items[0], true);
    } else {
      showTab(overviewId);
    }
  }

  return <AcademyStudyLayout villageCourse={villageCourse} course={course} overallPercent={overallPercent} completedMaterialCount={readCount} videoLearning={videoLearning}
    onClose={onClose} favoriteBusy={favoriteBusy || favoriting} favoriteError={favoriteError}
    onFavorite={() => void favoriteCourse()} actionLabel={actionLabel} onStart={startLearning}
    onPreviewVideo={featuredVideo ? () => openMaterial(featuredVideo, true) : undefined}
    tab={tab} onTab={id=>showTab(id)} sectionLinks={[materialSection, reflectionSection]}>
      <section role="tabpanel" aria-labelledby={"go-"+materialId} hidden={tab !== materialId} id={materialSection.id} className="academy-study-section" tabIndex={-1}>
        {!reading && <><div className="academy-study-bar"><h2>课程目录</h2><span>已完成 {chapters.filter(isChapterDone).length} / {chapters.length} 章</span></div>
        {materials.some(m => m.kind === "video") && <p className="study-player-breadcrumb">{villageCourse && !course.required ? "任务视频进度" : "整套视频进度"} · 已看完 {materials.filter(m => m.kind === "video" && completedVideos.has(m.id)).length} / {materials.filter(m => m.kind === "video").length} 个视频</p>}
        <nav className="study-syllabus" aria-label="章节与学习任务">
          {chapters.map((ch, chapterIndex) => {
            const sections = ch.sections.map(section => ({ ...section, materials: sectionMaterials(section.materialIds) }));
            const list = sections.flatMap(section => section.materials);
            const complete = isChapterDone(ch);
            const chapterProgress = academyOverallPercent(list.length,
              academyMaterialProgressPercent(list, course.openedMaterialIds ?? [], watches), [ch], chapterStates);
            const panelId = `study-chapter-materials-${chapterIndex}`;
            return <div key={ch.id} className="study-chapter" data-active={ch.id === chapter.id}>
              <h3><button type="button" className="study-chapter-toggle" aria-expanded={expanded.has(ch.id)}
                aria-controls={panelId} onClick={() => toggleChapter(ch.id)}>
                <span className="study-chapter-heading"><small>第 {chapterIndex + 1} 章</small><strong>{ch.title}</strong></span>
                <span className="study-chapter-meta">{list.length} 个学习任务</span>
                <span className="study-chapter-progress" data-done={complete}>{complete ? "已完成" : `进度 ${chapterProgress}%`}</span>
                <span className="study-chapter-chevron" aria-hidden="true">⌄</span>
              </button></h3>
              <div id={panelId} hidden={!expanded.has(ch.id)}>
                {sections.filter(section => section.materials.length).map(section => <div className="study-outline-section" key={section.id}>
                  {!section.chapterLevel && <h4>{section.title}</h4>}
                  {section.materials.map(item => {
                    const selected = ch.id === chapter.id && item.id === current?.id;
                    const read = isRead(item);
                    const watch = watches[item.id];
                    return <button type="button" key={item.id} className="study-material-row" aria-current={selected ? "true" : undefined}
                      onClick={() => { if (ch.id !== chapter.id) selectChapter(ch, item); openMaterial(item,false,ch.id); }}>
                      <span className="study-material-kind">{taskNumber(list.indexOf(item) + 1)}</span>
                      <span className="study-material-title"><strong>{taskName(item)}</strong><small>{taskMaterialType(item)} · {item.title}</small></span>
                      {selected && <span className="study-material-current">当前</span>}
                      <span className="study-material-state" data-read={read}>{read ? "已学完"
                        : watch?.watchedSeconds > 0 ? `已看 ${academyVideoProgressPercent(watch)}%` : "待学习"}</span>
                    </button>;
                  })}
                </div>)}
                <button className="study-chapter-assessment" type="button" onClick={() => {
                  if (chapter.id !== ch.id) selectChapter(ch);
                  showTab(reflectionId,reflectionId,ch.id);
                }}>{ch.exam || ch.homework ? "章节心得与考核" : "章节心得"} <span aria-hidden="true">→</span></button>
              </div>
            </div>;
          })}
        </nav></>}
        {tab === materialId && reading && current && <div className="academy-study-material" id="academy-active-material" tabIndex={-1} key={current.id}>
          <p className="study-player-breadcrumb">第 {chapters.indexOf(chapter) + 1} 章 · {chapter.title} · {taskNumber(currentIndex + 1)}（共 {items.length} 个任务）</p>
          <h3>{taskName(current)}</h3><p>{taskMaterialType(current)} · {current.title}</p>
          {current.kind === "video"
            ? <AcademyTrackedVideo villageCourse={villageCourse} courseId={course.id} revision={course.revision} material={current} overallPercent={overallPercent}
                playRequest={selection.play && selection.id === current.id ? selection.request : 0} onProgress={onWatchProgress} />
            : <ReadingMaterial material={current} onRead={() => recordOpen(current.id)} />}
          <div className="study-material-navigation">
            <LearnerBack onClick={() => showTab(materialId)}>返回课程目录</LearnerBack>
            <button type="button" className="study-material-next" onClick={() => following ? openMaterial(following) : showTab(reflectionId)}>
              {following ? `下一任务 · ${taskName(following)}` : "本章学习心得"} <span aria-hidden="true">→</span>
            </button>
          </div>
        </div>}
        {readError && <p role="alert" className="academy-error">{readError.message}
          <button type="button" className="module-secondary" onClick={() => recordOpen(readError.id)}>重试记录</button>
        </p>}
      </section>
      <section role="tabpanel" aria-labelledby={"go-"+reflectionId} hidden={tab !== reflectionId} id={reflectionSection.id} className="academy-study-section academy-study-reflection" tabIndex={-1}>
        {chapters.length>1 && <label className="study-reflection-chapter">选择章节 <select value={chapter.id} onChange={e=>{const next=chapters.find(ch=>ch.id===e.target.value);if(next){selectChapter(next);showTab(reflectionId,reflectionId,next.id);}}}>{chapters.map((ch,i)=><option key={ch.id} value={ch.id}>第 {i+1} 章 · {ch.title}</option>)}</select></label>}
        <div className="academy-study-bar"><h2>{chapter.title} · 章节心得</h2></div>
        {reflection && <ReflectionResult reflection={reflection} />}
        {!passed && <form onSubmit={submit}>
          <label className="module-field"><span>结合本章内容，写下你的理解和实际应用。</span>
            <textarea rows={5} maxLength={8000} required value={text} disabled={saving}
              onChange={event => { const value=event.target.value; setDrafts(previous=>({...previous,[chapter.id]:value})); }} />
          </label>
          <div className="academy-study-submit">
            {videoRemaining > 0 || otherRemaining > 0 ? <small>
              {videoRemaining > 0 && `还有 ${videoRemaining} 份视频需要看完。`}
              {otherRemaining > 0 && `还有 ${otherRemaining} 份材料需要打开。`}
            </small> : <small>{text.length} / 8000</small>}
            <button type="submit" className="module-primary" disabled={saving || !allowed || !text.trim()}>
              {villageCourse ? (saving ? "正在保存…" : "提交本章心得") : saving ? "正在评审…" : reflection ? "重新提交评审" : "提交心得并评审"}
            </button>
          </div>
        </form>}
        {error && <p className="academy-error" role="alert">{error}</p>}
        {(["exam", "homework"] as const).map(kind => chapter[kind] && <ChapterAssessment key={chapter.id+kind}
          title={kind==="exam"?"课后考试":"课后作业"} prompt={chapter[kind]} xp={kind==="exam"?EXAM_XP:chapter.homeworkXp}
          submission={record[kind]} unlocked={items.every(isRead)} onSubmit={async answer => {
            await learn({command:"assessment",id:course.id,revision:course.revision,chapterId:chapter.id,kind,text:answer});
            await refresh();
          }} />)}
        {isChapterDone(chapter) && chapters[chapters.indexOf(chapter)+1] && <button type="button" className="module-primary"
          onClick={()=>{const next=chapters[chapters.indexOf(chapter)+1];selectChapter(next);showTab(materialId,materialId,next.id);}}>学习下一章 →</button>}
      </section>
  </AcademyStudyLayout>;
}
