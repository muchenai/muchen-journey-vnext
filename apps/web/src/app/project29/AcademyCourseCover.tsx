"use client";

import { useEffect, useRef, useState } from "react";
import { academyMediaSource } from "@/lib/academy-learning-media";
import { ModuleCourseArtwork } from "./ModuleCourseArtwork";
import type { AcademyItem } from "./useAcademy";

export function academyArtworkIndex(id: string) {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return hash % 6;
}

export function academyCoverSource(course: Pick<AcademyItem, "id" | "coverUrl" | "enhanced">): string | undefined {
  if (course.enhanced) return academyMediaSource(course.coverUrl);
  // The original academy serves covers through its authenticated proxy.
  if (!course.coverUrl) return undefined;
  const match = /^\/api\/v1\/(?:me|ops)\/academy\/courses\/([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})\/cover\?source=([a-f0-9]{64})$/i.exec(course.coverUrl);
  if (!match || match[1].toLowerCase() !== course.id.toLowerCase()) return undefined;
  return `/api/learner/academy/courses/${match[1]}/cover?source=${match[2]}`;
}

export function AcademyCourseCover({ course, index }: { course: AcademyItem; index: number }) {
  const source = academyCoverSource(course);
  const video = course.enhanced ? academyMediaSource(course.coverVideoUrl) : undefined;
  return <CourseCoverImage key={JSON.stringify([source, video])} source={source} video={video} type={course.type} index={index} />;
}

function CourseCoverImage({ source, video, type, index }: { source?: string; video?: string; type: AcademyItem["type"]; index: number }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  return <>
    {!loaded && <><ModuleCourseArtwork index={index} /><span className="module-cover-label">{type === "video" ? "ACADEMY CINEMA" : type === "share" ? "CO-CREATION" : "KNOWLEDGE PORTAL"}</span></>}
    {/* Protected local assets are fetched with the learner's session cookie. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    {source && !failed && <img className={`academy-cover-image${loaded ? " is-loaded" : ""}`} src={source} alt="" loading="lazy" decoding="async" onLoad={() => setLoaded(true)} onError={() => { setLoaded(false); setFailed(true); }} />}
    {(!source || failed) && video && <VideoCoverFrame source={video} loaded={loaded} setLoaded={setLoaded} />}
  </>;
}

function VideoCoverFrame({ source, loaded, setLoaded }: {
  source: string; loaded: boolean; setLoaded: (loaded: boolean) => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    // Fetch a frame only for cards near the viewport. The cover never plays
    // and is independent from the learner's tracked video player.
    const load = () => { element.src = source; };
    if (!window.IntersectionObserver) {
      load();
      return;
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        observer.disconnect();
        load();
      }
    }, { rootMargin: "250px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [source]);

  return <video ref={video} className={`academy-cover-image${loaded ? " is-loaded" : ""}`}
    aria-hidden="true" tabIndex={-1} muted playsInline preload="metadata" disablePictureInPicture disableRemotePlayback
    onLoadedMetadata={event => {
      const media = event.currentTarget;
      if (Number.isFinite(media.duration) && media.duration > 0) media.currentTime = Math.min(0.001, media.duration / 2);
    }}
    onLoadedData={() => setLoaded(true)} onSeeked={() => setLoaded(true)} onError={() => setLoaded(false)} />;
}
