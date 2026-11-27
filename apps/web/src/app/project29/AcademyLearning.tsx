"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { AcademyCatalogSection } from "./AcademyCatalogCard";
import { AcademyAccount } from "./AcademyAccount";
import { AcademyCourseEntry } from "./AcademyCourseEntry";
import { AcademyCourseCover } from "./AcademyCourseCover";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { academyRequest, courseUpdateTime, useAcademy, type AcademyItem, type AcademyShare } from "./useAcademy";
import "./academyLearning.css";

function academyCourseHref(id: string) {
  return `/app?view=academy&course=${encodeURIComponent(id)}`;
}

function category(course: AcademyItem) {
  if (course.enhanced) return course.chapters && course.chapters.length>1 ? "系列课程" : "学院课程";
  return ({ link: "管理员外链", video: "平台视频", share: "员工共建" })[course.type];
}
function matchesKind(course: AcademyItem, kind: string) {
  return kind === "all" || (course.enhanced ? course.materials?.some(material=>material.kind===kind) : course.type===kind);
}
function learningStatus(course: AcademyItem) {
  if (course.completed) return "已完成";
  if (course.progress > 0) return Math.max(1, Math.round(course.progress)) + "%";
  return course.seconds > 0 ? "学习中" : "尚未开始";
}
const date = (value: string) => new Date(value).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" });
const safeLink = (value: string) => { try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) && !u.username && !u.password ? u.href : ""; } catch { return ""; } };
const errorMessage = (e: unknown) => e instanceof Error ? e.message : "操作失败，请重试。";

type AcademyCatalogProps = {
  active: boolean; savedOnly: boolean; query: string; onSaved: (saved: boolean) => void; onClearSearch: () => void;
  learnerName: string; onOpenAccount: () => void;
};

export function AcademyLearning({ courseId, ...props }: AcademyCatalogProps & { courseId?: string }) {
  return courseId ? <AcademyCourseEntry courseId={courseId} /> : <AcademyCatalog {...props} />;
}

function AcademyCatalog({ active, savedOnly, query, onSaved, onClearSearch, learnerName, onOpenAccount }: AcademyCatalogProps) {
  const academy = useAcademy(active);
  const [kind, setKind] = useState("all"), [tag, setTag] = useState("all"), [sort, setSort] = useState("newest");
  const [view, setView] = useState<"courses" | "records" | "shares">("courses");
  const [share, setShare] = useState<AcademyShare | "new" | null>(null);
  const [busyFavorite, setBusyFavorite] = useState("");
  const [notice, setNotice] = useState("");
  const [showAccount, setShowAccount] = useState(false);
  const [lastSavedOnly, setLastSavedOnly] = useState(savedOnly);
  if (lastSavedOnly !== savedOnly) { setLastSavedOnly(savedOnly); setKind("all"); setTag("all"); }
  if (!active && share) setShare(null);
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(""), 5000); return () => window.clearTimeout(timer); }, [notice]);
  const favorites = academy.courses.filter(course => course.favorite);
  const completed = academy.courses.filter(course => course.completed);
  const started = academy.courses.filter(course => course.progress > 0 || course.seconds > 0 || course.completed);
  const search = query.trim().toLocaleLowerCase();
  const pool = savedOnly ? favorites : view === "records" ? started : academy.courses;
  const kinds = [["all", "全部类型"], ["link", "链接"], ["video", "视频"], ["document", "文档"], ["image", "图片"], ["share", "员工共建"]];
  const sections: ["courses" | "records" | "shares" | "saved", string, number][] = [
    ["courses", "课程目录", academy.courses.length], ["records", "学习记录", started.length], ["saved", "我的收藏", favorites.length], ["shares", "我的分享", academy.shares.length],
  ];
  const visible = pool.filter(course => matchesKind(course, kind) && (tag === "all" || course.tags.includes(tag))
    && `${course.title} ${course.summary} ${course.author.name} ${course.tags.join(" ")}`.toLocaleLowerCase().includes(search))
    .sort((a, b) => {
      if (sort === "duration") return a.minutes - b.minutes;
      if (sort === "title") return a.title.localeCompare(b.title, "zh-CN");
      return (courseUpdateTime(b) ?? Number.MIN_SAFE_INTEGER) - (courseUpdateTime(a) ?? Number.MIN_SAFE_INTEGER);
    });
  async function toggle(course: AcademyItem) {
    if (busyFavorite) return;
    setBusyFavorite(course.id);
    try { await academy.favorite(course.id, !course.favorite); setNotice(course.favorite ? "已取消收藏" : "已收藏课程"); }
    catch (e) { setNotice(errorMessage(e)); }
    finally { setBusyFavorite(""); }
  }
  function showView(next: "courses" | "records" | "shares") { if (savedOnly) onSaved(false); setView(next); }
  const isCatalog = !savedOnly && view === "courses";
  const filtered = Boolean(search || tag !== "all" || kind !== "all");
  const sectionTitle = filtered ? "筛选结果" : savedOnly ? "收藏的课程" : view === "records" ? "已开始的课程" : sort === "newest" ? "最新课程" : "全部课程";
  const inProgress = started.filter(course => !course.completed);
  const personalCourses = inProgress.length ? inProgress : favorites;
  const cardProps = { category, learningStatus, busyFavorite, courseHref: academyCourseHref, onFavorite: toggle };
  return <section className="academy-learning academy-catalog">
    <header className="academy-catalog-header">
      <div className="academy-heading-copy">
        <h1>AI 学院</h1>
        <p>已完成 <strong>{completed.length}</strong> / {academy.courses.length} 门课程</p>
      </div>
      <div className="academy-header-actions">
        {inProgress.length > 0 && <a className="module-secondary academy-course-link" href={academyCourseHref(inProgress[0].id)}>继续学习</a>}
        <button type="button" className="module-secondary accent" onClick={() => setShare("new")}><ModuleIcon file="d4a6c" size={16} />分享课程</button>
      </div>
    </header>
    <section className="academy-identity" aria-label="我的学院账号"><div className="academy-identity-bar">
      <span>当前学员 <strong>{learnerName}</strong></span>
      <span title={academy.academyXp === undefined ? "当前账号暂未提供学院经验统计" : undefined}>
        学院累计经验 <strong>{academy.academyXp ?? "—"}</strong>
      </span>
      <button type="button" onClick={() => setShowAccount(true)}>我的成长账户</button>
    </div>
    </section>
    {active && showAccount && <AcademyAccount name={learnerName} close={() => setShowAccount(false)}
      openProfile={() => { setShowAccount(false); onOpenAccount(); }} />}
    <div className="academy-catalog-listing">
      <div className="academy-browse-bar">
        <nav className="academy-catalog-tabs" aria-label="学院栏目">
          {sections.map(([id, label, count]) => <button key={id} type="button" aria-current={(savedOnly ? id === "saved" : view === id) ? "page" : undefined}
            onClick={() => id === "saved" ? onSaved(true) : showView(id)}>{label}<span>{count}</span></button>)}
        </nav>
        {(savedOnly || view !== "shares") && <div className="academy-browse-filters">
          <select aria-label="课程分类" value={kind} onChange={event => setKind(event.target.value)}>
            {kinds.map(([id, label]) =>
              <option key={id} value={id}>{label}（{pool.filter(course => matchesKind(course, id)).length}）</option>)}
          </select>
          <select aria-label="课程标签" value={tag} onChange={event => setTag(event.target.value)}>
            <option value="all">全部标签</option>
            {academy.tags.map(label => <option key={label} value={label}>{label}</option>)}
          </select>
          <select aria-label="课程排序" value={sort} onChange={event => setSort(event.target.value)}>
            <option value="newest">最近更新</option><option value="duration">用时最短</option><option value="title">按名称排序</option>
          </select>
          <button type="button" className="academy-refresh" onClick={() => void academy.refresh()}>刷新</button>
        </div>}
      </div>
      {academy.error && <div className="academy-error" role="alert">{academy.error}<button className="module-secondary" onClick={() => void academy.refresh()}>重新加载</button></div>}
      {academy.loading ? <ModulePanel className="academy-empty"><p role="status">正在读取学院内容…</p></ModulePanel> : view === "shares" && !savedOnly ? <ModulePanel className="academy-share-list"><div className="module-row"><h2>我的分享</h2><button className="module-secondary" onClick={() => void academy.refresh()}>刷新审核状态</button></div>{academy.shares.filter(item => `${item.title} ${item.summary}`.toLocaleLowerCase().includes(search)).map(item => <article key={item.id}><div className="module-row"><h3>{item.title}</h3><span className={`module-tag academy-share-${item.status}`}>{({ pending: "待审核", approved: "已通过", rejected: "已驳回" })[item.status]}</span></div><p>{item.summary}</p><div className="academy-course-tags">{item.tags.map(label => <span className="module-tag" key={label}>{label}</span>)}</div><div className="module-row"><small>提交于 {date(item.createdAt)}</small><a className="module-secondary" href={safeLink(item.url) || undefined} target="_blank" rel="noopener noreferrer">查看分享链接 ↗</a></div>{item.reason && <p className="academy-review-reason">审核意见：{item.reason}</p>}{item.status === "rejected" && <button className="module-secondary" onClick={() => setShare(item)}>修改并重新提交</button>}</article>)}{!academy.shares.length && <div className="academy-empty"><h3>还没有提交分享</h3><p>分享一份有用的方法或资源，审核通过后会出现在学院课程中。</p><button className="module-primary" onClick={() => setShare("new")}>分享我的发现 →</button></div>}</ModulePanel> : <>
        <AcademyCatalogSection title={sectionTitle} courses={visible} {...cardProps} />
        {isCatalog && !filtered && sort === "newest" && personalCourses.length > 0 && <AcademyCatalogSection
          title={inProgress.length ? "继续学习" : "我的收藏"} courses={personalCourses} layout="shelf" {...cardProps} />}
        {!visible.length && !academy.error && <ModulePanel className="academy-empty"><ModuleIcon file="643cc" size={34} /><h3>{pool.length ? "没有找到匹配的课程" : savedOnly ? "还没有收藏课程" : view === "records" ? "还没有学习记录" : "暂无已发布课程"}</h3><p>{pool.length ? "试试其他标签、类型或搜索词。" : savedOnly ? "在课程卡片点击“收藏”，即可在这里找到它。" : view === "records" ? "选择一门课程开始学习，进度会保存在这里。" : "管理员发布课程后，内容会显示在这里。"}</p><button className="module-secondary" onClick={() => { setKind("all"); setTag("all"); onClearSearch(); showView("courses"); }}>查看全部课程</button></ModulePanel>}
      </>}
    </div>
    {active && share && <ShareDialog item={share === "new" ? null : share} tags={academy.tags} onClose={() => setShare(null)} onSaved={() => { setShare(null); setView("shares"); onSaved(false); setNotice("分享已提交，等待管理员审核。"); void academy.refresh(); }} />}
    {notice && <div className="module-toast" role="status">{notice}<button aria-label="关闭提示" onClick={() => setNotice("")}> ×</button></div>}
  </section>;
}

export function AcademyFavoritesPreview({ onBrowse, onViewAll }: { onBrowse: () => void; onViewAll: () => void }) {
  const academy = useAcademy(true);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const saved = academy.courses.filter(course => course.favorite);
  async function toggle(course: AcademyItem) {
    if (busy) return;
    setBusy(true);
    try { await academy.favorite(course.id, !course.favorite); setError(""); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
return <><ModulePanel className="favorite-knowledge is-compact"><div className="favorite-knowledge-heading"><span className="favorite-knowledge-symbol"><ModuleIcon file="b5cc7" size={26} /></span><div><h2>我的收藏 <span>{saved.length}</span></h2><p>AI 学院的知识科普，收藏后随时回来查看。</p></div><button data-page-navigation className="module-secondary" onClick={onViewAll}>查看全部 →</button></div><div className="favorite-knowledge-list">{academy.loading ? <p role="status">正在读取收藏…</p> : academy.error ? <p role="alert">{academy.error}<button onClick={() => void academy.refresh()}>重新加载</button></p> : saved.length ? saved.slice(0, 3).map((course, index) => <article className="favorite-knowledge-row" key={course.id}>{course.coverUrl || course.coverVideoUrl ? <div className="academy-favorite-cover" aria-hidden="true"><AcademyCourseCover course={course} index={academy.courses.indexOf(course) % 6} /></div> : <span className="favorite-knowledge-index">{String(index + 1).padStart(2, "0")}</span>}<div className="favorite-knowledge-copy"><a className="academy-course-link" href={academyCourseHref(course.id)}>{course.title}</a><p>AI 学院 · {category(course)} · {course.minutes} 分钟</p></div><a className="favorite-knowledge-read academy-course-link" href={academyCourseHref(course.id)}>查看 →</a><button className="knowledge-save-toggle is-saved" disabled={busy} aria-label={`取消收藏 ${course.title}`} onClick={() => void toggle(course)}><ModuleIcon file="b5cc7" size={16} />已收藏</button></article>) : <div className="favorite-knowledge-empty"><h3>还没有收藏课程</h3><p>去 AI 学院发现感兴趣的课程，收藏后可随时回来学习。</p><button data-page-navigation className="module-secondary" onClick={onBrowse}>去 AI 学院看看 →</button></div>}{error && <p role="alert">{error}</p>}</div></ModulePanel></>;
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
