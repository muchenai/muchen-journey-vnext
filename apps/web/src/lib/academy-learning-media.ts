
export const academyMaterialNames = {
  link: "链接", document: "文档", image: "图片", video: "视频",
} as const;

export type AcademyMedia = {
  id: string;
  kind: "video" | "image" | "document" | "link";
  title: string;
  taskTitle?: string;
  taskXp?: number;
  name?: string;
  url: string;
  assetId?: string;
  size?: number;
  mime?: string;
  durationSeconds?: number;
};

export type AcademyWatchSnapshot = {
  watchedSeconds: number;
  positionSeconds: number;
  durationSeconds: number;
  completed: boolean;
  updatedAt: string | null;
};

type VideoCoverage = Pick<AcademyWatchSnapshot, "watchedSeconds" | "durationSeconds" | "completed">;

function watchedFraction(watch: VideoCoverage | undefined) {
  if (!watch) return 0;
  if (watch.completed) return 1;
  if (!(watch.durationSeconds > 0) || !Number.isFinite(watch.watchedSeconds)) return 0;
  // Only a confirmed completion gives a video its final fraction.
  return Math.max(0, Math.min(0.999, watch.watchedSeconds / watch.durationSeconds));
}

export function academyVideoProgressPercent(watch: VideoCoverage) {
  return Math.floor(100 * watchedFraction(watch) + 1e-9);
}

export function academyMaterialProgressPercent(
  materials: readonly AcademyMedia[],
  openedMaterialIds: readonly string[],
  videoProgressById: Readonly<Record<string, VideoCoverage>>,
) {
  if (!materials.length) return 0;
  const opened = new Set(openedMaterialIds);
  const learnedUnits = materials.reduce((total, material) => {
    if (material.kind !== "video") return total + Number(opened.has(material.id));
    return total + watchedFraction(videoProgressById[material.id]);
  }, 0);
  return Math.floor(100 * learnedUnits / materials.length + 1e-9);
}

export function academyMediaSource(value?: string) {
  if (!value || /[\\\u0000-\u001f]/.test(value)) return undefined;
  if (value.startsWith("/")) return /^\/api\/learner\/course-assets\/[a-f\d-]{36}$/i.test(value) ? value : undefined;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch {
    return undefined;
  }
}
