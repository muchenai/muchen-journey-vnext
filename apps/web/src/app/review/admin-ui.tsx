"use client";
import { useEffect, useEffectEvent, useRef, type ReactNode } from "react";
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
 const paths: Record<string, ReactNode> = {
  plus: <path d="M12 5v14M5 12h14"/>, check: <path d="m5 12 4 4L19 6"/>, close: <path d="m6 6 12 12M6 18 18 6"/>,
  review: <><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v4H9zm0 10 2 2 4-4"/></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  checkCircle: <><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></>,
  book: <path d="M12 5C8 2 4 3 2 4v15c3-1.5 6-1 10 1 4-2 7-2.5 10-1V4c-2-1-6-2-10 1Zm0 0v15"/>,
  library: <path d="M4 4v16M9 4v16M14 4v16M18 4l3 16"/>,
  arrowRight: <path d="M4 12h16m-6-6 6 6-6 6"/>,
  chevronDown: <path d="m5 9 7 7 7-7"/>,
  chevronRight: <path d="m9 5 7 7-7 7"/>,
  alert: <><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3v1"/></>,
  star: <path d="m12 3 2.8 5.6 6.2.9-4.5 4.4 1.1 6.1-5.6-2.9L6.4 20l1.1-6.1L3 9.5l6.2-.9L12 3Z"/>,
  send: <><path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/></>,
  upload: <path d="M12 16V3m-5 5 5-5 5 5M4 16v4h16v-4"/>,
  publish: <><path d="M12 20H4V4h12v5M9 15l10-10 3 3-10 10-4 1z"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></>,
  moon: <path d="M20.8 13a8.8 8.8 0 0 1-9.8-9.8A9 9 0 1 0 20.8 13Z"/>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></>,
  shield: <><path d="m12 3 8 3v6c0 4-3.5 7-8 9-4.5-2-8-5-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
  award: <><circle cx="12" cy="8" r="5"/><path d="m8 12-2 9 6-3 6 3-2-9"/></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
  link: <path d="m10 13 4-4M8 16l-1 1a4.2 4.2 0 0 1-6-6l4-4a4.2 4.2 0 0 1 6 0m2 1 1-1a4.2 4.2 0 0 1 6 6l-4 4a4.2 4.2 0 0 1-6 0" transform="translate(1 1)"/>,
  file: <><path d="M14 2H5v20h14V7l-5-5Z"/><path d="M14 2v5h5M8 12h8M8 16h6"/></>,
  image: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5L5 21"/></>,
  trash: <path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>,
  external: <><path d="M14 3h7v7m0-7L10 14M10 3H3v18h18v-7"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  sparkles: <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4"/>,
  user: <><circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
  download: <path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>,
  help: <><circle cx="12" cy="12" r="9"/><path d="M9 8c0-3 6-3 6 0 0 2-3 2-3 5m0 3v1"/></>,
 };
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.file}</svg>;
}
export function Modal({ children, close, title, busy = false, className = '' }: { children: ReactNode; close: () => void; title: string; busy?: boolean; className?: string }) {
 const ref = useRef<HTMLElement>(null);
 const escape = useEffectEvent(() => { if (!busy) close(); });
 useEffect(() => {
  const before = document.activeElement as HTMLElement | null;
  const overflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  ref.current?.querySelector<HTMLElement>("button,input,select,textarea")?.focus();
  function key(e: KeyboardEvent) {
   if (e.key === "Escape") escape();
   if (e.key !== "Tab") return;
   const controls = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]') ?? []).filter(x => x.getClientRects().length);
   const first = controls[0], last = controls.at(-1);
   if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
   else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
  }
  document.addEventListener("keydown", key);
  return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", key); before?.focus(); };
 }, []);
 return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget && !busy) close(); }}><section ref={ref} className={`modal ${className}`} role="dialog" aria-modal="true" aria-label={title}><button className="modal-close icon-btn" aria-label="关闭" onClick={close} disabled={busy}><Icon name="close"/></button><div className="modal-content">{children}</div></section></div>;
}
export function Card({ title, children, right, id, bodyClass='' }: { title: string; children: ReactNode; right?: ReactNode; id?: string; bodyClass?: string }) {
 return <section className="card" id={id} tabIndex={-1} aria-label={title}><div className="card-header"><div className="section-title"><h2>{title}</h2></div>{right}</div><div className={`card-body ${bodyClass}`}>{children}</div></section>;
}
export function TextLinks({ text }: { text: string }) {
 return <div className="answer-text">{text.split(/(https:\/\/[^\s<>]+)/g).map((part, i) => /^https:\/\//.test(part) ? <a key={i} href={part} target="_blank" rel="noreferrer">{part} <Icon name="external" size={13}/></a> : part)}</div>;
}
export function time(value: string | null) { return value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "—"; }
export function statusLabel(status: string) { return ({ draft: "草稿", published: "已发布", archived: "已归档", PASS: "已通过", REVISION_REQUIRED: "退回修改", ASSIGNED: "待审核", IN_REVIEW: "审核中", FINALIZED: "已审核" } as Record<string, string>)[status] ?? status; }
