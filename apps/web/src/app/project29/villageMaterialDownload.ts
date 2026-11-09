const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;

function downloadName(disposition: string): string {
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  let name = disposition.match(/filename="([^"]*)"/i)?.[1] || "学习材料";
  if (encoded) {
    try { name = decodeURIComponent(encoded.trim()); } catch { /* Use a safe fallback. */ }
  }
  return name.replace(/[\\/\u0000-\u001f\u007f]/g, "_").replace(/^\.+/, "").trim().slice(0, 200) || "学习材料";
}

export async function requestVillageMaterial(taskId: string, index: number, signal: AbortSignal): Promise<{ blob: Blob; name: string }> {
  if (!uuid.test(taskId) || !Number.isInteger(index) || index < 0 || index > 99) throw new Error("学习材料参数无效，请重新打开任务。");
  let response: Response;
  try {
    // Keep authentication in the current browser/WebView. Never send a session
    // token in a URL or navigate another browser to this protected endpoint.
    response = await fetch(`/api/learner/village?task=${taskId}&material=${index}`, {
      credentials: "same-origin", cache: "no-store", redirect: "error", signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error("文件读取失败，请检查网络后重试。");
  }
  if (response.status === 401) throw new Error("登录已失效，请在当前页面重新登录后再下载。");
  if (response.status === 403) throw new Error("当前账号无权下载这份材料。");
  if (response.status === 404) throw new Error("没有找到这份学习材料，请重新打开任务。");
  if (!response.ok) throw new Error("文件读取失败，请稍后重试。");
  const disposition = response.headers.get("Content-Disposition") || "";
  if (!/^attachment(?:;|$)/i.test(disposition)) throw new Error("未收到有效文件，请重新打开任务后重试。");
  let blob: Blob;
  try { blob = await response.blob(); }
  catch (error) {
    if (signal.aborted) throw error;
    throw new Error("文件未完整读取，请重试。");
  }
  if (!blob.size) throw new Error("文件内容为空，请联系任务发布者。");
  return { blob, name: downloadName(disposition) };
}

export function startVillageMaterialDownload(url: string, name: string, parent: HTMLElement): void {
  if (!url.startsWith("blob:")) throw new Error("文件尚未准备好，请重试。");
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  // A modal dialog makes body siblings inert. Keep the temporary link inside
  // the current dialog; do not open a new window or navigate the task form.
  parent.appendChild(anchor);
  try { anchor.click(); } finally { anchor.remove(); }
}
