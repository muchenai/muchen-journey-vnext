import { useRef, useState, type FormEvent } from "react";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { formatGrowthCount, parseProfileWallet, XP_PER_MALL_POINT, type ProfileWallet } from "./profileGrowth";

export function ProfileExchange({ wallet, onExchanged, refresh, showHistory }: {
  wallet: ProfileWallet | null;
  onExchanged: (updated: ProfileWallet) => void;
  refresh: () => void;
  showHistory: () => void;
}) {
  const [amount, setAmount] = useState("1");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const pending = useRef(false);
  const requestKey = useRef("");
  const hasBalance = wallet?.mallPoints !== undefined;
  const enabled = hasBalance && wallet.mallExchangeAvailable === true;
  const maximum = Math.floor((wallet?.availableXp ?? 0) / XP_PER_MALL_POINT);
  const points = Number(amount);
  const valid = Number.isSafeInteger(points) && points > 0 && points <= maximum;

  async function exchange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled || !valid || pending.current) return;
    pending.current = true;
    setBusy(true);
    setMessage("");
    try {
      requestKey.current ||= crypto.randomUUID();
      const response = await fetch("/api/learner/experience", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "Idempotency-Key": requestKey.current },
        body: JSON.stringify({ points }),
      });
      const receipt = await response.json();
      if (!response.ok) throw new Error(receipt.error || "兑换失败，请重试。");
      const updated = parseProfileWallet(receipt.wallet);
      onExchanged(updated);
      requestKey.current = "";
      setAmount("");
      setMessage(`已兑换 ${formatGrowthCount(points)} 商城积分。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "兑换结果尚未确认，请重试。");
      refresh();
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  const exchangeControls = <>
    <label>兑换积分数<input type="number" min={1} max={maximum} step={1} value={amount}
      readOnly={!enabled} disabled={enabled && (busy || maximum === 0)}
      onChange={event => { setAmount(event.target.value); requestKey.current = ""; setMessage(""); }} /></label>
    <small>当前最多可兑换 {formatGrowthCount(maximum)} 积分</small>
    {enabled
      ? <button className="module-primary" disabled={busy || !valid}>{busy ? "正在兑换…" : valid ? `使用 ${formatGrowthCount(points * XP_PER_MALL_POINT)} 经验兑换 ${formatGrowthCount(points)} 积分` : "兑换商城积分"}</button>
      : <button type="button" className="module-primary" onClick={() => setMessage("暂未开放")}>经验兑换商城积分</button>}
  </>;
  return <ModulePanel className="profile-mall-points">
    <div className="module-row"><div><span className="badge-eyebrow">MUCHEN REWARDS</span><h3>沐晨商城积分</h3></div><ModuleIcon file="d7bdc" size={28}/></div>
    <div className="profile-mall-number"><strong>{formatGrowthCount(wallet?.mallPoints)}</strong><span>{hasBalance ? "积分余额" : wallet ? "暂未开放" : "积分余额待读取"}</span></div>
    {hasBalance && <>
      <div className="profile-exchange-rate"><span>兑换比例</span><b>{XP_PER_MALL_POINT} 经验 = 1 商城积分</b></div>
      {enabled ? <form onSubmit={exchange} className="xp-exchange-form">{exchangeControls}</form>
        : <div className="xp-exchange-form">{exchangeControls}</div>}
      <button className="profile-exchange-history" onClick={showHistory}>查看成长与兑换记录</button>
    </>}
    {message && <p role="status">{message}</p>}
  </ModulePanel>;
}
