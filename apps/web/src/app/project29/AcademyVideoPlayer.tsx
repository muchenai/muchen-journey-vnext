"use client";

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { academyVideoProgressPercent, videoTime } from "./academyVideoProgress";
import "./academyVideoPlayer.css";

type Props = {
  title: string;
  children: ReactNode;
  videoRef: RefObject<HTMLVideoElement | null>;
  position: number;
  watchedSeconds: number | null;
  duration: number;
  learningDuration?: number;
  overallPercent?: number;
  playing: boolean;
  ready: boolean;
  completed: boolean;
  busy?: boolean;
  error?: string;
  onTogglePlayback: () => void;
  onReplayPrevious?: () => void;
  onRetry?: () => void;
};

type IconName = "play" | "pause" | "rewind" | "sound" | "mute" | "expand" | "collapse";
const icons: Record<IconName, ReactNode> = {
  play: <path d="m8 4 12 8-12 8z" fill="currentColor" stroke="none" />,
  pause: <path d="M6 5h4v14H6zm8 0h4v14h-4z" fill="currentColor" stroke="none" />,
  rewind: <><path d="M4 4v5h5M4.5 9A8 8 0 1 1 5 17" /><path d="M12 8v5l3 2" /></>,
  sound: <><path d="M3 9h4l5-4v14l-5-4H3z" /><path d="M16 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" /></>,
  mute: <><path d="M3 9h4l5-4v14l-5-4H3z" /><path d="m16 9 5 6m0-6-5 6" /></>,
  expand: <path d="M4 9V4h5m6 0h5v5m0 6v5h-5m-6 0H4v-5" />,
  collapse: <path d="M9 4v5H4m16 0h-5V4m0 16v-5h5m-16 0h5v5" />,
};

function PlayerIcon({ name }: { name: IconName }) {
  return <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icons[name]}</svg>;
}

export function AcademyVideoPlayer({ title, children, videoRef, position, watchedSeconds, duration, learningDuration = duration, overallPercent, playing, ready, completed,
  busy = false, error = "", onTogglePlayback, onReplayPrevious, onRetry }: Props) {
  const surface = useRef<HTMLDivElement>(null);
  const [muted, setMuted] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenAvailable, setFullscreenAvailable] = useState(false);
  const [fullscreenError, setFullscreenError] = useState("");
  const total = Number.isFinite(duration) && duration > 0 ? duration : 0;
  const elapsed = Math.min(total, Math.max(0, Number.isFinite(position) ? position : 0));
  const learningTotal = Number.isFinite(learningDuration) && learningDuration > 0 ? learningDuration : 0;
  const learned = completed ? learningTotal : Math.min(learningTotal, Math.max(0, watchedSeconds ?? 0));
  const percentage = learningTotal > 0 && watchedSeconds !== null
    ? academyVideoProgressPercent({ watchedSeconds: learned, durationSeconds: learningTotal, completed }) : null;
  const atEnd = total > 0 && elapsed >= total - 0.05 && completed;
  const playLabel = playing ? "暂停" : atEnd ? "重新播放" : elapsed > 0.1 ? "继续播放" : "播放";
  const disabled = !playing && (!ready || !!error || busy);
  const status = error ? "" : busy ? "正在连接…" : buffering && playing ? "正在缓冲…" : !ready ? "正在载入视频…" : "";

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const volumeChanged = () => setMuted(video.muted || video.volume === 0);
    const waiting = () => setBuffering(!video.paused);
    const clearBuffering = () => setBuffering(false);
    const fullscreenChanged = () => setFullscreen(document.fullscreenElement === surface.current);
    setFullscreenAvailable(Boolean(document.fullscreenEnabled && surface.current?.requestFullscreen));
    volumeChanged();
    video.addEventListener("volumechange", volumeChanged);
    video.addEventListener("waiting", waiting);
    video.addEventListener("playing", clearBuffering);
    video.addEventListener("pause", clearBuffering);
    document.addEventListener("fullscreenchange", fullscreenChanged);
    return () => {
      video.removeEventListener("volumechange", volumeChanged);
      video.removeEventListener("waiting", waiting);
      video.removeEventListener("playing", clearBuffering);
      video.removeEventListener("pause", clearBuffering);
      document.removeEventListener("fullscreenchange", fullscreenChanged);
    };
  }, [videoRef]);

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement === surface.current) await document.exitFullscreen();
      else await surface.current?.requestFullscreen();
      setFullscreenError("");
    } catch {
      setFullscreenError("暂时无法进入全屏，可以继续在这里观看。");
    }
  }

  return <div ref={surface} className="tracked-learning-video academy-tracked-video" data-completed={completed}
    role="group" aria-label={title + " 视频播放器"} onKeyDown={event => {
      if (!event.altKey && !event.ctrlKey && !event.metaKey &&
          ["arrowleft", "arrowright", "home", "end", "j", "l"].includes(event.key.toLowerCase())) {
        event.preventDefault();
      }
    }}>
    <div className="academy-video-learning" aria-label="学习进度">
      {overallPercent !== undefined && <div className="academy-video-metric" data-scope="course">
        <span>课程整体学习进度</span><strong>{overallPercent}%</strong>
      </div>}
      <div className="academy-video-metric" data-scope="video">
        <span>视频学习进度</span><strong>{percentage === null ? "—" : percentage + "%"}</strong>
        <small>已看 {percentage === null ? "--:--" : videoTime(learned)} / {learningTotal ? videoTime(learningTotal) : "--:--"}</small>
      </div>
    </div>
    <div className="tracked-video-stage">
      {children}
      <button type="button" className="academy-video-surface-action" data-playing={playing}
        aria-label={playLabel + "：" + title} disabled={disabled} onClick={onTogglePlayback}>
        <span className="academy-video-overlay-icon"><PlayerIcon name={playing ? "pause" : "play"} /></span>
      </button>
      {status && <span className="academy-video-loading" role="status">{status}</span>}
    </div>
    <div className="academy-video-transport">
      <progress className="academy-playback-progress" aria-label="视频播放进度"
        aria-valuetext={videoTime(elapsed) + " / " + (total ? videoTime(total) : "时长待载入")}
        max={total || 1} value={elapsed} title="随播放更新，不可拖动" />
      <div className="academy-video-controls">
        <button type="button" className="academy-video-button academy-playback-toggle" disabled={disabled}
          aria-label={playing ? "暂停视频" : "播放视频"} onClick={onTogglePlayback}>
          <PlayerIcon name={playing ? "pause" : "play"} /><span>{playLabel}</span>
        </button>
        <span className="academy-video-time"><span className="academy-video-time-label">当前播放</span> <strong>{videoTime(elapsed)}</strong><span> / </span>{total ? videoTime(total) : "--:--"}</span>
        <div className="academy-video-tools">
          {onReplayPrevious && <button type="button" className="academy-video-button" onClick={onReplayPrevious}
            disabled={!ready || !!error || busy || elapsed <= 0} title="回看 10 秒" aria-label="回看 10 秒">
            <PlayerIcon name="rewind" /><span>回看 10 秒</span>
          </button>}
          <button type="button" className="academy-video-button" title={muted ? "取消静音" : "静音"}
            aria-label={muted ? "取消静音" : "静音"} onClick={() => {
              const video = videoRef.current;
              if (!video) return;
              if (muted && video.volume === 0) video.volume = 1;
              video.muted = !muted;
            }}><PlayerIcon name={muted ? "mute" : "sound"} /></button>
          {fullscreenAvailable && <button type="button" className="academy-video-button" onClick={toggleFullscreen}
            title={fullscreen ? "退出全屏" : "全屏"} aria-label={fullscreen ? "退出全屏" : "全屏"}>
            <PlayerIcon name={fullscreen ? "collapse" : "expand"} />
          </button>}
        </div>
      </div>
      {completed && <p className="academy-video-complete">✓ 已完整观看</p>}
    </div>
    {error && <div className="tracked-video-error" role="alert"><span>{error}</span>
      {onRetry && <button type="button" onClick={onRetry}>重试</button>}
    </div>}
    {fullscreenError && <p className="tracked-video-note" role="status">{fullscreenError}</p>}
  </div>;
}
