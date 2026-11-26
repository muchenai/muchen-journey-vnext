"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GrowthHistoryDialog } from "./GrowthHistoryDialog";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { formatGrowthCount, parseProfileWallet, type ProfileWallet } from "./profileGrowth";
import "./personalProfile.css";

export function AcademyAccount({ name, close, openProfile }: {
  name: string; close: () => void; openProfile: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const pending = useRef<AbortController | null>(null);
  const [wallet, setWallet] = useState<ProfileWallet | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState(false);

  const refresh = useCallback(async () => {
    pending.current?.abort();
    const request = new AbortController();
    pending.current = request;
    try {
      const response = await fetch("/api/learner/medals", {
        credentials: "same-origin", cache: "no-store", signal: request.signal,
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.error || "成长账户暂时无法读取。");
      const currentWallet = parseProfileWallet(result.wallet);
      if (!request.signal.aborted) {
        setWallet(currentWallet);
        setError("");
      }
    } catch (failure) {
      if (!request.signal.aborted) {
        setWallet(null);
        setError(failure instanceof Error ? failure.message : "读取失败，请重试。");
      }
    }
  }, []);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    const load = window.setTimeout(refresh, 0);
    return () => {
      window.clearTimeout(load);
      pending.current?.abort();
      element?.close();
    };
  }, [refresh]);

  return <dialog ref={dialog} className="module-dialog journey-dialog" aria-labelledby="academy-account-title"
    onCancel={event => { if (event.target === dialog.current) close(); }}>
    <JourneyDialogSurface>
      <div className="module-dialog-heading"><h2 id="academy-account-title">{name}的成长账户</h2>
        <button type="button" onClick={close}>关闭 ×</button></div>
      {wallet && <p>累计经验 {formatGrowthCount(wallet.xp)} · 可兑换经验 {formatGrowthCount(wallet.availableXp)}</p>}
      {error ? <p role="alert">{error} <button type="button" className="module-secondary" onClick={refresh}>重新读取</button></p>
        : wallet ? <ModulePanel className="profile-mall-points">
          <div className="module-row"><div><span className="badge-eyebrow">MUCHEN REWARDS</span><h3>沐晨商城积分</h3></div>
            <ModuleIcon file="d7bdc" size={28} /></div>
          <div className="profile-mall-number"><strong>—</strong><span>暂未开放</span></div>
          <button type="button" className="profile-exchange-history" onClick={() => setHistory(true)}>查看成长与兑换记录</button>
          <button type="button" className="profile-exchange-history" onClick={openProfile}>查看个人主页</button>
        </ModulePanel> : <p role="status">正在读取成长账户…</p>}
    </JourneyDialogSurface>
    {history && <GrowthHistoryDialog onClose={() => setHistory(false)} onRefreshSummary={refresh} />}
  </dialog>;
}
