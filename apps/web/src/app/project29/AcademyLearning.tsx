"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ModuleHero, ModuleIcon, ModulePanel } from "./ModuleShell";
import { AcademyCourseCover, academyCoverSource } from "./AcademyCourseCover";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { academyRequest, useAcademy, type AcademyItem, type AcademyShare } from "./useAcademy";
import "./academyLearning.css";

const category = (course: AcademyItem) => ({ link: "管理员外链", video: "平台视频", share: "员工共建" })[course.type];
const date = (value: string) => new Date(value).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" });
const safeLink = (value: string) => { try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) && !u.username && !u.password ? u.href : ""; } catch { return ""; } };
const errorMessage = (e: unknown) => e instanceof Error ? e.message : "操作失败，请重试。";

export function AcademyLearning({ active, savedOnly, query, onSaved, onClearSearch }: {
  active: boolean; savedOnly: boolean; query: string; onSaved: (saved: boolean) => void; onClearSearch: () => void;
}) {
  const academy = useAcademy(active);
  const [kind, setKind] = useState("all"), [tag, setTag] = useState("all"), [sort, setSort] = useState("newest");
  const [view, setView] = useState<"courses" | "records" | "shares">("courses");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [share, setShare] = useState<AcademyShare | "new" | null>(null);
  const [busyFavorite, setBusyFavorite] = useState("");
  const [notice, setNotice] = useState("");
  const listing = useRef<HTMLDivElement>(null);
  useEffect(() => { const timer = window.setTimeout(() => { setKind("all"); setTag("all"); }, 0); return () => window.clearTimeout(timer); }, [savedOnly]);
  useEffect(() => { if (active) return; const timer = window.setTimeout(() => { setSelectedId(null); setShare(null); }, 0); return () => window.clearTimeout(timer); }, [active]);
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(""), 5000); return () => window.clearTimeout(timer); }, [notice]);
  const selected = academy.courses.find(course => course.id === selectedId);
  const favorites = academy.courses.filter(course => course.favorite);
  const completed = academy.courses.filter(course => course.completed);
  const started = academy.courses.filter(course => course.progress > 0 || course.seconds > 0 || course.completed);
  const search = query.trim().toLocaleLowerCase();
  const pool = savedOnly ? favorites : view === "records" ? started : academy.courses;
  const visible = pool.filter(course => (kind === "all" || course.type === kind) && (tag === "all" || course.tags.includes(tag))
    && `${course.title} ${course.summary} ${course.author.name} ${course.tags.join(" ")}`.toLocaleLowerCase().includes(search))
    .sort((a, b) => sort === "duration" ? a.minutes - b.minutes : sort === "title" ? a.title.localeCompare(b.title, "zh-CN") : b.updatedAt.localeCompare(a.updatedAt));
  async function toggle(course: AcademyItem) {
    if (busyFavorite) return;
    setBusyFavorite(course.id);
    try { await academy.favorite(course.id, !course.favorite); setNotice(course.favorite ? "已取消收藏" : "已收藏课程"); }
    catch (e) { setNotice(errorMessage(e)); }
    finally { setBusyFavorite(""); }
  }
  function showView(next: "courses" | "records" | "shares") { if (savedOnly) onSaved(false); setView(next); }
  return <section className="academy-learning">
    <div className="module-page-heading"><div><h1>{savedOnly ? "我的收藏" : "AI 学院"}</h1><p>在知识星海里，解锁你的下一种可能。</p></div><div className="module-actions">
      <button data-page-navigation className={`module-secondary favorite-entry${savedOnly ? " is-active" : ""}`} onClick={() => onSaved(!savedOnly)}><ModuleIcon file="b5cc7" size={18} />{savedOnly ? "返回学院" : "我的收藏"}<span className="favorite-entry-count">{favorites.length}</span></button>
      <button className="module-secondary" onClick={() => showView(view === "records" ? "courses" : "records")}><ModuleIcon file="42cb2" />学习记录</button>
      <button className="module-secondary accent" onClick={() => setShare("new")}><ModuleIcon file="d4a6c" />分享我的发现</button>
    </div></div>
    {!savedOnly && <div className="module-hero-grid"><ModuleHero module="academy" title="与 AI 共创，" subtitle="走向更大的自己。" description="从一个灵感到一次实践，让每一份好奇，都成为成长路上的能量。" onContinue={() => {
      const next = started.find(course => !course.completed) || academy.courses.find(course => !course.completed) || academy.courses[0];
      if (next) setSelectedId(next.id); else { setNotice(academy.loading ? "课程正在读取，请稍候。" : "暂无已发布课程，管理员发布后会显示在这里。"); listing.current?.scrollIntoView({ block: "nearest" }); }
    }} /><ModulePanel className="module-weekly"><div className="module-row"><h3>我的学习进度</h3><ModuleIcon file="d7bdc" size={30} /></div><p className="module-weekly-count"><strong>{completed.length}</strong><span>/ {academy.courses.length} 门课程</span></p><progress className="academy-progress" value={completed.length} max={Math.max(academy.courses.length, 1)} aria-label="课程完成进度" /><div className="module-row module-small"><span>已开始 {started.length} 门</span><span className="module-cyan">已收藏 {favorites.length} 门</span></div><blockquote>学习进度与收藏保存在你的账号中，回来后可以继续学习。</blockquote></ModulePanel></div>}
    <div ref={listing} className="module-listing">
      {!savedOnly && <div className="module-filter-tabs academy-view-tabs" role="group" aria-label="学院栏目">{[["courses", "全部课程"], ["records", "学习记录"], ["shares", "我的分享"]].map(([id, label]) => <button key={id} className={view === id ? "is-active" : ""} aria-pressed={view === id} onClick={() => setView(id as typeof view)}>{label}<span>{id === "courses" ? academy.courses.length : id === "records" ? started.length : academy.shares.length}</span></button>)}</div>}
      {academy.error && <div className="academy-error" role="alert">{academy.error}<button className="module-secondary" onClick={() => void academy.refresh()}>重新加载</button></div>}
      {academy.loading ? <ModulePanel className="academy-empty"><p role="status">正在读取学院内容…</p></ModulePanel> : view === "shares" && !savedOnly ? <ModulePanel className="academy-share-list"><div className="module-row"><h2>我的分享</h2><button className="module-secondary" onClick={() => void academy.refresh()}>刷新审核状态</button></div>{academy.shares.filter(item => `${item.title} ${item.summary}`.toLocaleLowerCase().includes(search)).map(item => <article key={item.id}><div className="module-row"><h3>{item.title}</h3><span className={`module-tag academy-share-${item.status}`}>{({ pending: "待审核", approved: "已通过", rejected: "已驳回" })[item.status]}</span></div><p>{item.summary}</p><div className="academy-course-tags">{item.tags.map(label => <span className="module-tag" key={label}>{label}</span>)}</div><div className="module-row"><small>提交于 {date(item.createdAt)}</small><a className="module-secondary" href={safeLink(item.url) || undefined} target="_blank" rel="noopener noreferrer">查看分享链接 ↗</a></div>{item.reason && <p className="academy-review-reason">审核意见：{item.reason}</p>}{item.status === "rejected" && <button className="module-secondary" onClick={() => setShare(item)}>修改并重新提交</button>}</article>)}{!academy.shares.length && <div className="academy-empty"><h3>还没有提交分享</h3><p>分享一份有用的方法或资源，审核通过后会出现在学院课程中。</p><button className="module-primary" onClick={() => setShare("new")}>分享我的发现 →</button></div>}</ModulePanel> : <>
        <ModulePanel className="academy-filter-panel"><div className="module-filterbar"><div className="module-tabs" role="group" aria-label="课程分类">{[["all", "全部课程"], ["link", "管理员外链"], ["video", "平台视频"], ["share", "员工共建"]].map(([id, label]) => <button key={id} className={kind === id ? "is-active" : ""} aria-pressed={kind === id} onClick={() => setKind(id)}>{label}<span>{pool.filter(course => id === "all" || course.type === id).length}</span></button>)}</div><label className="module-sort">排序<select aria-label="课程排序" value={sort} onChange={event => setSort(event.target.value)}><option value="newest">最近更新</option><option value="duration">用时最短</option><option value="title">按名称排序</option></select></label></div><div className="academy-tag-filter" role="group" aria-label="课程标签">{["all", ...academy.tags].map(label => <button key={label} className={tag === label ? "is-active" : ""} aria-pressed={tag === label} onClick={() => setTag(label)}>{label === "all" ? "全部标签" : label}</button>)}</div></ModulePanel>
        <div className="module-list-caption"><span>{visible.length} 门课程 · {savedOnly ? "我的收藏" : view === "records" ? "学习记录" : "已发布课程"}</span><button className="academy-refresh" onClick={() => void academy.refresh()}>刷新课程 ↻</button></div>
        <div className="module-cards-grid">{visible.map(course => {
          const index = academy.courses.indexOf(course) % 6;
          return <ModulePanel className="module-course-card" key={course.id}><div className="module-row"><span className="module-tag"><ModuleIcon file="0fa72" size={13} />{category(course)}</span><button className={`knowledge-save-toggle${course.favorite ? " is-saved" : ""}`} disabled={!!busyFavorite} aria-pressed={course.favorite} aria-label={`${course.favorite ? "取消收藏" : "收藏"} ${course.title}`} onClick={() => void toggle(course)}><ModuleIcon file={course.favorite ? "b5cc7" : "cdc4e"} size={16} />{course.favorite ? "已收藏" : "收藏"}</button></div><button className="module-course-cover" onClick={() => setSelectedId(course.id)} aria-label={`查看课程 ${course.title}`}><AcademyCourseCover course={course} index={index} /><span className="module-cover-time">{course.minutes} 分钟</span></button><button className="module-card-title" onClick={() => setSelectedId(course.id)}>{course.title}</button><p className="module-card-description">{course.summary}</p><div className="academy-course-tags">{course.tags.map(label => <span className="module-tag" key={label}>{label}</span>)}</div><div className="module-course-meta"><span>{course.author.name}</span><span>更新于 {date(course.updatedAt)}</span></div><div className="module-course-reward"><span>学习进度</span><strong>{course.completed ? "已完成" : course.progress > 0 ? `${Math.round(course.progress)}%` : "尚未开始"}</strong></div><button className="module-card-action" onClick={() => setSelectedId(course.id)}>{course.completed ? "再次学习" : course.progress > 0 ? "继续学习" : "开始学习"} →</button></ModulePanel>;
        })}</div>
        {!visible.length && !academy.error && <ModulePanel className="academy-empty"><ModuleIcon file="643cc" size={34} /><h3>{pool.length ? "没有找到匹配的课程" : savedOnly ? "还没有收藏课程" : view === "records" ? "还没有学习记录" : "暂无已发布课程"}</h3><p>{pool.length ? "试试其他标签、类型或搜索词。" : savedOnly ? "在课程卡片点击“收藏”，即可在这里找到它。" : view === "records" ? "选择一门课程开始学习，进度会保存在这里。" : "管理员发布课程后，内容会显示在这里。"}</p><button className="module-secondary" onClick={() => { setKind("all"); setTag("all"); onClearSearch(); showView("courses"); }}>查看全部课程</button></ModulePanel>}
      </>}
    </div>
    {active && selectedId && <CourseDialog course={selected} onClose={() => setSelectedId(null)} onProgress={academy.progress} onFavorite={course => academy.favorite(course.id, !course.favorite)} favoriteBusy={!!busyFavorite} />}
    {active && share && <ShareDialog item={share === "new" ? null : share} tags={academy.tags} onClose={() => setShare(null)} onSaved={() => { setShare(null); setView("shares"); onSaved(false); setNotice("分享已提交，等待管理员审核。"); void academy.refresh(); }} />}
    {notice && <div className="module-toast" role="status">{notice}<button aria-label="关闭提示" onClick={() => setNotice("")}> ×</button></div>}
  </section>;
}

export function AcademyFavoritesPreview({ onBrowse, onViewAll }: { onBrowse: () => void; onViewAll: () => void }) {
  const academy = useAcademy(true);
  const [selectedId, setSelectedId] = useState<string | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const saved = academy.courses.filter(course => course.favorite);
  async function toggle(course: AcademyItem) {
    if (busy) return;
    setBusy(true);
    try { await academy.favorite(course.id, !course.favorite); setError(""); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <><ModulePanel className="favorite-knowledge is-compact"><div className="favorite-knowledge-heading"><span className="favorite-knowledge-symbol"><ModuleIcon file="b5cc7" size={26} /></span><div><h2>我的收藏 <span>{saved.length}</span></h2><p>AI 学院的知识科普，收藏后随时回来查看。</p></div><button data-page-navigation className="module-secondary" onClick={onViewAll}>查看全部 →</button></div><div className="favorite-knowledge-list">{academy.loading ? <p role="status">正在读取收藏…</p> : academy.error ? <p role="alert">{academy.error}<button onClick={() => void academy.refresh()}>重新加载</button></p> : saved.length ? saved.slice(0, 3).map((course, index) => <article className="favorite-knowledge-row" key={course.id}><span className="favorite-knowledge-index">{String(index + 1).padStart(2, "0")}</span><div className="favorite-knowledge-copy"><button onClick={() => setSelectedId(course.id)}>{course.title}</button><p>AI 学院 · {category(course)} · {course.minutes} 分钟</p></div><button className="favorite-knowledge-read" onClick={() => setSelectedId(course.id)}>查看 →</button><button className="knowledge-save-toggle is-saved" disabled={busy} aria-label={`取消收藏 ${course.title}`} onClick={() => void toggle(course)}><ModuleIcon file="b5cc7" size={16} />已收藏</button></article>) : <div className="favorite-knowledge-empty"><h3>还没有收藏课程</h3><p>去 AI 学院发现感兴趣的课程，收藏后可随时回来学习。</p><button data-page-navigation className="module-secondary" onClick={onBrowse}>去 AI 学院看看 →</button></div>}{error && <p role="alert">{error}</p>}</div></ModulePanel>{selectedId && <CourseDialog course={academy.courses.find(item => item.id === selectedId)} onClose={() => setSelectedId(null)} onProgress={academy.progress} onFavorite={course => academy.favorite(course.id, !course.favorite)} favoriteBusy={busy} />}</>;
}

function CourseDialog({ course, onClose, onProgress, onFavorite, favoriteBusy }: {
  course: AcademyItem | undefined; onClose: () => void;
  onProgress: (id: string, seconds: number, duration: number, completed?: boolean, revision?: number) => Promise<AcademyItem>;
  onFavorite: (course: AcademyItem) => Promise<void>; favoriteBusy: boolean;
}) {
  const modal = useRef<HTMLDialogElement>(null), video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [mediaError, setMediaError] = useState(false), [favoriting, setFavoriting] = useState(false);
  const lastSave = useRef(0), queue = useRef<Promise<unknown>>(Promise.resolve());
  const alive = useRef(true), initialSeconds = useRef(course?.seconds || 0);
  useEffect(() => { const el = modal.current; alive.current = true; el?.showModal(); return () => { alive.current = false; el?.close(); }; }, []);
  useEffect(() => { initialSeconds.current = course?.seconds || 0; }, [course?.revision, course?.seconds]);
  function saveVideo(force = false) {
    const el = video.current;
    if (!course || !el || !Number.isFinite(el.duration) || el.duration <= 0) return;
    const now = Date.now();
    if (!force && now - lastSave.current < 10000) return;
    lastSave.current = now;
    const seconds = el.currentTime, duration = el.duration, id = course.id, revision = course.revision;
    queue.current = queue.current.catch(() => {}).then(() => onProgress(id, seconds, duration, undefined, revision)).then(() => { if (alive.current) setError(""); }).catch(e => { if (alive.current) setError(`进度未保存：${errorMessage(e)}`); });
  }
  function close() { if (video.current) { video.current.pause(); saveVideo(true); } onClose(); }
  async function complete() {
    if (!course) return;
    setBusy(true);
    try { await onProgress(course.id, course.minutes * 60, course.minutes * 60, true, course.revision); setError(""); }
    catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function favoriteCourse() {
    if (!course || favoriting) return;
    setFavoriting(true);
    try { await onFavorite(course); setError(""); } catch (e) { setError(errorMessage(e)); } finally { setFavoriting(false); }
  }
  return <dialog ref={modal} className="module-dialog journey-dialog academy-course-dialog" aria-labelledby="academy-course-title" onCancel={event => { event.preventDefault(); close(); }}><JourneyDialogSurface><div className="module-dialog-heading"><span className="badge-eyebrow">AI ACADEMY</span><button onClick={close} aria-label="关闭课程">关闭</button></div>{!course ? <><h2 id="academy-course-title">课程暂不可用</h2><p>该课程已下架或已更新，请返回课程列表查看。</p></> : <><span className="module-tag">{category(course)}</span><h2 id="academy-course-title">{course.title}</h2><p className="academy-detail-summary">{course.summary}</p><div className="module-meta"><span>{course.author.name}</span><span>{course.minutes} 分钟</span><span>{course.completed ? "已完成学习" : `学习进度 ${Math.round(course.progress)}%`}</span></div><div className="academy-course-tags">{course.tags.map(label => <span className="module-tag" key={label}>{label}</span>)}</div>{course.type === "video" ? <><video ref={video} className="academy-player" poster={academyCoverSource(course)} controls preload="metadata" playsInline src={`/api/learner/academy/courses/${course.id}/video?revision=${course.revision}`} aria-label={`${course.title} 课程视频`} onLoadedMetadata={event => { const el = event.currentTarget; if (initialSeconds.current > 0 && initialSeconds.current < el.duration - 1) el.currentTime = initialSeconds.current; setMediaError(false); }} onTimeUpdate={() => saveVideo()} onPause={() => saveVideo(true)} onEnded={() => saveVideo(true)} onError={() => setMediaError(true)} />{mediaError ? <p className="academy-error" role="alert">视频暂时无法播放，请确认网络或刷新课程。<button className="module-secondary" onClick={() => { setMediaError(false); video.current?.load(); }}>重新加载视频</button></p> : <p className="academy-player-note">播放进度会自动保存，下次打开时可继续观看。</p>}</> : <div className="academy-link-actions"><a className="module-primary" href={safeLink(course.url) || undefined} target="_blank" rel="noopener noreferrer" onClick={() => { void onProgress(course.id, Math.max(course.seconds, 1), course.minutes * 60, undefined, course.revision).catch(e => setError(errorMessage(e))); }}>打开课程内容 ↗</a><button className="module-secondary" disabled={busy || course.completed} onClick={() => void complete()}>{busy ? "正在保存…" : course.completed ? "已完成学习" : "我已完成学习"}</button><p>课程在新窗口打开，阅读完成后回到这里记录学习状态。</p></div>}<div className="academy-detail-actions"><button className="module-secondary" aria-pressed={course.favorite} disabled={favoriteBusy || favoriting} onClick={() => void favoriteCourse()}>{course.favorite ? "取消收藏" : "收藏课程"}</button>{error && <p role="alert" className="academy-error">{error}</p>}</div></>}</JourneyDialogSurface></dialog>;
}

function ShareDialog({ item, tags, onClose, onSaved }: { item: AcademyShare | null; tags: string[]; onClose: () => void; onSaved: () => void }) {
  const modal = useRef<HTMLDialogElement>(null);
  const [draftId] = useState(() => crypto.randomUUID());
  const [selectedTags, setSelectedTags] = useState<string[]>(item?.tags || []), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => { const el = modal.current; el?.showModal(); return () => el?.close(); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget), url = String(form.get("url") || "").trim();
    if (!safeLink(url)) { setError("请填写完整的 http 或 https 课程链接，不支持含账号密码的链接。"); return; }
    setBusy(true); setError("");
    try {
      await academyRequest({ command: item ? "resubmit" : "share", ...(item ? { id: item.id, revision: item.revision } : { id: draftId }), title: String(form.get("title") || "").trim(), summary: String(form.get("summary") || "").trim(), url, minutes: Number(form.get("minutes")), tags: selectedTags });
      onSaved();
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <dialog ref={modal} className="module-dialog journey-dialog academy-share-dialog" aria-labelledby="academy-share-title" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }}><JourneyDialogSurface><div className="module-dialog-heading"><span className="badge-eyebrow">SHARE & GROW</span><button disabled={busy} onClick={onClose}>关闭</button></div><h2 id="academy-share-title">{item ? "修改并重新提交分享" : "分享我的发现"}</h2><p>分享一份可复用的方法或资源，审核通过后让更多同学看到。</p>{item?.reason && <p className="academy-review-reason">上次审核意见：{item.reason}</p>}<form onSubmit={event => void submit(event)}><fieldset disabled={busy}><label className="module-field">课程名称 *<input name="title" required maxLength={100} defaultValue={item?.title || ""} placeholder="给你的方法起一个清晰的名字" /></label><label className="module-field">课程简介 *<textarea name="summary" required maxLength={1200} rows={4} defaultValue={item?.summary || ""} placeholder="它解决了什么问题？适合哪些同学？" /></label><label className="module-field">资源链接 *<input name="url" type="url" required maxLength={2000} defaultValue={item?.url || ""} placeholder="https://…" /></label><label className="module-field">预计时长（分钟）<input name="minutes" type="number" min="0.1" max="1440" step="0.1" required defaultValue={item?.minutes || 15} /></label><fieldset className="academy-share-tags"><legend>课程标签（可多选）</legend>{tags.map(tag => <label key={tag}><input type="checkbox" checked={selectedTags.includes(tag)} onChange={() => setSelectedTags(old => old.includes(tag) ? old.filter(value => value !== tag) : [...old, tag])} /><span>{tag}</span></label>)}</fieldset>{error && <p className="academy-error" role="alert">{error}</p>}<div className="academy-detail-actions"><button type="button" className="module-secondary" onClick={onClose}>取消</button><button className="module-primary" type="submit">{busy ? "正在提交…" : "提交审核 →"}</button></div></fieldset></form></JourneyDialogSurface></dialog>;
}
