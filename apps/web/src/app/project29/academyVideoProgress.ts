export type AcademyWatchSnapshot = {
  watchedSeconds: number;
  durationSeconds: number;
  completed: boolean;
};

export function academyVideoProgressPercent(watch: AcademyWatchSnapshot) {
  if (watch.completed) return 100;
  if (!(watch.durationSeconds > 0) || !Number.isFinite(watch.watchedSeconds)) return 0;
  return Math.floor(100 * Math.max(0, Math.min(0.999, watch.watchedSeconds / watch.durationSeconds)) + 1e-9);
}

export function videoTime(value: number) {
  const seconds = Math.max(0, Math.floor(Number.isFinite(value) ? value : 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  return `${hours ? `${hours}:` : ""}${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
