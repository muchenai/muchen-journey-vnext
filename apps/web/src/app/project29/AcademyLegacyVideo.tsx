"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import type { AcademyWatchSnapshot } from "./academyVideoProgress";
import { academyCoverSource } from "./AcademyCourseCover";
import { AcademyVideoPlayer } from "./AcademyVideoPlayer";
import type { AcademyItem } from "./useAcademy";

type Props = {
  course: AcademyItem;
  startRef: RefObject<(() => void) | null>;
  overallPercent?: number;
  onProgress: (id: string, seconds: number, duration: number, completed?: boolean, revision?: number) => Promise<AcademyItem>;
  onLearningProgress?: (snapshot: AcademyWatchSnapshot) => void;
};

export function AcademyLegacyVideo({ course, startRef, onProgress, onLearningProgress, overallPercent }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const bookmark = useRef(course.seconds);
  const frontier = useRef(course.seconds);
  const learningCallback = useRef(onLearningProgress);
  const controls = useRef<{ toggle: () => void; replayPrevious: () => void; retry: () => void } | null>(null);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [watchedToEnd, setWatchedToEnd] = useState(false);
  const [watchedSeconds, setWatchedSeconds] = useState<number | null>(null);
  const [mediaError, setMediaError] = useState("");
  const [saveError, setSaveError] = useState("");
  useEffect(() => { learningCallback.current = onLearningProgress; }, [onLearningProgress]);

  useEffect(() => {
    const media = video.current;
    if (!media) return;
    const player = media;
    let active = true;
    let lastSaveAt = 0;
    let lastQueuedSeconds = -1;
    let queuedComplete = false;
    let queue = Promise.resolve();
    let playhead = 0;
    let permittedSeek: number | null = null;
    let hasPlayed = false;
    let learnedToEnd = false;
    let reportedFrontier = -1;

    function reportLearning(force = false) {
      if (!active || !Number.isFinite(player.duration) || player.duration <= 0) return;
      if (!force && Math.floor(frontier.current) === Math.floor(reportedFrontier)) return;
      reportedFrontier = frontier.current;
      const watched = Math.min(frontier.current, player.duration);
      setWatchedSeconds(watched);
      learningCallback.current?.({ watchedSeconds: watched, durationSeconds: player.duration, completed: learnedToEnd });
    }

    function moveTo(seconds: number) {
      playhead = seconds;
      if (Math.abs(player.currentTime - seconds) > .01) {
        permittedSeek = seconds;
        player.currentTime = seconds;
      }
      setPosition(seconds);
    }

    function readMetadata() {
      if (!Number.isFinite(player.duration) || player.duration <= 0) return;
      setDuration(player.duration);
      setMediaError("");
      const atEnd = bookmark.current >= player.duration - .05;
      learnedToEnd = frontier.current >= player.duration;
      setWatchedToEnd(learnedToEnd);
      moveTo(atEnd ? 0 : Math.max(0, bookmark.current));
      reportLearning(true);
    }

    function checkSeek() {
      if (permittedSeek !== null && Math.abs(player.currentTime - permittedSeek) < .25) return;
      moveTo(playhead);
    }

    function finishSeek() {
      checkSeek();
      if (!player.seeking) permittedSeek = null;
    }

    function save(force: boolean) {
      if (!hasPlayed || !Number.isFinite(player.duration) || player.duration <= 0) return;
      const finished = player.ended && !player.seeking;
      const seconds = finished ? player.duration : player.seeking ? playhead : player.currentTime;
      const length = player.duration;
      const now = Date.now();
      if (seconds === lastQueuedSeconds && (!finished || queuedComplete)) return;
      if (!force && now - lastSaveAt < 10000) return;
      lastSaveAt = now;
      lastQueuedSeconds = seconds;
      queuedComplete = finished;
      queue = queue.then(async () => {
        try {
          await onProgress(course.id, seconds, length, finished || undefined, course.revision);
          if (active) setSaveError("");
        } catch (failure) {
          if (lastQueuedSeconds === seconds) lastQueuedSeconds = -1;
          if (active) setSaveError(failure instanceof Error ? failure.message : "请检查网络连接。");
        }
      });
    }

    function tick() {
      if (player.seeking || permittedSeek !== null || player.readyState < 1) return;
      playhead = player.currentTime;
      bookmark.current = playhead;
      setPosition(playhead);
      if (hasPlayed) {
        frontier.current = Math.max(frontier.current, playhead);
        reportLearning();
      }
      save(false);
    }
    function play() {
      if (player.ended) moveTo(0);
      void player.play().catch(failure => {
        if (active && failure?.name !== "AbortError") setMediaError("视频无法播放，请重新加载。");
      });
    }
    function started() {
      if (document.hidden) { player.pause(); return; }
      hasPlayed = true;
      setPlaying(true);
    }
    function paused() {
      setPlaying(false);
      if (!player.seeking && hasPlayed) frontier.current = Math.max(frontier.current, player.currentTime);
      reportLearning(true);
      save(true);
    }
    function ended() {
      learnedToEnd = true;
      frontier.current = player.duration;
      playhead = player.duration;
      setPlaying(false);
      setWatchedToEnd(true);
      reportLearning(true);
      save(true);
    }
    function rateChanged() { if (player.playbackRate !== 1) player.playbackRate = 1; }
    function failed() { setPlaying(false); setMediaError("视频暂时无法播放，请检查网络连接。"); }
    function hide() { if (document.hidden) { player.pause(); save(true); } }
    const flush = () => save(true);
    const handlers: Record<string, EventListener> = {
      loadedmetadata: readMetadata, seeking: checkSeek, seeked: finishSeek, timeupdate: tick,
      play: started, pause: paused, ended, ratechange: rateChanged, error: failed,
    };
    Object.entries(handlers).forEach(([name, handler]) => player.addEventListener(name, handler));
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", hide);
    startRef.current = play;
    controls.current = {
      toggle: () => player.paused ? play() : player.pause(),
      replayPrevious: () => {
        save(true);
        moveTo(Math.max(0, playhead - 10));
      },
      retry: () => { player.load(); },
    };
    if (player.readyState >= 1) readMetadata();
    return () => {
      active = false;
      startRef.current = null;
      controls.current = null;
      Object.entries(handlers).forEach(([name, handler]) => player.removeEventListener(name, handler));
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", hide);
      save(true);
      player.pause();
    };
  }, [course.id, course.revision, onProgress, startRef]);

  return <>
    <AcademyVideoPlayer title={course.title} videoRef={video} position={position} watchedSeconds={watchedSeconds} duration={duration}
      overallPercent={overallPercent}
      playing={playing} ready={duration > 0 && !mediaError} completed={watchedToEnd} error={mediaError}
      onTogglePlayback={() => controls.current?.toggle()} onReplayPrevious={() => controls.current?.replayPrevious()}
      onRetry={() => controls.current?.retry()}>
      <video ref={video} src={`/api/learner/academy/courses/${encodeURIComponent(course.id)}/video?revision=${course.revision}`}
        aria-label={course.title + " 课程视频"} poster={academyCoverSource(course)} preload="metadata" playsInline
        disablePictureInPicture disableRemotePlayback controls={false} controlsList="nodownload noplaybackrate noremoteplayback"
        onContextMenu={event => event.preventDefault()} />
    </AcademyVideoPlayer>
    {saveError && <p className="academy-error" role="alert">进度未保存：{saveError}</p>}
  </>;
}
