"use client";

import { useRef, useState } from "react";
import { academyVideoProgressPercent, type AcademyWatchSnapshot } from "./academyVideoProgress";
import { AcademyLegacyVideo } from "./AcademyLegacyVideo";
import { AcademyStudyLayout } from "./AcademyStudyLayout";
import type { AcademyItem } from "./useAcademy";

type Props = {
  course: AcademyItem;
  villageCourse?: boolean;
  onClose: () => void;
  onProgress: (id: string, seconds: number, duration: number, completed?: boolean, revision?: number) => Promise<AcademyItem>;
  onFavorite: (course: AcademyItem) => Promise<void>;
};

const materialId = "legacy-course-material";
const sectionLinks = [{ id: materialId, label: "学习材料" }];
const errorMessage = (failure: unknown) => failure instanceof Error ? failure.message : "操作失败，请重试。";

function externalCourseUrl(value: string) {
  if (!value || /[\\\u0000-\u001f]/.test(value)) return undefined;
  try {
    const url = new URL(value);
    if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password) return url.href;
  } catch { /* Invalid links are shown as unavailable. */ }
  return undefined;
}

export function AcademyLegacyStudyPage({ course, villageCourse, onClose, onProgress, onFavorite }: Props) {
  const section = useRef<HTMLElement>(null);
  const startVideo = useRef<(() => void) | null>(null);
  const link = useRef<HTMLAnchorElement>(null);
  const [busy, setBusy] = useState(false);
  const [favoriting, setFavoriting] = useState(false);
  const [favoriteError, setFavoriteError] = useState("");
  const [error, setError] = useState("");
  const [videoWatch, setVideoWatch] = useState<AcademyWatchSnapshot | null>(null);
  const isVideo = course.type === "video";
  const duration = videoWatch?.durationSeconds || course.duration || 0;
  const watched = Math.min(duration, Math.max(course.seconds, videoWatch?.watchedSeconds ?? 0));
  const videoLearning = isVideo ? {
    title: course.videoName || course.title,
    watchedSeconds: watched,
    durationSeconds: duration,
    completed: videoWatch?.completed ?? (duration > 0 && watched >= duration),
  } : undefined;
  const overallPercent = course.completed ? 100 : Math.min(100, Math.max(0, Math.floor(course.progress),
    videoLearning ? academyVideoProgressPercent(videoLearning) : 0));
  const externalUrl = externalCourseUrl(course.url);

  async function complete() {
    if (busy || course.completed) return;
    setBusy(true);
    try {
      const duration = course.minutes * 60;
      await onProgress(course.id, duration, duration, true, course.revision);
      setError("");
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  async function favoriteCourse() {
    if (favoriting) return;
    setFavoriting(true);
    setFavoriteError("");
    try { await onFavorite(course); }
    catch (failure) { setFavoriteError(errorMessage(failure)); }
    finally { setFavoriting(false); }
  }

  function start() {
    section.current?.focus({ preventScroll: true });
    section.current?.scrollIntoView({ block: "start" });
    if (isVideo) {
      startVideo.current?.();
    } else {
      link.current?.click();
    }
  }

  return <AcademyStudyLayout course={course} villageCourse={villageCourse} overallPercent={overallPercent} videoLearning={videoLearning} onClose={onClose} sectionLinks={sectionLinks}
    onFavorite={favoriteCourse} favoriteBusy={favoriting} favoriteError={favoriteError}
    actionLabel={course.completed ? "复习课程" : course.seconds > 0 ? "继续学习" : "开始学习"} onStart={start}>
    <section ref={section} id={materialId} tabIndex={-1} className="academy-study-section">
      <h2>学习材料</h2>
      {isVideo ? <AcademyLegacyVideo course={course} startRef={startVideo} overallPercent={overallPercent}
        onProgress={onProgress} onLearningProgress={setVideoWatch} /> : <div className="academy-link-actions">
        {externalUrl ? <a ref={link} className="module-primary" href={externalUrl} target="_blank" rel="noopener noreferrer"
          onClick={() => { void onProgress(course.id, Math.max(course.seconds, 1), course.minutes * 60, undefined, course.revision)
            .catch(failure => setError(errorMessage(failure))); }}>打开课程内容 ↗</a>
          : <p role="alert" className="academy-error">课程链接无效，请联系发布人更新。</p>}
        <button type="button" className="module-secondary" disabled={busy || course.completed} onClick={complete}>
          {busy ? "正在保存…" : course.completed ? "已完成学习" : "我已完成学习"}
        </button>
        {externalUrl && <p>课程在新窗口打开，阅读完成后回到这里记录学习状态。</p>}
      </div>}
      {error && <p role="alert" className="academy-error">{error}</p>}
    </section>
  </AcademyStudyLayout>;
}
