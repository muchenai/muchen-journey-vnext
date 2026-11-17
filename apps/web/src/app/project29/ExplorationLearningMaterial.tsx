"use client";

import { useRef, useState } from "react";
import type { VillageTask } from "./useVillageTasks";

type LearningMaterial = VillageTask["materials"][number];
const rasterMimes = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp", "image/x-ms-bmp"]);
const rasterFilename = /\.(?:png|jpe?g|gif|webp|avif|bmp)$/i;
const videoMimes = new Set(["video/mp4", "video/webm", "video/ogg"]);

function isInlineVideo(material: LearningMaterial) {
  if (!["file", "video"].includes(material.type)) return false;
  const mime = material.mime?.split(";")[0].trim().toLowerCase() || "";
  return videoMimes.has(mime) || ((!mime || mime === "application/octet-stream") && /\.(?:mp4|webm|ogv|ogg)$/i.test(material.name.trim()));
}

function isInlineImage(material: LearningMaterial) {
  if (!["file", "image"].includes(material.type)) return false;
  if (/\.(?:svgz?|html?|xhtml)$/i.test(material.name.trim())) return false;
  const mime = material.mime?.split(";")[0].trim().toLowerCase() || "";
  if (rasterMimes.has(mime)) return true;
  // Legacy attachments may only have a filename. A specific non-raster MIME
  // always wins over the name, so SVG/HTML cannot opt into this preview.
  return (!mime || mime === "application/octet-stream") && rasterFilename.test(material.name.trim());
}

function readingUrl(value: string) {
  if (!value) return null;
  try { const parsed = new URL(value, typeof location === "undefined" ? "http://localhost" : location.origin); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null; }
  catch { return null; }
}

export function ExplorationLearningMaterial({ taskId, index, material, group = "learning", opened = false, onOpened }: {
  taskId: string;
  index: number;
  material: LearningMaterial;
  group?: "learning" | "task";
  opened?: boolean;
  onOpened?: () => Promise<VillageTask | null>;
}) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordError, setRecordError] = useState(false);
  const opening = useRef(false);
  const file = ["file", "image", "video"].includes(material.type);
  const image = isInlineImage(material);
  const video = isInlineVideo(material);
  const name = material.name || `${group === "task" ? "任务文件" : "学习材料"} ${index + 1}`;
  const downloadUrl = `/api/learner/exploration?task=${encodeURIComponent(taskId)}&material=${index}${group === "task" ? "&group=task" : ""}`;
  const url = file ? null : readingUrl(material.url);
  async function markOpened() {
    if (!onOpened || opened || opening.current) return;
    opening.current = true; setRecording(true); setRecordError(false);
    try {
      if (!await onOpened()) { opening.current = false; setRecordError(true); }
    } catch { opening.current = false; setRecordError(true); }
    finally { setRecording(false); }
  }
  return <li className={image || video ? "ex-material-image-item" : undefined}>
    <span className="ex-material-icon" aria-hidden="true">{video ? "▷" : image ? "▧" : file ? "↓" : "↗"}</span>
    <div>
      {image ? <>
        <div className="ex-material-image-heading"><strong>{name}</strong>{!failed && <a href={downloadUrl} download onClick={() => void markOpened()}>下载原图 ↓</a>}</div>
        <figure className="ex-material-image" data-loaded={loaded}>
          {failed ? <div className="ex-material-image-fallback" role="status"><p>图片暂时无法展示，你可以下载原图后查看。</p><a href={downloadUrl} download onClick={() => void markOpened()}>下载原图 ↓</a></div> : <>
            {!loaded && <p className="ex-material-image-loading" role="status">正在加载图片…</p>}
            <img src={`${downloadUrl}&inline=1`} alt={name} loading="lazy" decoding="async" onLoad={() => { setLoaded(true); void markOpened(); }} onError={() => setFailed(true)} />
          </>}
        </figure>
      </> : video ? <>
        <div className="ex-material-image-heading"><strong>{name}</strong><a href={downloadUrl} download onClick={() => void markOpened()}>下载视频 ↓</a></div>
        {failed ? <div className="ex-material-image-fallback" role="status"><p>视频暂时无法播放，请下载后使用本地播放器观看。</p><a href={downloadUrl} download onClick={() => void markOpened()}>下载视频 ↓</a></div> : <video className="ex-material-video" src={`${downloadUrl}&inline=1`} controls playsInline preload="metadata" onPlay={() => void markOpened()} onError={() => setFailed(true)}>当前浏览器不支持播放这份视频，请下载后观看。</video>}
      </> : file ? <a href={downloadUrl} download onClick={() => void markOpened()}>{name}<span>下载文件 ↓</span></a> : url ? <a href={url} target="_blank" rel="noopener noreferrer" onClick={() => void markOpened()}>{name}<span>打开阅读 ↗</span></a> : <strong>{name}</strong>}
      {material.text && !file && <p>{material.text}</p>}
      {onOpened && !file && !url && material.text && <button type="button" className="ex-material-mark" disabled={opened || recording} onClick={() => void markOpened()}>{opened ? "已确认阅读" : recording ? "正在保存…" : "我已阅读这份材料"}</button>}
      {onOpened && <div className="ex-material-read-state" data-opened={opened} aria-live="polite">{recordError && !opened ? <><span>打开记录暂未保存。</span><button type="button" disabled={recording} onClick={() => void markOpened()}>重试记录</button></> : recording ? "正在保存打开记录…" : opened ? "✓ 已打开" : "尚未打开"}</div>}
    </div>
  </li>;
}
