"use client";

import { useState } from "react";
import { ModuleCourseArtwork } from "./ModuleCourseArtwork";
import type { AcademyItem } from "./useAcademy";

/** Only our authenticated cover endpoint may be used as an image source. */
export function academyCoverSource(course: Pick<AcademyItem, "id" | "coverUrl">): string | undefined {
  if (!course.coverUrl) return undefined;
  const match = /^\/api\/v1\/(?:me|ops)\/academy\/courses\/([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})\/cover\?source=([a-f0-9]{64})$/i.exec(course.coverUrl);
  if (!match || match[1].toLowerCase() !== course.id.toLowerCase()) return undefined;
  return `/api/learner/academy/courses/${match[1]}/cover?source=${match[2]}`;
}

export function AcademyCourseCover({ course, index }: { course: AcademyItem; index: number }) {
  const source = academyCoverSource(course);
  return <CourseCoverImage key={source || "default"} source={source} type={course.type} index={index} />;
}

function CourseCoverImage({ source, type, index }: { source?: string; type: AcademyItem["type"]; index: number }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  return <>
    {!loaded && <><ModuleCourseArtwork index={index} /><span className="module-cover-label">{type === "video" ? "ACADEMY CINEMA" : type === "share" ? "CO-CREATION" : "KNOWLEDGE PORTAL"}</span></>}
    {source && !failed && <img className={`academy-cover-image${loaded ? " is-loaded" : ""}`} src={source} alt="" loading="lazy" decoding="async" onLoad={() => setLoaded(true)} onError={() => { setLoaded(false); setFailed(true); }} />}
  </>;
}
