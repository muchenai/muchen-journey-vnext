import { useEffect, useState, type ComponentType } from "react";
import { useCanvasScale } from "./useCanvasScale";
// Refresh with node scripts/check-resources.mjs --write after changing assets.
import imageUrls from "./preloadAssets.json";

let pendingLoad: Promise<void> | undefined;
let resourcesReady = false;
const readyImages = new Set<string>();
const total = imageUrls.length + 2;
let completed = 0;
let failure = false;
let stage = "正在准备探索营";
const listeners = new Set<() => void>();
const publish = () => listeners.forEach(listener => listener());

function withTimeout<T>(operation: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("资源加载超时")), 45000);
    operation.then(value => {
      window.clearTimeout(timer);
      resolve(value);
    }, error => {
      window.clearTimeout(timer);
      reject(error);
    });
  });
}

function prepare() {
  if (pendingLoad) return pendingLoad;
  failure = false;
  completed = 0;
  stage = "正在加载应用";
  publish();
  pendingLoad = (async () => {
    let active = true;
    try {

      completed = 1 + readyImages.size;
      stage = "正在加载图片与本地字体";
      publish();
      const remaining = imageUrls.filter(url => !readyImages.has(url));
      let next = 0;
      const loadImages = async () => {
        while (active && next < remaining.length) {
          const url = remaining[next++];
          await withTimeout(new Promise<void>((resolve, reject) => {
            const image = new Image();
            image.onload = () => {
              image.decode().then(() => resolve(), reject);
            };
            image.onerror = () => reject(new Error("图片加载失败"));
            image.src = url;
          }));
          if (!active) return;
          readyImages.add(url);
          completed++;
          publish();
        }
      };
      const loadFont = async () => {
        const faces = await withTimeout(document.fonts.load('400 16px "Source Han Sans SC"', "星际成长"));
        if (!faces.length) throw new Error("本地字体未就绪");
        if (!active) return;
        completed++;
        publish();
      };
      await Promise.all([
        loadFont(),
        ...Array.from({ length: Math.min(6, remaining.length) }, loadImages),
      ]);
      resourcesReady = true;
      completed = total;
      stage = "应用已就绪";
    } catch {

      failure = true;
      stage = "应用加载失败或超时，请检查网络后重试";
    } finally {
      active = false;
    }
    publish();
  })().finally(() => { pendingLoad = undefined; });
  return pendingLoad;
}

export function ProjectResourceLoader({onReady}: {onReady:()=>void}) {
  const scale = useCanvasScale();
  const [, refresh] = useState(0);
  useEffect(() => {
    const update = () => refresh(value => value + 1);
    listeners.add(update);
    void prepare();
    return () => { listeners.delete(update); };
  }, []);
  useEffect(()=>{ if(resourcesReady)onReady(); });
  const progress = Math.floor(completed / total * 100);
  return <div className="app-loader-viewport"><main className="app-loader" style={{ zoom: scale }} aria-busy={!failure}>
    <section className="app-loader-content" aria-labelledby="app-loader-title">
      <p className="app-loader-brand">MUCHEN JOURNEY</p>
      <div className="app-loader-ring" role="progressbar" aria-label="探索营资源载入进度"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
        <svg viewBox="0 0 200 200" aria-hidden="true">
          <defs>
            <linearGradient id="loader-ring-gradient" x1="0" y1="1" x2="1" y2="0" gradientUnits="objectBoundingBox">
              <stop offset="0%" stopColor="#7771ff" />
              <stop offset="55%" stopColor="#31c9f5" />
              <stop offset="100%" stopColor="#8af7ff" />
            </linearGradient>
          </defs>
          <circle className="app-loader-ring-track" cx="100" cy="100" r="86" />
          <circle className="app-loader-ring-fill" cx="100" cy="100" r="86" pathLength="100"
            strokeDasharray={`${progress} 100`} opacity={progress === 0 ? 0 : 1} />
        </svg>
        <div className="app-loader-ring-value"><strong>{progress}<span>%</span></strong><span>资源载入中</span></div>
      </div>
      <h1 id="app-loader-title">正在准备你的探索旅程</h1>
      <p className="app-loader-status" role="status">{stage} · {completed}/{total}</p>
      {failure && <button type="button" className="app-loader-retry" onClick={() => void prepare()}>重新加载</button>}
    </section>
  </main></div>;
}
