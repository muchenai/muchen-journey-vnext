"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { markAllLearnerNotificationsRead, markLearnerNotificationRead } from "../actions";
import type { LearnerNotification, LearnerNotificationPage } from "@/lib/learner-notifications";

export function ReviewNotificationBell({ children }: { children: ReactNode }) {
  const panelId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const controller = useRef<AbortController | null>(null);
  const writing = useRef(false);
  const visibleCount = useRef(30);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<LearnerNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async (after?: string) => {
    controller.current?.abort();
    const pending = new AbortController();
    controller.current = pending;
    setLoading(true);
    try {
      const readPage = async (cursor?: string) => {
        const response = await fetch(`/api/learner/notifications${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
          { cache: "no-store", signal: pending.signal });
        const page = await response.json() as LearnerNotificationPage & { error?: string };
        if (!response.ok) throw new Error(page.error || "通知读取失败，请重试。");
        return page;
      };
      let page = await readPage(after);
      const incoming = [...page.items];
      // Refresh every loaded page so read changes on another device are reflected.
      while (!after && page.nextCursor && incoming.length < visibleCount.current) {
        page = await readPage(page.nextCursor);
        incoming.push(...page.items);
      }
      if (pending.signal.aborted) return;
      visibleCount.current = after ? visibleCount.current + incoming.length : Math.max(30, incoming.length);
      setItems(previous => {
        const merged = new Map((after ? previous : []).map(item => [item.id, item]));
        for (const item of incoming) merged.set(item.id, item);
        return [...merged.values()].sort((a, b) => b.reviewedAt.localeCompare(a.reviewedAt) || b.id.localeCompare(a.id));
      });
      setCursor(page.nextCursor);
      setUnread(page.unreadCount);
      setLoaded(true);
      setError("");
    } catch (failure) {
      if (!pending.signal.aborted) setError(failure instanceof Error ? failure.message : "通知读取失败，请重试。");
    } finally {
      if (!pending.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const check = () => { if (!document.hidden && !writing.current) void refresh(); };
    check();
    const timer = window.setInterval(check, 30_000);
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    return () => {
      clearInterval(timer); controller.current?.abort();
      window.removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", check);
    };
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);

  async function mark(item?: LearnerNotification, navigate = false) {
    if (writing.current) return;
    writing.current = true; setBusy(true); setError("");
    controller.current?.abort(); setLoading(false);
    try {
      const result = item ? (item.readAt ? {} : await markLearnerNotificationRead(item.id))
        : await markAllLearnerNotificationsRead();
      if (result.error) { setError(result.error); return; }
      setItems(previous => item ? previous.filter(row => row.id !== item.id) : []);
      if (!item) setCursor(null);
      setUnread(count => item ? Math.max(0, count - (item.readAt ? 0 : 1)) : 0);
      if (item && navigate) {
        window.location.assign(`/app/tasks/${encodeURIComponent(item.assignmentId)}?view=review`);
      } else await refresh();
    } catch {
      setError("标记已读失败，请重试。");
    } finally { writing.current = false; setBusy(false); }
  }

  return <div className="review-notifications" ref={root}>
    <button className="review-notification-trigger" ref={trigger} type="button"
      aria-label={unread ? `查看通知，${unread}条未读` : "查看通知"}
      aria-expanded={open} aria-controls={panelId}
      onClick={() => { setOpen(value => !value); if (!open && !writing.current) void refresh(); }}>
      {children}
      {unread > 0 && <span className="review-notification-count">{unread > 99 ? "99+" : unread}</span>}
    </button>
    {open && <ReviewNotificationPanel panelId={panelId} unread={unread} busy={busy} loading={loading}
      loaded={loaded} error={error} items={items} cursor={cursor} mark={mark} refresh={refresh} />}
  </div>;
}

export function ReviewNotificationPanel({ panelId, unread, busy, loading, loaded, error, items, cursor, mark, refresh }: {
  panelId: string; unread: number; busy: boolean; loading: boolean; loaded: boolean; error: string;
  items: LearnerNotification[]; cursor: string | null;
  mark: (item?: LearnerNotification, navigate?: boolean) => Promise<void>;
  refresh: (after?: string) => Promise<void>;
}) {
  const unreadItems = items.filter(item => !item.readAt);
  return <section id={panelId} className="review-notification-panel" aria-label="审核结果通知">
      <header><h2>审核通知{unread > 0 ? ` · ${unread}条未读` : ""}</h2>
        <button type="button" disabled={busy || !unread} onClick={() => void mark()}>全部已读</button></header>
      {error && <div className="review-notification-error" role="alert">{error}
        <button type="button" disabled={busy || loading} onClick={() => void refresh()}>重新读取</button></div>}
      <div className="review-notification-list" aria-busy={loading || busy}>
        {!loaded && !error && <p className="review-notification-empty">正在读取通知…</p>}
        {loaded && !unreadItems.length && <p className="review-notification-empty">暂无未读通知</p>}
        {unreadItems.map(item => <article className="review-notification-item" data-unread={!item.readAt} key={item.id}>
          <button className="review-notification-link" type="button" disabled={busy} onClick={() => void mark(item, true)}>
            {!item.readAt && <span className="review-notification-dot" aria-label="未读" />}
            <strong>{item.taskTitle}</strong>
            <span className="review-notification-result" data-decision={item.decision}>
              {item.decision === "PASS" ? "审核已通过" : "已退回，请修改"}</span>
            <time dateTime={item.reviewedAt}>{new Date(item.reviewedAt).toLocaleString("zh-CN", { hour12: false })}</time>
          </button>
          {!item.readAt && <button className="review-notification-read" type="button" disabled={busy}
            onClick={() => void mark(item)}>标为已读</button>}
        </article>)}
        {cursor && <button className="review-notification-more" type="button" disabled={loading || busy}
          onClick={() => void refresh(cursor)}>{loading ? "正在读取…" : "查看更多"}</button>}
      </div>
    </section>;
}
