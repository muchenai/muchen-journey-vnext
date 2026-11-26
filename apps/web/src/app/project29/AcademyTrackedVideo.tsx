"use client";

import { useEffect, useRef, useState } from "react";
import type { AcademyMedia, AcademyWatchSnapshot } from "@/lib/academy-learning-media";
import { AcademyVideoPlayer } from "./AcademyVideoPlayer";

type Props = {
  villageCourse?: boolean;
  courseId: string;
  revision: number;
  material: AcademyMedia;
  playRequest?: number;
  overallPercent?: number;
  onProgress?: (value: AcademyWatchSnapshot, materialId: string) => void;
};
type WatchReply = AcademyWatchSnapshot & { sessionId?: string | null };
type PlayerActions = { start: () => void; toggle: () => void; rewind: () => void; retry: () => void };

export function AcademyTrackedVideo({ villageCourse, courseId, revision, material, playRequest = 0, overallPercent, onProgress }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const controls = useRef<PlayerActions | null>(null);
  const callback = useRef(onProgress);
  const consumedRequest = useRef(0);
  const [snapshot, setSnapshot] = useState<AcademyWatchSnapshot | null>(null);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [position, setPosition] = useState(0);
  const [watchedSeconds, setWatchedSeconds] = useState<number | null>(null);
  const [mediaDuration, setMediaDuration] = useState(0);

  useEffect(() => { callback.current = onProgress; }, [onProgress]);

  useEffect(() => {
    const element = videoRef.current;
    if (!element) return;
    const video: HTMLVideoElement = element;
    const query = new URLSearchParams({ courseId, revision: String(revision), materialId: material.id });
    if (villageCourse) query.set("camp", "village");
    const url = "/api/learner/academy/watch?" + query;
    let active = true;
    let starting = false;
    let restoring = false;
    let waitingForGesture = false;
    let writePending = false;
    let session: string | null = null;
    let saved: WatchReply | null = null;
    let queue = Promise.resolve();
    let trustedPosition = 0;
    let frontier = 0;
    let reportedFrontier = -1;
    let expectedSeek: number | null = null;
    let lastSample = performance.now();
    let lastPaint = 0;
    let frame = 0;

    async function request(body?: Record<string, unknown>, keepalive = false): Promise<WatchReply> {
      const res = await fetch(url, {
        cache: "no-store", credentials: "same-origin",
        ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), keepalive } : {}),
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.error || "无法保存观看进度。");
      return result;
    }

    function reportLearning(positionSeconds: number) {
      if (!active || !saved) return;
      reportedFrontier = frontier;
      setWatchedSeconds(frontier);
      callback.current?.({ ...saved, watchedSeconds: frontier, positionSeconds }, material.id);
    }

    function accept(next: WatchReply, restoringProgress = false) {
      saved = next;
      if (!active) return;
      const previous = restoringProgress ? 0 : frontier;
      frontier = next.completed ? next.durationSeconds : Math.max(previous, next.watchedSeconds);
      setSnapshot(next);
      reportLearning(next.positionSeconds);
    }

    function move(at: number) {
      const target = Math.max(0, Math.min(at, Number.isFinite(video.duration) ? video.duration : at));
      trustedPosition = target;
      lastSample = performance.now();
      if (video.readyState >= 1 && Math.abs(video.currentTime - target) > 0.025) {
        expectedSeek = target;
        video.currentTime = target;
      }
      if (active) setPosition(target);
    }

    function warn(failure: unknown) {
      if (!active) return;
      session = null;
      waitingForGesture = false;
      video.pause();
      if (saved) accept(saved, true);
      setError(failure instanceof Error ? failure.message : "视频连接中断，请从上次保存的位置继续。");
    }

    async function restore() {
      if (restoring) return;
      restoring = true;
      setBusy(true);
      try {
        await queue;
        if (!active) return;
        const next = await request();
        if (!active) return;
        accept(next, true);
        move(next.positionSeconds);
        setError(video.error ? "视频无法加载，请重试或联系课程管理员。" : "");
      } catch (failure) { warn(failure); }
      finally { restoring = false; if (active) setBusy(false); }
    }

    function save(action: "progress" | "pause" | "complete", keepalive = false) {
      const token = session;
      if (!token || !saved) return;
      const at = action === "complete" ? saved.durationSeconds : Math.min(trustedPosition, saved.durationSeconds);
      if (action !== "progress") { session = null; waitingForGesture = false; }
      writePending = true;
      queue = queue.then(async () => {
        try { accept(await request({ action, position: at, sessionId: token }, keepalive)); }
        catch (failure) { warn(failure); }
        finally { writePending = false; }
      });
    }

    // Only the media clock advances the visible timeline. A stalled, hidden or paused video earns no extra time.
    function sample(force = false) {
      if (video.seeking || video.readyState < 1) return;
      const at = video.currentTime;
      const now = performance.now();
      const delta = at - trustedPosition;
      if (delta < -0.1 || delta > (now - lastSample) / 1000 + 0.45) {
        move(trustedPosition);
        return;
      }
      trustedPosition = at;
      lastSample = now;
      if (session && saved && !saved.completed && !waitingForGesture && video.playbackRate === 1) {
        frontier = Math.max(frontier, Math.min(at, saved.durationSeconds));
        if (Math.floor(frontier) > Math.floor(reportedFrontier) || (force && frontier !== reportedFrontier)) reportLearning(at);
      }
      if (active && (force || now - lastPaint >= 80)) {
        lastPaint = now;
        setPosition(at);
      }
    }

    function draw() {
      sample();
      if (active && !video.paused && !video.ended) frame = window.requestAnimationFrame(draw);
    }

    function seeking() {
      const target = expectedSeek ?? trustedPosition;
      if (Math.abs(video.currentTime - target) > 0.1) move(target);
    }

    function seeked() {
      seeking();
      if (!video.seeking) {
        expectedSeek = null;
        sample(true);
      }
    }

    function readDuration() {
      if (active) setMediaDuration(Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0);
    }

    function loaded() {
      readDuration();
      if (saved) move(saved.positionSeconds);
    }

    async function start() {
      if (starting || restoring || !video.paused || !saved || video.readyState < 1 || document.hidden) return;
      starting = true;
      setBusy(true);
      setError("");
      try {
        if (waitingForGesture && session) {
          // Call play in the click handler itself on browsers that require user activation.
          await video.play();
          return;
        }
        await queue;
        if (!active || document.hidden) return;
        const atEnd = video.ended || (saved.completed && video.currentTime >= video.duration - 0.15);
        const at = atEnd ? 0 : Math.min(trustedPosition, saved.watchedSeconds);
        const next = await request({ action: "start", position: at, duration: video.duration });
        session = next.sessionId ?? null;
        if (!active || document.hidden) {
          if (session) await request({ action: "pause", position: at, sessionId: session }, true);
          session = null;
          return;
        }
        accept(next);
        move(next.positionSeconds);
        video.defaultPlaybackRate = video.playbackRate = 1;
        window.dispatchEvent(new CustomEvent("journey-learning-video-play", { detail: url }));
        await video.play();
      } catch (failure) {
        if (failure instanceof DOMException && failure.name === "NotAllowedError" && session) {
          waitingForGesture = true;
          return;
        }
        save("pause");
        if (!(failure instanceof DOMException && failure.name === "AbortError")) warn(failure);
      } finally { starting = false; if (active) setBusy(false); }
    }

    function paused() {
      window.cancelAnimationFrame(frame);
      sample(true);
      if (active) setPlaying(false);
      if (!video.ended) save("pause", document.hidden);
    }

    function started() {
      if (!session || document.hidden) { video.pause(); return; }
      waitingForGesture = false;
      lastSample = performance.now();
      setPlaying(true);
      setBusy(false);
      window.cancelAnimationFrame(frame);
      draw();
    }

    function ended() {
      window.cancelAnimationFrame(frame);
      if (active) { setPlaying(false); setPosition(video.duration); }
      save("complete", true);
    }

    function retry() {
      if (video.error) video.load();
      void restore();
    }

    function leave() { sample(true); save("pause", true); }
    function hidden() { if (document.hidden) { leave(); video.pause(); } }
    function other(event: Event) { if ((event as CustomEvent).detail !== url) video.pause(); }
    function offline() {
      session = null;
      waitingForGesture = false;
      video.pause();
      if (saved) { accept(saved, true); move(saved.positionSeconds); }
      if (active) setError("网络已断开，恢复连接后可从上次保存的位置继续。");
    }
    function preventRateChange() { if (video.playbackRate !== 1) video.playbackRate = 1; }

    const events: Record<string, EventListener> = {
      play: started, pause: paused, ended, seeking, seeked,
      timeupdate: () => sample(), loadedmetadata: loaded, durationchange: readDuration, ratechange: preventRateChange,
      error: () => warn(new Error("视频无法加载，请检查网络或联系课程管理员。")),
    };
    Object.entries(events).forEach(([name, listener]) => video.addEventListener(name, listener));
    window.addEventListener("offline", offline);
    window.addEventListener("online", retry);
    window.addEventListener("pagehide", leave);
    window.addEventListener("journey-learning-video-play", other);
    document.addEventListener("visibilitychange", hidden);
    const heartbeat = window.setInterval(() => {
      if (session && (!video.paused || waitingForGesture) && !writePending) { sample(); save("progress"); }
    }, 4000);

    controls.current = {
      start: () => void start(),
      toggle: () => { if (video.paused) void start(); else video.pause(); },
      rewind: () => {
        if (restoring || starting) return;
        sample(true);
        // Persist the high-water mark before the next heartbeat reports a replay position.
        if (session && saved && frontier > saved.watchedSeconds) save("progress");
        move(Math.max(0, trustedPosition - 10));
      },
      retry,
    };
    consumedRequest.current = 0;
    setPlaying(false); setSnapshot(null); setPosition(0); setWatchedSeconds(null); setError("");
    readDuration();
    void restore();
    return () => {
      active = false;
      controls.current = null;
      window.clearInterval(heartbeat);
      window.cancelAnimationFrame(frame);
      Object.entries(events).forEach(([name, listener]) => video.removeEventListener(name, listener));
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", retry);
      window.removeEventListener("pagehide", leave);
      window.removeEventListener("journey-learning-video-play", other);
      document.removeEventListener("visibilitychange", hidden);
      leave();
      video.pause();
    };
  }, [villageCourse, courseId, revision, material.id, material.url]);

  const ready = mediaDuration > 0 && !!snapshot && !error;
  useEffect(() => {
    if (ready && !busy && playRequest > 0 && consumedRequest.current !== playRequest) {
      consumedRequest.current = playRequest;
      controls.current?.start();
    }
  }, [ready, busy, playRequest]);

  return <AcademyVideoPlayer title={material.title} videoRef={videoRef} playing={playing} ready={ready}
    position={position} watchedSeconds={watchedSeconds} duration={mediaDuration || snapshot?.durationSeconds || material.durationSeconds || 0}
    learningDuration={snapshot?.durationSeconds ?? material.durationSeconds} overallPercent={overallPercent}
    busy={busy} completed={!!snapshot?.completed} error={error}
    onTogglePlayback={() => controls.current?.toggle()} onReplayPrevious={() => controls.current?.rewind()}
    onRetry={() => controls.current?.retry()}>
    <video ref={videoRef} src={material.url} playsInline preload="metadata" aria-label={material.title} tabIndex={-1}
      controls={false} disablePictureInPicture disableRemotePlayback controlsList="nodownload noplaybackrate noremoteplayback"
      onContextMenu={event => event.preventDefault()} />
  </AcademyVideoPlayer>;
}
