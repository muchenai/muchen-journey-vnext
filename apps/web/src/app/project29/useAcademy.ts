"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AcademyMedia, AcademyWatchSnapshot } from "@/lib/academy-learning-media";

import type { AcademyChapter, ChapterSubmission } from "@/lib/academy-chapters";

export type AcademyReflection = {
  text: string;
  status: "passed" | "retry" | "pending";
  feedback: string;
  score?: number | null;
  awardedXp?: number;
};

export type AcademyItem = {
  id: string; type: "link" | "video" | "share"; title: string; summary: string; url: string;
  minutes: number; tags: string[]; author: { id: string; name: string }; revision: number;
  createdAt?: string | null; updatedAt?: string | null; visibility: "published" | "unpublished";
  videoName?: string; videoSize?: number; videoUrl?: string; coverUrl?: string; coverVideoUrl?: string;
  progress: number; completed: boolean; favorite: boolean; seconds: number; duration: number;
  watchedSeconds?: number;
  enhanced?: boolean;
  chapters?: AcademyChapter[];
  chapterProgress?: Record<string, { reflection: AcademyReflection | null; exam?: ChapterSubmission; homework?: ChapterSubmission }>;
  required?: boolean;
  requiredSince?: string;
  requiredTopic?: string;
  contentText?: string;
  materials?: AcademyMedia[];
  openedMaterialIds?: string[];
  completedVideoIds?: string[];
  videoProgressById?: Record<string, AcademyWatchSnapshot>;
  rewardXp?: number;
  seriesRewardSettled?: boolean;
  reflection?: AcademyReflection | null;
};
// Earlier course responses could carry a null progress timestamp as updatedAt.
export function courseUpdateTime(course: Pick<AcademyItem, "updatedAt" | "createdAt">): number | undefined {
  for (const value of [course.updatedAt, course.createdAt]) {
    if (!value) continue;
    const time = Date.parse(value);
    if (Number.isFinite(time)) return time;
  }
}
export type AcademyShare = {
  id: string; title: string; summary: string; url: string; minutes: number; tags: string[];
  status: "pending" | "approved" | "rejected"; reason: string; revision: number;
  createdAt: string; updatedAt: string; reviewedAt?: string;
};
export type AcademySnapshot = {
  courses: AcademyItem[]; shares: AcademyShare[]; tags: string[];
  lockedCourses?: { id: string; title: string }[];
  learner?: { id: string; name: string };
  academyXp?: number;
};

class AcademyRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

type CourseScope = "academy" | "village";

export async function academyRequest<T>(body?: Record<string, unknown>, signal?: AbortSignal, scope: CourseScope = "academy"): Promise<T> {
  const response = await fetch(scope === "village" ? "/api/learner/village/courses" : "/api/learner/academy", {
    credentials: "same-origin", cache: "no-store", signal,
    keepalive: body?.command === "progress",
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || data === null) throw new AcademyRequestError(typeof data?.error === "string" ? data.error : "学院内容读取失败，请确认网络后重试。", response.status);
  return data as T;
}

export function useAcademy(active: boolean, scope: CourseScope = "academy") {
  const [data, setData] = useState<AcademySnapshot>({ courses: [], shares: [], tags: [] });
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const identityGeneration = useRef(0);
  const refresh = useCallback(async () => {
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    try {
      const result = await academyRequest<AcademySnapshot>(undefined, request.signal, scope);
      if (!request.signal.aborted && alive.current) { setData(result); setError(""); setLoading(false); }
    } catch (e) {
      if (!request.signal.aborted && alive.current) {
        const expired = e instanceof AcademyRequestError && [401,403].includes(e.status);
        if (expired) {
          identityGeneration.current++;
          setData({ courses: [], shares: [], tags: [] });
        }
        setError(e instanceof Error ? e.message : "学院内容读取失败。");
        setLoading(false);
      }
    }
  }, [scope]);
  useEffect(() => {
    alive.current = true;
    if (!active) return;
    const initial = window.setTimeout(() => void refresh(), 0);
    const onFocus = () => { if (!document.hidden) void refresh(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    const timer = window.setInterval(onFocus, 30000);
    return () => { window.clearTimeout(initial); controller.current?.abort(); window.clearInterval(timer); window.removeEventListener("focus", onFocus); document.removeEventListener("visibilitychange", onFocus); };
  }, [active, refresh]);
  useEffect(() => () => { alive.current = false; controller.current?.abort(); }, []);
  const update = useCallback((course: AcademyItem) => {
    controller.current?.abort();
    if (alive.current) setData(previous => ({ ...previous, courses: previous.courses.map(item => item.id === course.id ? course : item) }));
  }, []);
  const favorite = useCallback(async (id: string, saved: boolean) => {
    const generation = identityGeneration.current;
    const result = await academyRequest<{ id: string; saved: boolean }>({ command: "favorite", id, saved }, undefined, scope);
    if (generation !== identityGeneration.current) return;
    controller.current?.abort();
    if (alive.current) setData(previous => ({ ...previous, courses: previous.courses.map(item => item.id === result.id ? { ...item, favorite: result.saved } : item) }));
  }, [scope]);
  const progress = useCallback(async (id: string, seconds: number, duration: number, completed?: boolean, revision?: number) => {
    const generation = identityGeneration.current;
    const result = await academyRequest<AcademyItem>({ command: "progress", id, seconds, duration, ...(completed === undefined ? {} : { completed }), ...(revision === undefined ? {} : { revision }) }, undefined, scope);
    if (generation === identityGeneration.current) update(result);
    return result;
  }, [scope, update]);
  const learn = useCallback(async (body: Record<string, unknown>) => {
    const generation = identityGeneration.current;
    const course = await academyRequest<AcademyItem>(body, undefined, scope);
    if (generation === identityGeneration.current) update(course);
    return course;
  }, [scope, update]);
  return { ...data, loading, error, refresh, favorite, progress, learn };
}
