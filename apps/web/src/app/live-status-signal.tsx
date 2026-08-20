"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

const REFRESH_INTERVAL_MS = 12_000;

export function LiveStatusSignal({
  statusKey,
  active,
  title,
  detail,
  changedMessage,
  initialMessage = null,
}: {
  statusKey: string;
  active: boolean;
  title: string;
  detail: string;
  changedMessage: string;
  initialMessage?: string | null;
}) {
  const router = useRouter();
  const previousStatus = useRef(statusKey);
  const [announcement, setAnnouncement] = useState(initialMessage);
  const [, startTransition] = useTransition();

  useEffect(() => {
    if (previousStatus.current !== statusKey) {
      previousStatus.current = statusKey;
      setAnnouncement(changedMessage);
    }
  }, [changedMessage, statusKey]);

  useEffect(() => {
    if (!active) return;

    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      startTransition(() => router.refresh());
    };
    const interval = window.setInterval(refresh, REFRESH_INTERVAL_MS);
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [active, router]);

  if (!active && !announcement) return null;

  return (
    <section className="live-status-signal" role="status" aria-live="polite">
      <span aria-hidden="true">{active ? "◌" : "✓"}</span>
      <div>
        <strong>{announcement ?? title}</strong>
        <small>{announcement ? "当前页面已经同步到最新状态。" : detail}</small>
      </div>
    </section>
  );
}
