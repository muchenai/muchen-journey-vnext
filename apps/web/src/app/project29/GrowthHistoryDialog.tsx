import { useCallback, useEffect, useId, useRef, useState } from "react";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { pointNames } from "./VillageTaskCard";
import { formatGrowthDelta, readGrowthPage, type GrowthEntry, type GrowthPage } from "./profileGrowth";

export function GrowthHistoryContent({ page, loading, error, onRetry, onMore }: {
  page: GrowthPage | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onMore: () => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  return <div className="profile-growth-content" aria-busy={loading}>
    {page && <p className="profile-growth-count">共 {page.total.toLocaleString("zh-CN")} 条记录 · 按时间倒序</p>}
    <div className="profile-growth-scroll" role="region" aria-label="成长记录，可上下滚动" tabIndex={0}>
    {error && <div className="profile-growth-error" role="alert"><p>{error}</p><button className="module-secondary" disabled={loading} onClick={onRetry}>重新读取</button></div>}
    {!page && loading && <p className="profile-growth-empty" role="status">正在读取成长明细…</p>}
    {page && page.items.length === 0 && !error && <div className="profile-growth-empty"><h3>还没有成长记录</h3><p>新手村任务审核通过或兑换徽章后，相关记录会显示在这里。</p></div>}
    {page && page.items.length > 0 && <>
      <ol className="profile-growth-list">{page.items.map(item => <GrowthHistoryRow key={item.id} item={item}
        expanded={expandedId === item.id} onToggle={() => setExpandedId(current => current === item.id ? null : item.id)} />)}</ol>
      <div className="profile-growth-pagination">
        {page.hasMore ? <button className="module-secondary" disabled={loading} onClick={onMore}>{loading ? "正在读取…" : "加载更多"}</button>
          : <span>已显示全部成长记录</span>}
      </div>
    </>}
    </div>
  </div>;
}

function GrowthHistoryRow({ item, expanded, onToggle }: { item: GrowthEntry; expanded: boolean; onToggle: () => void }) {
  const detailId = useId();
  const at = new Date(item.occurredAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  const pointTypes = new Set(item.badgePoints.filter(point => point.points !== 0).map(point => point.id)).size;
  const summary = item.kind === "medal_redemption"
    ? `获得 1 枚徽章${pointTypes ? ` · 消耗 ${pointTypes} 类徽章点` : ""}`
    : [item.xp ? `${formatGrowthDelta(item.xp)} XP` : "", pointTypes ? `${pointTypes} 类徽章点` : ""].filter(Boolean).join(" · ");
  return <li className="profile-growth-entry">
    <button type="button" className="profile-growth-toggle" aria-expanded={expanded} aria-controls={detailId} onClick={onToggle}>
      <span className="profile-growth-entry-heading"><span className="module-tag">{item.module} · {item.kind === "task_reward" ? "任务奖励" : "获得徽章"}</span><time dateTime={item.occurredAt}>{at}</time></span>
      <span className="profile-growth-summary"><strong>{item.title}</strong><span className="profile-growth-chevron" aria-hidden="true">{expanded ? "−" : "+"}</span></span>
      <span className="profile-growth-overview">{summary || "查看奖励明细"}<span>{expanded ? "收起详情" : "展开详情"}</span></span>
    </button>
    <div id={detailId} className="profile-growth-details" hidden={!expanded}>
    <p className="profile-growth-method">{item.method}{item.medal ? ` · 已获得「${item.medal.name}」` : ""}</p>
    <div className="profile-growth-changes">
      {item.xp !== 0 && <span data-direction={item.xp > 0 ? "gain" : "cost"}><b>{formatGrowthDelta(item.xp)} XP</b><small>经验值</small></span>}
      {item.badgePoints.filter(point => point.points !== 0).map(point => <span key={point.id} data-direction={point.points > 0 ? "gain" : "cost"}><b>{formatGrowthDelta(point.points)} 点</b><small>{pointNames[point.id] || point.id}徽章点</small></span>)}
    </div>
    </div>
  </li>;
}

export function GrowthHistoryDialog({ onClose, onRefreshSummary }: { onClose: () => void; onRefreshSummary?: () => void }) {
  const modal = useRef<HTMLDialogElement>(null);
  const pending = useRef<AbortController | null>(null);
  const [page, setPage] = useState<GrowthPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const nextOffset = useRef(0);
  const requestedOffset = useRef(0);
  const load = useCallback(async (offset: number) => {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    requestedOffset.current = offset;
    setLoading(true); setError("");
    try {
      const result = await readGrowthPage(offset, controller.signal);
      if (controller.signal.aborted) return;
      nextOffset.current = result.nextOffset ?? offset;
      setPage(previous => offset === 0 || !previous ? result : {
        ...result,
        items: [...previous.items, ...result.items.filter(item => !previous.items.some(old => old.id === item.id))],
      });
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "成长明细读取失败，请重试。");
    } finally {
      if (!controller.signal.aborted) { pending.current = null; setLoading(false); }
    }
  }, []);
  useEffect(() => {
    const element = modal.current;
    element?.showModal();
    const initial = window.setTimeout(() => void load(0), 0);
    return () => { window.clearTimeout(initial); pending.current?.abort(); pending.current = null; element?.close(); };
  }, [load]);
  const refresh = () => { if (pending.current) return; onRefreshSummary?.(); void load(0); };
  return <dialog ref={modal} className="module-dialog journey-dialog profile-growth-dialog" aria-labelledby="profile-growth-title" aria-describedby="profile-growth-description" onCancel={onClose}>
    <JourneyDialogSurface>
      <div className="module-dialog-heading"><span className="badge-eyebrow">MY GROWTH RECORDS</span><button onClick={onClose} aria-label="关闭成长明细">关闭 ×</button></div>
      <div className="profile-growth-heading"><h2 id="profile-growth-title">成长明细</h2><button className="module-secondary" disabled={loading} onClick={refresh}>刷新记录</button></div>
      <p id="profile-growth-description">查看经验、徽章点的来源与徽章获取记录。商城积分与经验兑换暂未开放。</p>
      <GrowthHistoryContent page={page} loading={loading} error={error} onRetry={() => void load(requestedOffset.current)} onMore={() => void load(nextOffset.current)} />
    </JourneyDialogSurface>
  </dialog>;
}
