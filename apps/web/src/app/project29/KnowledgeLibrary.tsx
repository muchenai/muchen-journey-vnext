import { useCallback, useEffect, useRef, useState } from "react";
import { ModuleIcon, ModulePanel, type ModuleDestination } from "./ModuleShell";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import "./knowledgeLibrary.css";

type Resource = {
  id: string; title: string; description: string; categoryId: string; kind: "file" | "link";
  fileName?: string; fileType?: string; mimeType?: string; size?: number; url?: string;
  publisher: string; updatedAt: string; saved: boolean;
};
type Library = { categories: { id: string; name: string }[]; items: Resource[] };
const formats = [["all", "全部格式"], ["link", "在线文档"], ["pdf", "PDF"], ["word", "Word"], ["ppt", "PPT"], ["sheet", "表格"], ["image", "图片"], ["other", "其他文件"]];
const kind = (r: Resource) => r.kind === "link" ? "link" : r.fileType || "other";
const formatLabel = (r: Resource) => r.kind === "link" ? "在线文档" : r.fileName?.split(".").pop()?.toUpperCase() || "文件";
const sizeLabel = (r: Resource) => r.kind === "link" ? "在线文档" : (r.size || 0) >= 1048576 ? `${((r.size || 0) / 1048576).toFixed(1)} MB` : `${Math.ceil((r.size || 0) / 1024)} KB`;
const date = (v: string) => Number.isNaN(new Date(v).getTime()) ? "—" : new Date(v).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" });
const safeUrl = (v?: string) => { try { const u = new URL(v || ""); return ["http:", "https:"].includes(u.protocol) && !u.username && !u.password ? u.href : ""; } catch { return ""; } };
async function read<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", credentials: "same-origin", ...init });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "资料读取失败，请重试。");
  return data as T;
}

export function KnowledgeLibrary({ module, query, onClearSearch }: {
  module: ModuleDestination; query: string; onClearSearch: () => void;
}) {
  const [library, setLibrary] = useState<Library>({ categories: [], items: [] });
  const [category, setCategory] = useState("all"), [format, setFormat] = useState("all");
  const [sort, setSort] = useState("newest"), [favoriteOnly, setFavoriteOnly] = useState(false);
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [saving, setSaving] = useState("");
  const [selected, setSelected] = useState<Resource | null>(null);
  const [fileUrl, setFileUrl] = useState(""), [fileError, setFileError] = useState("");
  const [fileProgress, setFileProgress] = useState(0);
  const modal = useRef<HTMLDialogElement>(null);
  const request = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    try {
      const data = await read<Library>(`/api/learner/knowledge?module=${module}`, { signal: controller.signal });
      if (!controller.signal.aborted) { setLibrary(data); setError(""); setLoading(false); }
    } catch (e) {
      if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : "资料读取失败。"); setLoading(false); }
    }
  }, [module]);
  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 0);
    const refresh = () => { if (!document.hidden) void load(); };
    window.addEventListener("focus", refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => { window.clearTimeout(initial); request.current?.abort(); window.removeEventListener("focus", refresh); window.clearInterval(timer); };
  }, [load]);
  useEffect(() => {
    const element = modal.current;
    if (selected) element?.showModal(); else element?.close();
    return () => element?.close();
  }, [selected]);
  useEffect(() => {
    if (!selected || selected.kind !== "file") return;
    const controller = new AbortController(); let objectUrl = "";
    const item = selected;
    void (async () => {
      try {
        const chunks: Uint8Array<ArrayBuffer>[] = [];
        const count = Math.ceil((item.size || 0) / (512 * 1024));
        for (let position = 0; position < count; position++) {
          const part = await read<{ data: string }>(`/api/learner/knowledge?module=${module}&id=${item.id}&position=${position}`, { signal: controller.signal });
          chunks.push(Uint8Array.from(atob(part.data), char => char.charCodeAt(0)));
          if (controller.signal.aborted) return;
          setFileProgress(Math.round((position + 1) / count * 100));
        }
        if (controller.signal.aborted) return;
        const blob = new Blob(chunks, { type: item.mimeType || "application/octet-stream" });
        if (blob.size !== item.size) throw new Error("文件未完整读取，请关闭后重新打开。");
        objectUrl = URL.createObjectURL(blob); setFileUrl(objectUrl); setFileProgress(100);
      } catch (e) { if (!controller.signal.aborted) setFileError(e instanceof Error ? e.message : "文件读取失败。"); }
    })();
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [selected, module]);
  function openResource(item: Resource) {
    setFileUrl(""); setFileError(""); setFileProgress(0); setSelected(item);
  }
  async function toggle(item: Resource) {
    if (saving) return;
    setSaving(item.id);
    try {
      const result = await read<{ id: string; saved: boolean }>("/api/learner/knowledge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ module, id: item.id, saved: !item.saved }) });
      setLibrary(old => ({ ...old, items: old.items.map(r => r.id === result.id ? { ...r, saved: result.saved } : r) }));
      setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "收藏失败，请重试。"); }
    finally { setSaving(""); }
  }
  const categoryName = (id: string) => library.categories.find(c => c.id === id)?.name || "未分类";
  const collection = favoriteOnly ? library.items.filter(r => r.saved) : library.items;
  const search = query.trim().toLocaleLowerCase();
  const visible = collection.filter(r => (category === "all" || r.categoryId === category) && (format === "all" || kind(r) === format)
    && `${r.title} ${r.description} ${r.publisher} ${r.fileName || ""} ${categoryName(r.categoryId)}`.toLocaleLowerCase().includes(search))
    .sort((a, b) => sort === "title" ? a.title.localeCompare(b.title, "zh-CN") : b.updatedAt.localeCompare(a.updatedAt));
  const reset = () => { setCategory("all"); setFormat("all"); onClearSearch(); };
  return <div className="knowledge-page">
    <div className="module-page-heading"><div><h1>知识库</h1><p>连接公司、行业与成长，让每一次探索都有据可循。</p></div><div className="knowledge-view-tabs"><button className={`module-secondary${!favoriteOnly ? " is-active" : ""}`} aria-pressed={!favoriteOnly} onClick={() => { setFavoriteOnly(false); setCategory("all"); }}>资料库</button><button className={`module-secondary favorite-entry${favoriteOnly ? " is-active" : ""}`} aria-pressed={favoriteOnly} onClick={() => { setFavoriteOnly(true); setCategory("all"); }}><ModuleIcon file="b5cc7" size={17} />我的收藏 <span className="favorite-entry-count">{library.items.filter(r => r.saved).length}</span></button></div></div>
    <ModulePanel className="knowledge-intro"><div className="knowledge-book"><ModuleIcon file="643cc" size={42} /></div><div><span className="badge-eyebrow">KNOWLEDGE CONNECTS US</span><h2>让知识流动，让成长发生。</h2><p>公司文档、行业洞察、成长课程与实用模板，在这里找到下一步的答案。</p></div><div className="knowledge-intro-formats"><span>DOC</span><span>PPT</span><span>PDF</span><small>多种资料，一站查阅</small></div></ModulePanel>
    <div className="knowledge-layout"><ModulePanel className="knowledge-categories"><h3>资料分类</h3>{[{ id: "all", name: "全部资料" }, ...library.categories].map(c => <button key={c.id} className={category === c.id ? "is-active" : ""} onClick={() => setCategory(c.id)} aria-pressed={category === c.id}><span>{c.name}</span><small>{collection.filter(r => c.id === "all" || r.categoryId === c.id).length}</small></button>)}<p>资料由管理员维护，这里展示已发布到当前模块的内容。</p></ModulePanel>
      <section aria-label="知识库资料列表"><div className="knowledge-list-tools"><div><h3>{favoriteOnly ? "我的收藏" : category === "all" ? "全部资料" : categoryName(category)}</h3><span>共 {visible.length} 份资料</span></div><div><select aria-label="按文件格式筛选" value={format} onChange={e => setFormat(e.target.value)}>{formats.map(([id, name]) => <option value={id} key={id}>{name}</option>)}</select><select aria-label="资料排序" value={sort} onChange={e => setSort(e.target.value)}><option value="newest">最近更新</option><option value="title">按名称排序</option></select><button className="module-secondary" onClick={() => void load()}>刷新</button></div></div>
        {error && <div className="knowledge-error" role="alert">{error}<button onClick={() => void load()}>重新加载</button></div>}
        <ModulePanel className="knowledge-resource-list"><div className="knowledge-table-heading"><span>资料名称</span><span>分类</span><span>文件格式</span><span>更新日期</span><span>操作</span></div>
          {loading ? <div className="knowledge-empty" role="status">正在读取知识库…</div> : error ? null : visible.map(item => <article className="knowledge-resource-row" key={item.id}><div className="knowledge-resource-name"><span className="knowledge-file-icon" data-format={formatLabel(item)}>{formatLabel(item)}</span><div><h3><button onClick={() => openResource(item)}>{item.title}</button></h3><p>{item.description}</p><small>{item.publisher} · {sizeLabel(item)}</small></div></div><span className="module-tag">{categoryName(item.categoryId)}</span><span className="knowledge-format">{formatLabel(item)}</span><time dateTime={item.updatedAt}>{date(item.updatedAt)}</time><div className="knowledge-row-actions"><button onClick={() => openResource(item)}>查看资料</button><button aria-pressed={item.saved} disabled={!!saving} onClick={() => void toggle(item)}>{item.saved ? "已收藏" : "收藏"}</button></div></article>)}
          {!loading && !error && !visible.length && <div className="knowledge-empty"><ModuleIcon file="095be" size={32} /><h3>{collection.length ? "没有找到匹配的资料" : favoriteOnly ? "还没有收藏资料" : "暂无已发布资料"}</h3><p>{collection.length ? "试试其他分类、格式或搜索词。" : favoriteOnly ? "在资料库点击“收藏”，即可在这里找到它。" : "管理员发布到当前模块后，资料会显示在这里。"}</p><button className="module-secondary" onClick={() => { reset(); setFavoriteOnly(false); }}>查看全部资料</button></div>}
        </ModulePanel>
      </section>
    </div>
    <dialog ref={modal} className="module-dialog knowledge-preview-dialog journey-dialog" aria-labelledby="knowledge-resource-title" onCancel={() => setSelected(null)}><JourneyDialogSurface><div className="module-dialog-heading"><span className="badge-eyebrow">RESOURCE PREVIEW</span><button onClick={() => setSelected(null)} aria-label="关闭资料">关闭</button></div>{selected && <><span className="knowledge-file-icon" data-format={formatLabel(selected)}>{formatLabel(selected)}</span><h2 id="knowledge-resource-title">{selected.title}</h2><span className="module-tag">{categoryName(selected.categoryId)}</span><p>{selected.description}</p><div className="knowledge-preview-meta"><span>发布方：{selected.publisher}</span><span>格式：{formatLabel(selected)} · {sizeLabel(selected)}</span><span>更新日期：{date(selected.updatedAt)}</span></div>{selected.kind === "link" ? <a className="module-primary knowledge-open-link" href={safeUrl(selected.url) || undefined} target="_blank" rel="noopener noreferrer">打开在线文档 ↗</a> : <div className="knowledge-file-preview">{fileError ? <p role="alert">{fileError}</p> : !fileUrl ? <p role="status">正在读取文件… {fileProgress}%</p> : <>{/^image\/(png|jpeg|gif|webp|avif|bmp)$/.test(selected.mimeType || "") && <img src={fileUrl} alt={selected.title} />}{selected.mimeType === "application/pdf" && <a className="module-secondary" href={fileUrl} target="_blank" rel="noopener noreferrer">打开 PDF 预览 ↗</a>}<a className="module-primary" href={fileUrl} download={selected.fileName || selected.title}>下载文件 ↓</a></>}</div>}</>}</JourneyDialogSurface></dialog>
  </div>;
}
