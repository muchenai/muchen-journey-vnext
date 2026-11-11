import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { useEffect, useRef, useState, useCallback } from "react";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { badgeCostStatus, badgePointLabel, badgePointTypes, adaptMedals, type Badge, type MedalResponse } from "./badgeEconomy";
import "./badgeShop.css";
import { BadgeArtworkImage } from "./BadgeArtworkImage";
import { badgeArtworkFor, badgeGrades } from "./badgeArtwork";
import { BadgeCatalogGallery } from "./BadgeCatalogGallery";
import { badgeCatalogEntries } from "./badgeCatalog";
import { BadgePointBalances } from "./BadgePointBalances";

export function Medal({ badge, large = false, locked = false }: { badge: Badge; large?: boolean; locked?: boolean }) {
  const artwork = badgeArtworkFor(badge, locked);
  if (artwork) return <BadgeArtworkImage path={artwork.path} level={artwork.level} large={large} />;
  if (badge.image) return <div className={`badge-medal ${large ? "badge-medal-large" : ""}`} data-locked={locked || undefined}><img className="badge-published-image" src={badge.image} alt="" /></div>;
  return <div className={`badge-medal ${large ? "badge-medal-large" : ""}`} data-locked={locked || undefined} data-tone={badge.tone} aria-hidden="true">
    <div className="badge-medal-ribbons"><i /><i /></div>
    <div className="badge-medal-edge"><div className="badge-medal-face">
      <span className="badge-medal-stars">· · ·</span>
      <ModuleIcon file={badge.icon} pack="guild" size={large ? 58 : 36} />
      <span className="badge-medal-inscription">MUCHEN</span>
    </div></div>
  </div>;
}

export type BadgeTab = "catalog" | "shop" | "owned";

export function BadgeShop({ query, onTasks, initialTab = "shop" }: { query: string; onTasks: () => void; initialTab?: BadgeTab }) {
  const [data, setData] = useState<MedalResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const writing = useRef(false);
  const sequence = useRef(0);
  const refresh = useCallback(async () => {
    const ticket = ++sequence.current;
    try {
      const response = await fetch("/api/learner/medals", {cache:"no-store"});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "徽章读取失败，请重试。");
      if(ticket === sequence.current) {setData(result); setError("");}
    } catch(failure) { if(ticket === sequence.current) setError(failure instanceof Error ? failure.message : "徽章读取失败，请重试。"); }
  }, []);
  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const check = () => { if(!document.hidden && !writing.current) void refresh(); };
    const timer = window.setInterval(check, 30000);
    window.addEventListener("focus", check);
    return () => { window.clearTimeout(initial); ++sequence.current; window.clearInterval(timer); window.removeEventListener("focus", check); };
  }, [refresh]);
  const {badges, wallet} = adaptMedals(data || {medals:[], redemptions:[], wallet:{badgeBalances:{}}});
  const [tab, setTab] = useState<BadgeTab>(initialTab);
  const [category, setCategory] = useState("全部");
  const [sort, setSort] = useState("default");
  const [selected, setSelected] = useState<Badge | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [notice, setNotice] = useState("");
  const modal = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = modal.current;
    if (selected || showHistory) element?.showModal();
    else element?.close();
    return () => element?.close();
  }, [selected, showHistory]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const visible = badges.filter(badge =>
    (category === "全部" || badge.requirements.some(cost => cost.type === category)) &&
    (tab === "shop" ? badge.published : wallet.owned.includes(badge.id)) &&
    `${badge.name}${badge.category}${badge.description}`.includes(query.trim()),
  ).sort((a, b) => sort === "redeemable"
    ? Number(!wallet.owned.includes(b.id) && badgeCostStatus(wallet, b).affordable) -
      Number(!wallet.owned.includes(a.id) && badgeCostStatus(wallet, a).affordable)
    : 0);
  const currentSelection = selected && badges.find(b => b.id === selected.id);
  const selectedStatus = currentSelection ? badgeCostStatus(wallet, currentSelection) : null;
  const close = () => { setSelected(null); setShowHistory(false); };
  const redeem = async () => {
    if (!currentSelection || writing.current || wallet.owned.includes(currentSelection.id) || !badgeCostStatus(wallet, currentSelection).affordable || currentSelection.stock === 0 || !currentSelection.published) return;
    writing.current = true; ++sequence.current; setBusy(true); setError("");
    try {
      const response = await fetch("/api/learner/medals", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({medalId:currentSelection.id, revision:currentSelection.revision})});
      const result = await response.json();
      if(!response.ok) throw new Error(result.error || "兑换未完成，请重试。");
      close(); setNotice(result.alreadyRedeemed ? "这枚徽章已收藏，无需重复兑换。" : `兑换成功，「${currentSelection.name}」已加入你的徽章墙。`);
    } catch(failure) { setNotice(failure instanceof Error ? failure.message : "兑换未完成，请重试。"); }
    finally { await refresh(); writing.current=false; setBusy(false); }
  };
  if (!data) return <div className="badge-shop"><div className="module-page-heading"><h1>我的徽章</h1></div><ModulePanel className="badge-empty"><p role={error ? "alert" : "status"}>{error || "正在读取徽章和余额…"}</p>{error && <button onClick={() => void refresh()}>重新读取</button>}</ModulePanel></div>;


  return <div className="badge-shop">
    {error && <p role="alert">{error} <button onClick={() => void refresh()}>重新读取</button></p>}
    <div className="module-page-heading">
      <div><h1>我的徽章</h1><p>把努力铸成勋章，让成长闪闪发光。</p></div>
      <button className="module-secondary" onClick={() => setShowHistory(true)}><ModuleIcon file="eec40" />兑换记录</button>
    </div>

    <div className="badge-top-grid">
      <ModulePanel className="badge-intro">
        <div className="badge-intro-copy">
          <span className="badge-eyebrow">GROWTH DESERVES A MEDAL</span>
          <h2>每一份努力，<br />都值得被<span>看见。</span></h2>
          <p>完成任务，积累对应类型的徽章点。<br />按发布者设置的兑换条件，收藏属于你的成长印记。</p>
          <div className="badge-intro-path"><span>完成任务</span><i />审核通过<i /><span>获得对应徽章点</span><i /><span>兑换徽章</span></div>
        </div>
        <div className="badge-intro-art">
          <div className="badge-orbit badge-orbit-one" /><div className="badge-orbit badge-orbit-two" />
          <BadgeArtworkImage path="points/ai-evaluation/ai-evaluation-2" level={0} large />
          <span className="badge-art-caption">YOUR NEXT ACHIEVEMENT</span>
        </div>
      </ModulePanel>
      <ModulePanel className="badge-wallet">
        <div className="module-row"><span>我的徽章点</span><span className="module-tag">当前余额</span></div>
        <BadgePointBalances balances={wallet.balances} />
        <p>按类型分别累计，不能用其他类型补差。</p>
        <div className="badge-wallet-stats"><span>已拥有 <b>{wallet.owned.length}</b> 枚</span><span>累计已兑换 <b>{wallet.history.length}</b> 枚</span></div>
        <button className="module-secondary" onClick={onTasks}>去完成任务 <span aria-hidden="true">→</span></button>
      </ModulePanel>
    </div>

    <div className="badge-content-grid">
      <section className="badge-catalog" aria-label="徽章兑换">
        <div className="badge-tabs" role="group" aria-label="查看徽章">
          <button className={tab === "shop" ? "is-active" : ""} aria-pressed={tab === "shop"} onClick={() => setTab("shop")}>徽章商城 <span>{badges.filter(b => b.published).length}</span></button>
          <button className={tab === "owned" ? "is-active" : ""} aria-pressed={tab === "owned"} onClick={() => setTab("owned")}>已拥有徽章 <span>{wallet.owned.length}</span></button>
          <button className={tab === "catalog" ? "is-active" : ""} aria-pressed={tab === "catalog"} onClick={() => setTab("catalog")}>全部徽章 <span>{badgeCatalogEntries.length}</span></button>
          <span className="badge-tabs-note">你的成长，由你点亮</span>
        </div>
        {tab === "catalog" ? <BadgeCatalogGallery wallet={wallet} badges={badges} query={query} onPublication={setSelected} /> : <>
        <div className="badge-filter-row">
          <div className="badge-categories" role="group" aria-label="按所需徽章点类型筛选">
            {["全部", ...badgePointTypes].map(item =>
              <button key={item} className={category === item ? "is-active" : ""} aria-pressed={category === item} onClick={() => setCategory(item)}>{item === "全部" ? "全部" : `${item}徽章点`}</button>)}
          </div>
          <select aria-label="徽章排序" value={sort} onChange={event => setSort(event.target.value)}><option value="default">默认排序</option><option value="redeemable">可兑换优先</option></select>
        </div>
        <div className="badge-card-grid">
          {visible.map(badge => {
            const owned = wallet.owned.includes(badge.id);
            const status = badgeCostStatus(wallet, badge);
            const affordable = status.affordable && badge.stock !== 0 && badge.published;
            return <ModulePanel key={badge.id} className={`badge-card ${owned ? "badge-card-owned" : ""}`}>
              <div className="badge-card-art" data-tone={badge.tone}>
                <span className="badge-rarity">{badgeArtworkFor(badge) ? badgeGrades[badge.tone].label : badge.level}</span>
                {owned && <span className="badge-owned-label">已拥有</span>}
                <Medal badge={badge} locked={!wallet.owned.includes(badge.id)} />
                <span className="badge-card-index">MJ · {String(badges.indexOf(badge) + 1).padStart(2, "0")}</span>
              </div>
              <div className="badge-card-copy">
                <div className="module-row"><h3>{badge.name}</h3><span className="module-tag">{badge.category}</span></div>
                <p>{badge.description}</p>
                <div className="badge-card-bottom">
                  <div className="badge-price"><small>兑换所需</small>{status.details.map(cost => <span key={cost.type} data-insufficient={cost.missing > 0}>{badgePointLabel(cost.type)} <b>{cost.amount}</b></span>)}</div>
                  <button className={owned || !affordable ? "module-secondary" : "module-primary"} disabled={owned || !affordable} onClick={() => setSelected(badge)}>
                    {owned ? "已收藏" : !status.valid ? "配置待完善" : badge.stock === 0 ? "已兑完" : affordable ? "立即兑换" : "所需类型不足"}
                  </button>
                </div>
              </div>
            </ModulePanel>;
          })}
        </div>
        {!visible.length && <ModulePanel className="badge-empty"><h3>{tab === "owned" ? "这里还没有对应的徽章" : !badges.some(b => b.published) ? "暂无已上架徽章" : "没有找到对应的徽章"}</h3><p>{tab === "shop" && !badges.some(b => b.published) ? "管理员上架后，可在这里查看兑换条件并使用对应徽章点兑换。" : "试试其他分类，或通过顶部搜索框调整搜索词。"}</p><button className="module-secondary" onClick={() => { setCategory("全部"); setTab(tab === "shop" && !badges.some(b => b.published) ? "catalog" : "shop"); }}>{tab === "shop" && !badges.some(b => b.published) ? "查看全部徽章" : "浏览商城"}</button></ModulePanel>}
        </>}
      </section>

      <aside className="badge-aside">
        <ModulePanel className="badge-collection">
          <div className="module-row"><h3>我的徽章墙</h3><span>已拥有 {wallet.owned.length} 枚</span></div>
          <p>每一枚徽章，都是你的成长印记。</p>
          <div className="badge-mini-grid">{badges.map(badge =>
            <button key={badge.id} className={wallet.owned.includes(badge.id) ? "" : "is-locked"} aria-label={`${badge.name}，${wallet.owned.includes(badge.id) ? "已拥有" : "未拥有"}`} onClick={() => setSelected(badge)}>
              <Medal badge={badge} locked={!wallet.owned.includes(badge.id)} /><span>{badge.name}</span>
            </button>)}</div>
          <small>已收藏 {wallet.owned.length} 枚徽章，继续积累成长印记。</small>
          <button className="badge-collection-more" onClick={() => setTab("catalog")}>查看全部 {badgeCatalogEntries.length} 款徽章图鉴 <span>→</span></button>
        </ModulePanel>
        <ModulePanel className="badge-guide">
          <h3>如何获得徽章点？</h3>
          <ol><li><b>01</b><div><strong>选择任务，开始实践</strong><p>任务奖励仅包含经验值与对应类型的徽章点。</p></div></li><li><b>02</b><div><strong>提交成果，等待审核</strong><p>审核通过后，分别累计各类徽章点。</p></div></li><li><b>03</b><div><strong>满足指定类型，兑换徽章</strong><p>逐项满足发布者设置的类型和数量，不能混兑。</p></div></li></ol>
          <button onClick={onTasks}>前往任务大厅 <span aria-hidden="true">→</span></button>
        </ModulePanel>
      </aside>
    </div>
    <dialog ref={modal} className="module-dialog badge-dialog journey-dialog" aria-labelledby="badge-dialog-title" onCancel={close}>
    <JourneyDialogSurface>
      <div className="module-dialog-heading"><span className="badge-eyebrow">MY ACHIEVEMENTS</span><button onClick={close} aria-label="关闭徽章弹窗">关闭</button></div>
      <h2 id="badge-dialog-title">{showHistory ? "兑换记录" : selected && wallet.owned.includes(selected.id) ? "已拥有的成长印记" : "收藏新的成长印记"}</h2>
      {showHistory ? <div className="badge-history">
        {!wallet.history.length ? <p>暂无兑换记录。去发现你的下一枚徽章吧。</p> : wallet.history.map(item => <div key={item.id} className="module-row"><span>{item.name}<small>{new Date(item.at).toLocaleString("zh-CN")} · 兑换成功</small></span><strong>{item.costs.map(cost => <span key={cost.type}>−{cost.amount} {badgePointLabel(cost.type)}</span>)}</strong></div>)}
      </div> : selected && <>
        <div className="badge-dialog-medal"><Medal badge={currentSelection || selected} large locked={!wallet.owned.includes(selected.id)} /></div>
        <h3>{selected.name}</h3><p>{selected.description}</p>
        {wallet.owned.includes(selected.id) ? <p className="badge-dialog-owned">这枚徽章已在你的徽章墙中，无需重复兑换。</p> : <>
          <div className="badge-type-confirm"><div className="badge-type-confirm-heading"><span>指定徽章点</span><span>所需</span><span>余额</span><span>兑换后 / 缺口</span></div>{selectedStatus?.details.map(cost => <div key={cost.type} data-insufficient={cost.missing > 0}><span>{badgePointLabel(cost.type)}</span><b>{cost.amount}</b><span>{cost.available}</span><strong>{cost.missing ? `还差 ${cost.missing}` : cost.available - cost.amount}</strong></div>)}</div>
          <p className="badge-dialog-note">须同时满足发布者配置的所有类型与数量。其他徽章点、经验和商城积分均不能代替。</p>
          <button className="module-primary badge-confirm-button" disabled={!selectedStatus?.affordable || !currentSelection?.published || currentSelection?.stock === 0 || busy} onClick={redeem}>{busy ? "兑换中…" : !currentSelection?.published ? "徽章已下架" : currentSelection.stock === 0 ? "徽章已兑完" : !selectedStatus?.valid ? "兑换配置待完善" : !selectedStatus.affordable ? "指定类型徽章点不足" : "确认兑换"}</button>
          <p className="badge-dialog-note">确认后扣除对应类型的徽章点，每枚徽章仅需兑换一次。</p>
        </>}
      </>}
        </JourneyDialogSurface>
  </dialog>
    {notice && <div className="module-toast" role="status">{notice}</div>}
  </div>;
}
