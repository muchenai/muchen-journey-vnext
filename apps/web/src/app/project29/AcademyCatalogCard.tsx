"use client";

import { useEffect, useId, useRef, useState } from "react";
import { AcademyCourseCover, academyArtworkIndex } from "./AcademyCourseCover";
import { ModuleIcon } from "./ModuleShell";
import type { AcademyItem } from "./useAcademy";
import "./academyCatalogCards.css";

type CardActions = {
  category: (course: AcademyItem) => string;
  learningStatus: (course: AcademyItem) => string;
  busyFavorite: string;
  courseHref: (id: string) => string;
  onFavorite: (course: AcademyItem) => void;
};

type SectionProps = CardActions & {
  title: string;
  courses: AcademyItem[];
  layout?: "grid" | "shelf";
};

export function AcademyCatalogCard({ course, category, learningStatus, busyFavorite, courseHref, onFavorite }:
  CardActions & { course: AcademyItem }) {
  const format = category(course);
  const favoriteLabel = course.favorite ? "取消收藏" : "收藏课程";
  return (
    <article className="academy-catalog-card">
      <div className="academy-catalog-cover">
        <AcademyCourseCover course={course} index={academyArtworkIndex(course.id)} />
        <span className="academy-catalog-format" title={format}>{format}</span>
        {course.tags.length > 0 && (
          <div className="academy-catalog-tags" aria-label="课程标签">
            {course.tags.slice(0, 2).map(tag => <span key={tag} title={tag}>{tag}</span>)}
          </div>
        )}
      </div>
      <div className="academy-catalog-body">
        <h3>
          <a className="academy-catalog-open academy-course-link" title={course.title} href={courseHref(course.id)}>
            {course.title}
          </a>
        </h3>
        <p className="academy-catalog-author" title={course.author.name}>{course.author.name}</p>
        {course.summary && <p className="academy-catalog-description" title={course.summary}>{course.summary}</p>}
        <footer className="academy-catalog-meta">
          <span className="academy-catalog-status">
            <ModuleIcon file="42cb2" size={14} />{learningStatus(course)}
          </span>
          <span>{course.minutes} 分钟</span>
        </footer>
      </div>
      <button type="button" className="academy-catalog-save" disabled={Boolean(busyFavorite)}
        aria-pressed={course.favorite} aria-label={favoriteLabel + "：" + course.title} title={favoriteLabel}
        onClick={() => onFavorite(course)}>
        <ModuleIcon file={course.favorite ? "b5cc7" : "cdc4e"} size={18} />
      </button>
    </article>
  );
}

export function AcademyCatalogSection({ title, courses, layout = "grid", ...actions }: SectionProps) {
  const heading = useId();
  const listId = useId();
  const list = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ previous: false, next: false });
  const shelf = layout === "shelf";

  useEffect(() => {
    const element = list.current;
    if (!shelf || !element) return;
    function measure() {
      if (!element) return;
      const previous = element.scrollLeft > 2;
      const next = element.scrollLeft + element.clientWidth < element.scrollWidth - 2;
      setEdges(current => current.previous === previous && current.next === next ? current : { previous, next });
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    element.addEventListener("scroll", measure, { passive: true });
    return () => {
      observer.disconnect();
      element.removeEventListener("scroll", measure);
    };
  }, [shelf, courses.length]);

  function turnPage(direction: number) {
    const element = list.current;
    const card = element?.firstElementChild;
    if (!element || !(card instanceof HTMLElement)) return;
    const gap = parseFloat(getComputedStyle(element).columnGap) || 0;
    const stride = card.offsetWidth + gap;
    const count = Math.max(1, Math.round((element.clientWidth + gap) / stride));
    element.scrollBy({ left: direction * stride * count,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }

  if (!courses.length) return null;
  return (
    <section className="academy-catalog-section" aria-labelledby={heading}>
      <h2 id={heading}>{title}</h2>
      <div className="academy-catalog-shelf">
        <div ref={list} id={listId} className="academy-catalog-list" data-layout={layout}>
          {courses.map(course => <AcademyCatalogCard key={course.id} course={course} {...actions} />)}
        </div>
        {shelf && (edges.previous || edges.next) && (
          <>
            <button type="button" className="academy-catalog-page is-previous" aria-label={title + "，上一组"}
              aria-controls={listId} disabled={!edges.previous} onClick={() => turnPage(-1)}><ModuleIcon file="409af" size={18} /></button>
            <button type="button" className="academy-catalog-page is-next" aria-label={title + "，下一组"}
              aria-controls={listId} disabled={!edges.next} onClick={() => turnPage(1)}><ModuleIcon file="409af" size={18} /></button>
          </>
        )}
      </div>
    </section>
  );
}
