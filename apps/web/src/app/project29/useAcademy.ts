"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AcademyItem = {
  id: string; type: "link" | "video" | "share"; title: string; summary: string; url: string;
  minutes: number; tags: string[]; author: { id: string; name: string }; revision: number;
  createdAt: string; updatedAt: string; visibility: "published" | "unpublished";
  videoName?: string; videoSize?: number; videoUrl?: string; coverUrl?: string;
  progress: number; completed: boolean; favorite: boolean; seconds: number; duration: number;
};
export type AcademyShare = {
  id: string; title: string; summary: string; url: string; minutes: number; tags: string[];
  status: "pending" | "approved" | "rejected"; reason: string; revision: number;
  createdAt: string; updatedAt: string; reviewedAt?: string;
};
export type AcademySnapshot = { courses: AcademyItem[]; shares: AcademyShare[]; tags: string[] };

export async function academyRequest<T>(body?: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/api/learner/academy", {
    credentials: "same-origin", cache: "no-store", signal,
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "学院内容读取失败，请重试。");
  return data as T;
}

export function useAcademy(active: boolean) {
  const [data, setData] = useState<AcademySnapshot>({ courses: [], shares: [], tags: [] });
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const refresh = useCallback(async () => {
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    try {
      const result = await academyRequest<AcademySnapshot>(undefined, request.signal);
      if (!request.signal.aborted && alive.current) { setData(result); setError(""); setLoading(false); }
    } catch (e) {
      if (!request.signal.aborted && alive.current) { setError(e instanceof Error ? e.message : "学院内容读取失败。"); setLoading(false); }
    }
  }, []);
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
    const result = await academyRequest<{ id: string; saved: boolean }>({ command: "favorite", id, saved });
    controller.current?.abort();
    if (alive.current) setData(previous => ({ ...previous, courses: previous.courses.map(item => item.id === result.id ? { ...item, favorite: result.saved } : item) }));
  }, []);
  const progress = useCallback(async (id: string, seconds: number, duration: number, completed?: boolean, revision?: number) => {
    const result = await academyRequest<AcademyItem>({ command: "progress", id, seconds, duration, ...(completed === undefined ? {} : { completed }), ...(revision === undefined ? {} : { revision }) });
    update(result);
    return result;
  }, [update]);
  return { ...data, loading, error, refresh, favorite, progress };
}
