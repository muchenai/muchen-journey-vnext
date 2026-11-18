"use client";

import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import { TREASURE_CATALOG, type ExplorationTreasureDrop, type ExplorationTreasures } from "@/lib/exploration-treasures";
import "./explorationTreasureExperience.css";

type TreasureId = ExplorationTreasureDrop["treasureId"];
type Reveal = { drop: ExplorationTreasureDrop | null; preview: boolean; stage: "sealed" | "opening" | "revealed" };
const dateLabel = (value: string) => Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "时间未记录";

export function TreasureGlyph({ kind, className = "" }: { kind: TreasureId; className?: string }) {
  return <svg className={`treasure-glyph ${className}`} viewBox="0 0 120 120" fill="none" aria-hidden="true">
    <circle cx="60" cy="60" r="48" stroke="currentColor" strokeOpacity=".12" />
    <circle cx="60" cy="60" r="40" stroke="currentColor" strokeOpacity=".24" strokeDasharray="2 7" />
    {kind === "compass" ? <>
      <circle cx="60" cy="60" r="31" stroke="currentColor" strokeWidth="2" /><circle cx="60" cy="60" r="25" stroke="currentColor" strokeOpacity=".35" />
      <path d="m60 20 7 33 33 7-33 7-7 33-7-33-33-7 33-7 7-33Z" fill="currentColor" fillOpacity=".14" stroke="currentColor" strokeWidth="1.5" />
      <path d="m60 37 7 23-7 23-7-23 7-23Z" fill="currentColor" /><path d="m37 60 23-7 23 7-23 7-23-7Z" fill="currentColor" fillOpacity=".7" /><circle cx="60" cy="60" r="4" fill="#ecffff" />
    </> : kind === "crystal" ? <>
      <path d="m60 17 24 24 4 35-28 28-28-28 4-35 24-24Z" fill="currentColor" fillOpacity=".15" stroke="currentColor" strokeWidth="1.8" />
      <path d="m60 17-12 37 12 50 12-50-12-37Zm-24 24 12 13-16 22m52-35L72 54l16 22M48 54h24M32 76l28-8 28 8" stroke="currentColor" strokeWidth="1.3" />
      <path d="m60 17 12 37-12 14-12-14 12-37Z" fill="currentColor" fillOpacity=".5" /><path d="m60 26 5 25-5 7-5-7 5-25Z" fill="#f8efff" fillOpacity=".65" />
      <path d="m24 28 2 5 5 2-5 2-2 5-2-5-5-2 5-2 2-5Zm70 55 2 4 4 2-4 2-2 4-2-4-4-2 4-2 2-4Z" fill="currentColor" />
    </> : kind === "starmap" ? <>
      <path d="m24 37 24-11 24 11 24-11v58L72 95 48 84 24 95V37Z" fill="currentColor" fillOpacity=".12" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M48 26v58m24-47v58" stroke="currentColor" strokeOpacity=".4" /><path d="m35 65 22-18 14 22 14-18" stroke="currentColor" strokeWidth="1.3" strokeDasharray="3 3" />
      <circle cx="35" cy="65" r="3" fill="currentColor" /><circle cx="57" cy="47" r="4" fill="#d3efff" /><circle cx="71" cy="69" r="3" fill="currentColor" />
      <path d="m85 39 2 9 9 3-9 2-2 10-3-10-9-2 9-3 3-9Z" fill="currentColor" /><circle cx="57" cy="47" r="9" stroke="currentColor" strokeOpacity=".4" />
    </> : <>
      <path d="M65 56 39 82l-8 1-8 14 14-2 3-8 7-1 27-27" fill="currentColor" fillOpacity=".25" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="77" cy="40" r="23" fill="currentColor" fillOpacity=".13" stroke="currentColor" strokeWidth="2" /><circle cx="77" cy="40" r="14" stroke="currentColor" strokeOpacity=".65" />
      <path d="m77 29 3 8 8 3-8 3-3 8-3-8-8-3 8-3 3-8Z" fill="currentColor" /><path d="m49 72 7 7m-14-1 6 6" stroke="currentColor" strokeWidth="3" />
      <path d="m29 30 2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6Z" fill="currentColor" fillOpacity=".6" />
    </>}
  </svg>;
}

function TreasureChest({ stage }: { stage: Reveal["stage"] }) {
  const gradient = useId();
  return <div className="treasure-chest-scene" data-stage={stage} aria-hidden="true">
    <div className="treasure-chest-halo" /><div className="treasure-chest-orbit" /><div className="treasure-chest-rays" />
    <svg className="treasure-chest" viewBox="0 0 320 255" fill="none">
      <defs><linearGradient id={gradient} x1="70" y1="110" x2="240" y2="225" gradientUnits="userSpaceOnUse"><stop stopColor="#294779" /><stop offset=".5" stopColor="#132b50" /><stop offset="1" stopColor="#07172f" /></linearGradient></defs>
      <ellipse cx="160" cy="226" rx="108" ry="14" fill="#02091c" fillOpacity=".55" /><ellipse cx="160" cy="226" rx="99" ry="10" stroke="#5be5ff" strokeOpacity=".3" />
      <path d="m69 136 91-27 92 27v65l-92 27-91-27v-65Z" fill={`url(#${gradient})`} stroke="#709fd1" strokeWidth="1.6" />
      <path d="m160 163 92-27v65l-92 27v-65Z" fill="#071a34" fillOpacity=".75" /><path d="m69 136 91 27 92-27M160 163v65" stroke="#70c9ef" strokeOpacity=".5" />
      <path d="m81 153 67 20v40l-67-20v-40Zm91 20 67-20v40l-67 20v-40Z" stroke="#3f6494" strokeWidth="1.5" />
      <path d="m103 146 10 3v62l-10-3v-62Zm104 3 10-3v62l-10 3v-62Z" fill="#e0b773" fillOpacity=".8" />
      <g className="treasure-chest-lid">
        <path d="m69 136 11-37 80-24 81 24 11 37-92 28-91-28Z" fill={`url(#${gradient})`} stroke="#a9c6e6" strokeWidth="1.8" />
        <path d="m80 99 80 25 81-25M160 124v40" stroke="#7ba7d1" /><path d="m82 109 78 24 79-24" stroke="#f6d08b" strokeWidth="4" />
        <path d="m112 89 10-3 1 59-10-3-1-53Zm87-3 10 3-1 53-10 3 1-59Z" fill="#dcb879" />
        <path d="m160 87 27 9-27 9-26-9 26-9Z" fill="#9defff" fillOpacity=".15" stroke="#69dbf4" /><path d="m160 92 13 4-13 4-13-4 13-4Z" fill="#a0f3ff" />
      </g>
      <path d="m160 151 15 5v25l-15 12-15-12v-25l15-5Z" fill="#0d2a46" stroke="#f3d096" strokeWidth="2" /><path d="m160 158 7 10-7 11-7-11 7-10Z" fill="#82edff" />
    </svg>
    {Array.from({ length: 10 }, (_, index) => <i key={index} className="treasure-spark" style={{ "--spark-index": index, "--spark-y": `${24 + index % 3 * 14}%` } as CSSProperties} />)}
  </div>;
}

export function ExplorationTreasureExperience({ treasures, collectionOpen, onCollectionClose, canReveal = true, busy = false, onAcknowledge, onUnlockGraduation, presentedDrop, onDropSettled }: {
  treasures: ExplorationTreasures;
  collectionOpen: boolean;
  onCollectionClose: () => void;
  canReveal?: boolean;
  busy?: boolean;
  onAcknowledge: (id: string) => Promise<boolean>;
  onUnlockGraduation?: () => Promise<boolean>;
  presentedDrop?: ExplorationTreasureDrop | null;
  onDropSettled?: (id: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const focusBeforeOpen = useRef<HTMLElement | null>(null);
  const acknowledged = useRef(new Set<string>());
  const deferredDrops = useRef(new Set<string>());
  const acknowledging = useRef(false);
  const mounted = useRef(true);
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const [selectedId, setSelectedId] = useState<TreasureId | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [unlocking, setUnlocking] = useState(false);
  const [graduationError, setGraduationError] = useState("");
  const [copied, setCopied] = useState(false);
  const unlockingRef = useRef(false);
  const graduation = treasures.graduation;
  const ownedCount = new Set(treasures.items.filter(drop => TREASURE_CATALOG.some(item => item.id === drop.treasureId)).map(drop => drop.treasureId)).size;
  const graduationReady = graduation?.status === "READY" && !!graduation.code;
  const graduationMigrated = graduation?.status === "MIGRATED";
  const graduationFormalAccount = graduation?.status === "NOT_REQUIRED";
  const graduationAccountMessage = graduationMigrated ? "历史数据已迁移至公司飞书账号。" : "当前为公司飞书账号，无需使用毕业码。";
  const canUnlockGraduation = ownedCount === 4 && graduation?.status === "AVAILABLE" && !!onUnlockGraduation;
  const mode = reveal ? "reveal" : collectionOpen ? "collection" : null;
  const selected = treasures.items.find(item => item.treasureId === selectedId);
  const selectedTreasure = TREASURE_CATALOG.find(item => item.id === selectedId);
  const revealedTreasure = TREASURE_CATALOG.find(item => item.id === (reveal?.drop?.treasureId ?? "compass")) ?? TREASURE_CATALOG[0];

  useEffect(() => {
    if (!canReveal || busy || collectionOpen || reveal) return;
    const candidates = presentedDrop === undefined ? treasures.pendingDrops : presentedDrop ? [presentedDrop] : [];
    const next = candidates.find(drop => !acknowledged.current.has(drop.id) && !deferredDrops.current.has(drop.id));
    if (next) { setError(""); setReveal({ drop: next, preview: false, stage: "sealed" }); }
  }, [treasures.pendingDrops, collectionOpen, canReveal, busy, reveal, presentedDrop]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    const element = dialog.current;
    if (mode && element && !element.open) {
      focusBeforeOpen.current = document.activeElement as HTMLElement | null;
      element.showModal();
    } else if (!mode && element?.open) { element.close(); focusBeforeOpen.current?.focus(); }
    if (mode) element?.querySelector<HTMLButtonElement>(".treasure-primary")?.focus();
  }, [mode]);
  useEffect(() => () => { dialog.current?.close(); focusBeforeOpen.current?.focus(); }, []);
  useEffect(() => {
    if (reveal?.stage !== "opening") return;
    const timer = window.setTimeout(() => setReveal(previous => previous ? { ...previous, stage: "revealed" } : null), 650);
    return () => window.clearTimeout(timer);
  }, [reveal?.stage]);

  function openChest() {
    if (!reveal || reveal.stage !== "sealed" || busy || saving) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setReveal({ ...reveal, stage: reduced ? "revealed" : "opening" });
  }
  async function close() {
    if (acknowledging.current || unlockingRef.current || busy) return;
    if (!reveal) { onCollectionClose(); return; }
    if (reveal.preview) { setReveal(null); setError(""); return; }
    if (!reveal.drop) return;
    const id = reveal.drop.id;
    if (acknowledged.current.has(id) || deferredDrops.current.has(id)) return;
    acknowledging.current = true; setSaving(true); setError("");
    try {
      const saved = await onAcknowledge(id);
      if (!mounted.current) return;
      if (!saved) { setError("宝藏已保留，暂未确认领取结果。请重试收下宝藏。"); return; }
      acknowledged.current.add(id);
      setReveal(null);
      onDropSettled?.(id);
    } catch { if (mounted.current) setError("宝藏已保留，暂时无法保存查看状态，请重试。"); }
    finally { acknowledging.current = false; if (mounted.current) setSaving(false); }
  }
  async function unlockGraduation() {
    if (!canUnlockGraduation || !onUnlockGraduation || busy || unlockingRef.current) return;
    unlockingRef.current = true; setUnlocking(true); setGraduationError("");
    try {
      if (!await onUnlockGraduation()) setGraduationError("暂时未能解锁毕业码，宝藏进度已保留，请重试。");
    } catch { setGraduationError("毕业码解锁失败，请重试。"); }
    finally { unlockingRef.current = false; setUnlocking(false); }
  }
  async function copyGraduationCode() {
    if (!graduationReady || !graduation?.code) return;
    setGraduationError(""); setCopied(false);
    try { await navigator.clipboard.writeText(graduation.code); setCopied(true); }
    catch { setGraduationError("复制失败，请选中毕业码手动复制。"); }
  }
  return <dialog ref={dialog} className="exploration-treasure-dialog" data-mode={mode ?? "closed"}
    aria-labelledby="exploration-treasure-title" onCancel={event => { event.preventDefault(); void close(); }}
    onClick={event => {
      if (event.target !== event.currentTarget) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) void close();
    }}>
    <div className="treasure-dialog-stars" aria-hidden="true" />
    <div className="treasure-dialog-body">
      <button type="button" className="treasure-close" aria-label="关闭宝藏窗口" disabled={saving || unlocking || busy} onClick={() => void close()}><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.5" /></svg></button>
      {reveal ? <section className="treasure-discovery" data-stage={reveal.stage} data-treasure={revealedTreasure.id}>
        <p className="treasure-eyebrow">{reveal.preview ? "效果预览 · 不计入收集" : "EXPLORATION · NEW DISCOVERY"}</p>
        <h2 id="exploration-treasure-title">{reveal.stage === "revealed" ? "发现一件探索宝藏" : "你的探索，有了意外收获"}</h2>
        <p className="treasure-discovery-intro">{reveal.stage === "revealed" ? "每一步认真探索，都在点亮你的成长星图。" : reveal.preview ? "打开宝箱，看看下一次相遇会是什么模样。" : "任务已完成，一份神秘的宝藏正在等待你开启。"}</p>
        <div className="treasure-reveal-art">
          <TreasureChest stage={reveal.stage} />
          {reveal.stage === "revealed" && <div className="treasure-revealed-object"><TreasureGlyph kind={revealedTreasure.id} /><span>探索收藏 · {String(TREASURE_CATALOG.indexOf(revealedTreasure) + 1).padStart(2, "0")}</span></div>}
        </div>
        {reveal.stage === "revealed" ? <><h3>{revealedTreasure.name}</h3><p className="treasure-reveal-subtitle">{revealedTreasure.subtitle}</p><p className="treasure-reveal-description">{revealedTreasure.description}</p>
          {!reveal.preview && <p className="treasure-source">来自任务 · {reveal.drop?.taskTitle}</p>}
          <div className="treasure-reveal-progress"><span>探索宝藏</span><strong>{treasures.count}<small> / 4</small></strong><span>{reveal.preview ? "当前收集进度" : treasures.count === 4 ? "已集齐，新的远航即将开始" : "每件宝藏，都有自己的故事"}</span></div>
          <button type="button" className="treasure-primary" disabled={saving || busy} onClick={() => void close()}>{saving ? "正在收好宝藏…" : reveal.preview ? "返回宝藏收藏" : "收下宝藏"}<span aria-hidden="true">→</span></button>
        </> : <button type="button" className="treasure-primary" disabled={saving || busy || reveal.stage === "opening"} onClick={openChest}>{reveal.stage === "opening" ? "宝藏正在苏醒…" : "开启宝藏"}<span aria-hidden="true">✦</span></button>}
        {error && <p className="treasure-error" role="alert">{error}</p>}
        {error && reveal.stage !== "revealed" && <button type="button" className="treasure-text-button" disabled={saving || busy} onClick={() => void close()}>重试保存查看状态</button>}
        {error && <button type="button" className="treasure-text-button" disabled={saving || busy} onClick={() => {
          if (!reveal.drop || acknowledging.current || deferredDrops.current.has(reveal.drop.id)) return;
          deferredDrops.current.add(reveal.drop.id);
          setError(""); setReveal(null);
          onDropSettled?.(reveal.drop.id);
        }}>稍后查看</button>}
        <p className="treasure-discovery-footnote">{reveal.preview ? "仅预览开启效果，不会获得宝藏或改变任务进度。" : "宝藏已为你保留，关闭窗口也不会丢失。"}</p>
      </section> : <section className="treasure-collection">
        <header className="treasure-collection-heading"><p className="treasure-eyebrow">EXPLORATION COLLECTION</p><h2 id="exploration-treasure-title">你的探索，值得珍藏</h2><p>完成任务，遇见藏在成长路上的小小惊喜。</p></header>
        <div className="treasure-collection-progress"><div><span>已探索宝藏</span><strong>{treasures.count}<small> / 4</small></strong></div><div className="treasure-collection-meter"><div className="treasure-meter-segments" aria-label={`已探索 ${treasures.count} 个宝藏，共 4 个`}>{TREASURE_CATALOG.map((item, index) => <i key={item.id} data-active={index < treasures.count} />)}</div><p>{treasures.count === 4 ? "四件宝藏已集齐，愿你带着收获继续远航。" : "四件独一无二的宝藏，等待与你相遇。"}</p></div></div>
        <div className="treasure-collection-grid">{TREASURE_CATALOG.map((item, index) => {
          const drop = treasures.items.find(discovery => discovery.treasureId === item.id);
          return <button type="button" className="treasure-collection-item" data-treasure={item.id} data-owned={!!drop} data-selected={selectedId === item.id} key={item.id} disabled={!drop} aria-label={drop ? `查看${item.name}` : `${item.name}，等待探索`} onClick={() => setSelectedId(item.id)}>
            <div className="treasure-item-top"><span>0{index + 1}</span><span>{drop ? "已探索" : "待探索"}</span></div><div className="treasure-item-art"><TreasureGlyph kind={item.id} />{!drop && <svg className="treasure-item-lock" viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="5" y="9" width="10" height="8" rx="2" stroke="currentColor" /><path d="M7 9V6a3 3 0 0 1 6 0v3" stroke="currentColor" /></svg>}</div>
            <h3>{item.name}</h3><p>{drop ? item.subtitle : "下一次完成，也许就会相遇"}</p><span className="treasure-item-bottom">{drop ? "查看宝藏故事 ↗" : "等待被你点亮"}</span>
          </button>;
        })}</div>
        {selected && selectedTreasure && <section className="treasure-collection-detail" aria-label={`${selectedTreasure.name}的收藏记录`} data-treasure={selectedTreasure.id}><TreasureGlyph kind={selectedTreasure.id} /><div><h3>{selectedTreasure.name}<span>收藏手记</span></h3><p>{selectedTreasure.description}</p><small>来自任务 · {selected.taskTitle}</small><time dateTime={selected.discoveredAt}>{dateLabel(selected.discoveredAt)}</time></div></section>}
        <div className="treasure-drop-rules" aria-label="宝藏掉落规则"><div><strong>首尾任务必掉</strong><span>按后台排序，首次完成任务时结算</span></div><div><strong>中间任务随机掉落</strong><span>另外两件宝藏，随机藏在探索途中</span></div><div><strong>总共 4 件宝藏</strong><span>每个任务结算一次，宝藏不重复</span></div></div>
        <footer className="treasure-collection-footer">
          <div className="treasure-footer-info"><p>集齐 4 件后停止掉落，已获得的宝藏会一直保留。</p><button type="button" className="treasure-preview-button" disabled={unlocking || busy} onClick={() => { setError(""); setReveal({ drop: null, preview: true, stage: "sealed" }); }}>预览掉落效果 <span aria-hidden="true">↗</span></button></div>
          <div className="treasure-graduation" data-status={graduationMigrated || graduationFormalAccount ? graduation?.status : graduationReady ? "READY" : canUnlockGraduation ? "AVAILABLE" : "LOCKED"}>
            <div className="treasure-graduation-heading"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m3 8 9-4 9 4-9 4-9 4Zm4 2v6c3 3 7 3 10 0v-6M21 8v8" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg><strong>探索营毕业码</strong><span>{graduationMigrated ? "迁移完成" : graduationFormalAccount ? "正式账号" : graduationReady ? "已解锁" : canUnlockGraduation ? "待解锁" : "未解锁"}</span></div>
            {graduationMigrated || graduationFormalAccount ? <p className="treasure-graduation-hint">{graduationAccountMessage}</p> : graduationReady ? <><code className="treasure-graduation-code" aria-label="探索营毕业码" tabIndex={0}>{graduation?.code}</code><p className="treasure-graduation-hint">专属毕业码 · 请妥善保管</p><button type="button" className="treasure-graduation-copy" onClick={() => void copyGraduationCode()}>{copied ? "已复制" : "复制毕业码"}<span aria-hidden="true">↗</span></button><span className="treasure-graduation-feedback" role="status">{copied ? "毕业码已复制" : ""}</span></> : <><p className="treasure-graduation-hint" id="treasure-graduation-hint">{canUnlockGraduation ? "全部任务已完成，4 件宝藏已集齐，解锁你的专属毕业码。" : graduation?.blockReason || "完成全部任务并集齐 4 件宝藏后解锁。"}</p><button type="button" className="treasure-graduation-unlock" disabled={!canUnlockGraduation || busy || unlocking} aria-describedby="treasure-graduation-hint" aria-busy={unlocking} onClick={() => void unlockGraduation()}><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><rect x="4" y="8" width="12" height="9" rx="2" stroke="currentColor" strokeWidth="1.4" /><path d="M6.5 8V5.5a3.5 3.5 0 0 1 7 0V8m-3.5 4v2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>{unlocking ? "正在解锁…" : "解锁毕业码"}<span aria-hidden="true">→</span></button></>}
            {graduationError && <p className="treasure-graduation-error" role="alert">{graduationError}</p>}
          </div>
        </footer>
      </section>}
    </div>
  </dialog>;
}
