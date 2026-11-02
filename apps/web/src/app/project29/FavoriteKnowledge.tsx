import { type AcademyCourse } from "./moduleDemoData";
import { ModuleIcon, ModulePanel } from "./ModuleShell";

export function KnowledgeSaveButton({ course, saved, onToggle }: {
  course: AcademyCourse;
  saved: boolean;
  onToggle: (id: string) => void;
}) {
  return <button className={`knowledge-save-toggle${saved ? " is-saved" : ""}`}
    aria-label={`${saved ? "取消收藏" : "收藏"} ${course.title}`} aria-pressed={saved} onClick={() => onToggle(course.id)}>
    <ModuleIcon file={saved ? "b5cc7" : "cdc4e"} size={16} /><span>{saved ? "已收藏" : "收藏"}</span>
  </button>;
}

export function FavoriteKnowledge({ courses, favoriteIds, query = "", compact = false, headingLevel = "h2", onToggle, onOpen, onBrowse, onShowAll, onClearSearch }: {
  courses: AcademyCourse[];
  favoriteIds: string[];
  query?: string;
  compact?: boolean;
  headingLevel?: "h1" | "h2";
  onToggle: (id: string) => void;
  onOpen: (course: AcademyCourse) => void;
  onBrowse: () => void;
  onShowAll?: () => void;
  onClearSearch?: () => void;
}) {
  const saved = courses.filter(course => favoriteIds.includes(course.id));
  const matching = saved.filter(course => `${course.title}${course.description}${course.domain}`.toLowerCase().includes(query.trim().toLowerCase()));
  const visible = compact ? matching.slice(0, 3) : matching;
  const Heading = headingLevel;
  return <ModulePanel className={`favorite-knowledge${compact ? " is-compact" : ""}`}>
    <div className="favorite-knowledge-heading">
      <span className="favorite-knowledge-symbol"><ModuleIcon file="b5cc7" size={26} /></span>
      <div><Heading>我的收藏 <span aria-label={`共 ${saved.length} 条收藏`}>{saved.length}</span></Heading><p>AI 学院的知识科普，收藏后随时回来查看。</p></div>
      <button data-page-navigation className="module-secondary" onClick={compact && onShowAll ? onShowAll : onBrowse}>{compact && onShowAll ? "查看全部" : "去 AI 学院"} <span aria-hidden="true">→</span></button>
    </div>
    <div className="favorite-knowledge-list">
      {visible.map((course, index) => <article className="favorite-knowledge-row" key={course.id}>
        <span className="favorite-knowledge-index">{String(index + 1).padStart(2, "0")}</span>
        <div className="favorite-knowledge-copy"><button onClick={() => onOpen(course)}>{course.title}</button><p>AI 学院 · {course.domain} · {course.minutes} 分钟{course.unavailable ? " · 内容暂不可用" : ""}</p></div>
        <button className="favorite-knowledge-read" onClick={() => onOpen(course)}>查看 <span aria-hidden="true">→</span></button>
        <KnowledgeSaveButton course={course} saved onToggle={onToggle} />
      </article>)}
      {!visible.length && <div className="favorite-knowledge-empty"><ModuleIcon file="cdc4e" size={30} /><h3>{query.trim() && saved.length ? "没有找到匹配的收藏" : "暂未开放"}</h3><p>{query.trim() && saved.length ? "试试其他搜索词，或清空搜索查看全部收藏。" : "课程收藏功能暂未开放。"}</p><button data-page-navigation className="module-secondary" onClick={query.trim() && saved.length && onClearSearch ? onClearSearch : onBrowse}>{query.trim() && saved.length && onClearSearch ? "清空搜索" : "去 AI 学院看看"}</button></div>}
    </div>
    {compact && matching.length > visible.length && onShowAll && <button className="favorite-knowledge-more" onClick={onShowAll}>查看其余 {matching.length - visible.length} 条收藏 <span aria-hidden="true">→</span></button>}
  </ModulePanel>;
}
