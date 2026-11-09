import { useEffect, useRef, useState } from "react";
import type { VillageTask } from "./useVillageTasks";
import { requestVillageMaterial, startVillageMaterialDownload } from "./villageMaterialDownload";

function MaterialDownload({ taskId, index, name }: { taskId: string; index: number; name: string }) {
  const host = useRef<HTMLDivElement>(null);
  const request = useRef<AbortController | null>(null);
  const prepared = useRef<{ url: string; name: string } | null>(null);
  const [file, setFile] = useState<{ url: string; name: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => () => {
    request.current?.abort();
    // Give a just-started download time to consume the Blob if the task closes.
    const url = prepared.current?.url;
    if (url) window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  }, []);

  async function download() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setFailed(false); setMessage("正在读取文件…");
    try {
      let ready = prepared.current;
      if (!ready) {
        const result = await requestVillageMaterial(taskId, index, controller.signal);
        if (controller.signal.aborted) return;
        ready = { url: URL.createObjectURL(result.blob), name: result.name };
        prepared.current = ready; setFile(ready);
      }
      if (host.current) {
        try {
          startVillageMaterialDownload(ready.url, ready.name, host.current);
          setMessage("已发起下载；如未开始，请点击“下载文件”。");
        } catch {
          setMessage("文件已准备好，请点击“下载文件”保存。");
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setFailed(true);
        setMessage(error instanceof Error ? error.message : "下载未能开始，请重试。");
      }
    } finally {
      if (!controller.signal.aborted) { request.current = null; setBusy(false); }
    }
  }

  return <div ref={host} className="village-material-download">
    <button type="button" className="module-cyan village-material-button" disabled={busy} onClick={() => void download()} aria-label={`下载学习材料：${name}`}>
      {name} <span aria-hidden="true">↓</span>
    </button>
    <div className={`village-material-feedback${failed ? " is-error" : ""}`} role={failed ? "alert" : "status"} aria-live={failed ? "assertive" : "polite"} aria-atomic="true">
      {message && <span>{message}</span>}
      {file && !busy && <a className="module-cyan" href={file.url} download={file.name}>下载文件 ↓</a>}
    </div>
  </div>;
}

export function VillageTaskMaterials({ task }: { task: VillageTask }) {
  return <ul className="village-task-materials">{task.materials.map((material, index) => <li key={`${task.id}:${task.versionId}:${index}`}>
    {material.type === "file" || material.type === "image"
      ? <MaterialDownload taskId={task.id} index={index} name={material.name} />
      : material.url ? <a className="module-cyan" href={material.url} target="_blank" rel="noopener noreferrer">{material.name} ↗</a> : <strong>{material.name}</strong>}
    {material.text && <p style={{ whiteSpace: "pre-wrap" }}>{material.text}</p>}
  </li>)}</ul>;
}
