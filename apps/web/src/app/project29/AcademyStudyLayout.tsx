"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { academyMaterialNames, academyVideoProgressPercent } from "@/lib/academy-learning-media";
import { DEFAULT_SERIES_XP } from "@/lib/academy-chapters";
import { videoTime } from "./academyVideoProgress";
import { AcademyCourseCover, academyArtworkIndex } from "./AcademyCourseCover";
import { LearnerBack } from "./LearnerBack";
import { ModuleIcon } from "./ModuleShell";
import { courseUpdateTime, type AcademyItem } from "./useAcademy";
import "./academyStudyPage.css";

type StudySection = { id: string; label: string };

export function goToSection(id: string) {
  const section = document.getElementById(id);
  section?.focus({ preventScroll: true });
  section?.scrollIntoView({ block: "start", behavior: "instant" });
}

type LayoutProps = {
  villageCourse?: boolean;
  course: AcademyItem;
  overallPercent: number;
  completedMaterialCount?: number;
  videoLearning?: { title: string; watchedSeconds: number; durationSeconds: number; completed: boolean };
  onClose: () => void;
  onFavorite: () => void;
  favoriteBusy: boolean;
  favoriteError?: string;
  actionLabel: string;
  onStart: () => void;
  onPreviewVideo?: () => void;
  children: ReactNode;
  sectionLinks?: StudySection[];
  tab?: string;
  onTab?: (id:string)=>void;
};

function ProgressMeter({ label, percent }: { label: string; percent: number }) {
  return <div className="study-progress-row">
    <progress aria-label={label} max={100} value={percent} /><strong>{percent}<small>%</small></strong>
  </div>;
}

export function AcademyStudyLayout({ villageCourse, course, overallPercent, completedMaterialCount, videoLearning, onClose, onFavorite, favoriteBusy, favoriteError, actionLabel, onStart, onPreviewVideo, children, sectionLinks = [], tab, onTab }: LayoutProps) {
  const overview = { id: "academy-course-overview", label: "课程介绍" };
  const hasOverview = Boolean(onTab || course.summary || course.contentText);
  const sections = hasOverview ? [overview, ...sectionLinks] : sectionLinks;
  const body = useRef<HTMLDivElement>(null);
  const [activeSection, setActiveSection] = useState(sections[0]?.id);
  useEffect(() => {
    if (tab) return;
    const items = Array.from(body.current?.querySelectorAll<HTMLElement>(":scope > section[id]") ?? []);
    if (items.length < 2) return;
    const panel = body.current?.closest<HTMLElement>(".module-page-content");
    const scrollTarget = panel ?? window;
    function updateSection() {
      const bounds = panel?.getBoundingClientRect();
      const top = (bounds?.top ?? 0) + Math.min(180, (bounds?.height ?? window.innerHeight) / 3);
      const scroll = panel ?? document.documentElement;
      const atBottom = scroll.scrollTop > 0 && scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 2;
      const current = atBottom ? items[items.length - 1] : items.filter(item => item.getBoundingClientRect().top <= top).at(-1) ?? items[0];
      setActiveSection(current.id);
    }
    updateSection();
    scrollTarget.addEventListener("scroll", updateSection, { passive: true });
    window.addEventListener("resize", updateSection);
    return () => {
      scrollTarget.removeEventListener("scroll", updateSection);
      window.removeEventListener("resize", updateSection);
    };
  }, [course.id, course.revision, tab]);
  const state = course.completed ? "已完成" : course.reflection?.status === "retry" ? "心得需修改"
    : course.reflection?.status === "pending" ? "心得待评审" : course.enhanced && (overallPercent === 100 || !course.materials?.length) ? "待提交心得"
    : overallPercent > 0 || course.seconds > 0 || (videoLearning?.watchedSeconds ?? 0) > 0 || course.openedMaterialIds?.length ? "学习中" : "未开始";
  const kind = course.enhanced
    ? [...new Set(course.materials?.map(item => academyMaterialNames[item.kind]))].join(" · ") || "图文"
    : { video: "视频", link: "外链", share: "员工共建" }[course.type];
  const updated = courseUpdateTime(course);
  const author = course.author.name.trim();
  return <article className="academy-study-page" aria-labelledby="academy-study-title">
    <header className="study-head study-panel">
      <nav className="study-breadcrumb" aria-label="面包屑">
        <LearnerBack onClick={onClose} aria-label={villageCourse ? "返回新手村课程目录" : "返回 AI 学院课程目录"}>
          {villageCourse ? "返回新手村" : "返回 AI 学院"}
        </LearnerBack>
        <span aria-hidden="true">/</span><span aria-current="page">课程详情</span>
      </nav>
      <h1 id="academy-study-title">{course.title}</h1>
      <div className="study-byline">
        {villageCourse && <span>{course.required ? "必修课程" : "普通任务"}</span>}
        <span>{kind}</span>
        {course.minutes > 0 && <span>预计 {course.minutes} 分钟</span>}
        {course.enhanced && !!course.materials?.length && <span>{course.materials.length} 份学习材料</span>}
      </div>
      <div className="study-hero-grid">
        <div className="study-hero-cover">
          <AcademyCourseCover course={course} index={academyArtworkIndex(course.id)} />
          {(onPreviewVideo || (!course.enhanced && course.type === "video")) && <button className="study-cover-play" type="button" onClick={onPreviewVideo ?? onStart}>
            <span aria-hidden="true">▶</span> 观看视频
          </button>}
        </div>
        <div className="study-hero-details">
          {course.tags.length > 0 && <div className="study-labels" aria-label="课程标签">
            {course.tags.map(tag => <span key={tag}>{tag}</span>)}
          </div>}
          <div className="study-progress-card">
            <div className="study-progress-title"><h2>课程整体学习进度</h2><span data-complete={course.completed}>{state}</span></div>
            <ProgressMeter label="课程整体学习进度" percent={overallPercent} />
            {completedMaterialCount !== undefined && !!course.materials?.length &&
              <p className="study-progress-caption">已学完 {completedMaterialCount} / {course.materials.length} 份材料</p>}
            {videoLearning && <div className="study-video-learning">
              <div className="study-progress-title"><h3>视频学习进度</h3></div>
              <ProgressMeter label="视频学习进度" percent={academyVideoProgressPercent(videoLearning)} />
              <p className="study-progress-caption"><span>{videoLearning.title}</span>
                <span>已看 {videoTime(videoLearning.watchedSeconds)} / {videoLearning.durationSeconds > 0 ? videoTime(videoLearning.durationSeconds) : "--:--"}</span></p>
            </div>}
            {course.enhanced && <p className="study-reward">{villageCourse && !course.required ? "任务奖励" : "整套课程奖励"} <b>{course.rewardXp ?? DEFAULT_SERIES_XP} 经验</b> · {course.seriesRewardSettled ? "已结算" : course.materials?.some(m => m.kind === "video") ? (villageCourse && !course.required ? "看完本任务的全部视频后一次发放" : "看完所有章节的全部视频后一次发放") : "学完全部材料后一次发放"}</p>}
          </div>
          <div className="study-hero-actions">
            <button type="button" className="study-launch" onClick={onStart}>{actionLabel}<span aria-hidden="true">→</span></button>
            <button type="button" className="study-favorite" aria-pressed={course.favorite} disabled={favoriteBusy} onClick={onFavorite}>
              <ModuleIcon file={course.favorite ? "b5cc7" : "cdc4e"} size={17} />{course.favorite ? "已收藏" : "收藏课程"}
            </button>
          </div>
          {favoriteError && <p role="alert" className="academy-error">{favoriteError}</p>}
        </div>
      </div>
    </header>
    <div className="study-body-grid">
      <div className="study-main study-panel" ref={body}>
        {sections.length > 1 && <nav className="study-section-nav" role={onTab ? "tablist" : undefined} aria-label="课程内容导航">
          {sections.map(section => <button type="button" key={section.id} id={"go-"+section.id} role={onTab ? "tab" : undefined}
            aria-selected={onTab ? tab===section.id : undefined} tabIndex={onTab && tab!==section.id ? -1 : 0}
            onKeyDown={event=>{
              if(!onTab || !["ArrowLeft","ArrowRight","Home","End"].includes(event.key)) return;
              event.preventDefault();
              const index=sections.indexOf(section);
              const next=event.key==="Home"?0:event.key==="End"?sections.length-1:(index+(event.key==="ArrowRight"?1:-1)+sections.length)%sections.length;
              onTab(sections[next].id);
            }} aria-controls={section.id} aria-current={(tab ?? activeSection) === section.id ? "location" : undefined}
            onClick={() => onTab ? onTab(section.id) : goToSection(section.id)}>{section.label}</button>)}
        </nav>}
        {hasOverview && <section role={tab?"tabpanel":undefined} aria-labelledby={tab?"go-"+overview.id:undefined} hidden={!!tab && tab !== overview.id} id={overview.id} className="academy-study-section" tabIndex={-1}>
          <h2>{overview.label}</h2>
          {!course.summary && !course.contentText && <p>暂无课程介绍。</p>}
          {course.summary && <p className="academy-study-content">{course.summary}</p>}
          {course.contentText && course.contentText !== course.summary && <p className="academy-study-content">{course.contentText}</p>}
        </section>}
        {children}
      </div>
      <aside className="study-author study-panel" aria-label="课程信息">
        <h2>课程信息</h2>
        {author && <div className="study-author-row">
          <span className="study-avatar" aria-hidden="true">{Array.from(author)[0]}</span>
          <div><span>课程作者</span><strong>{author}</strong></div>
        </div>}
        {updated !== undefined && <dl><dt>最近更新</dt><dd>{new Date(updated).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" })}</dd></dl>}
      </aside>
    </div>
  </article>;
}
