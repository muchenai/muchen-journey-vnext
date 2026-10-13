"use client";

import { useEffect, useState, type CSSProperties } from "react";

import { JOURNEY_ENTRY_RESOURCES, prepareJourneyCache, preloadJourneyEntryResources } from "@/lib/journey-entry-preload";

export function ProjectResourceLoader({ onReady }: { onReady: () => void }) {
  const [loaded, setLoaded] = useState(0);
  const [total, setTotal] = useState<number>(JOURNEY_ENTRY_RESOURCES.length);
  const [loadedBytes, setLoadedBytes] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  const percent = Math.round((loaded / total) * 100);

  useEffect(() => {
    const controller = new AbortController();
    let completionTimer: number | undefined;
    void prepareJourneyCache().then(() => preloadJourneyEntryResources(progress => {
      setLoaded(progress.loaded);
      setTotal(progress.total);
      setLoadedBytes(progress.loadedBytes);
    }, controller.signal)).then(() => {
      completionTimer = window.setTimeout(onReady, 420);
    }).catch(error => {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setFailed(true);
    });
    return () => {
      controller.abort();
      if (completionTimer !== undefined) window.clearTimeout(completionTimer);
    };
  }, [attempt, onReady]);

  const ringStyle = { "--journey-load-progress": `${percent * 3.6}deg` } as CSSProperties;
  return (
    <main className="journey-resource-loader">
      <div className="journey-loader-stars" aria-hidden="true" />
      <section className="journey-loader-content" aria-label="项目资源载入">
        <p className="journey-loader-brand">MUCHEN JOURNEY</p>
        <div
          className={`journey-loader-ring ${failed ? "has-failed" : ""}`}
          style={ringStyle}
          role="progressbar"
          aria-label="项目资源载入进度"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <div className="journey-loader-orbit" aria-hidden="true" />
          <strong>{percent}<small>%</small></strong>
          <span>{failed ? "缓存未完成" : percent === 100 ? "资源准备完成" : "资源缓存中"}</span>
        </div>
        <h1>{failed ? "部分资源未能载入" : percent === 100 ? "探索旅程准备完成" : "正在准备你的探索旅程"}</h1>
        <p className="journey-loader-count">
          {failed ? "请检查网络后重新载入" : `已缓存 ${loaded}/${total} 项 · ${(loadedBytes / 1024 / 1024).toFixed(1)} MB`}
        </p>
        {failed && <button type="button" onClick={() => {
          setLoaded(0);
          setLoadedBytes(0);
          setFailed(false);
          setAttempt(value => value + 1);
        }}>重新载入</button>}
      </section>
    </main>
  );
}
