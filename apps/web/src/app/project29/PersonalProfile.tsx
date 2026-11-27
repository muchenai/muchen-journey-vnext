import { ProfileExchange } from "./ProfileExchange";
import { useCallback, useEffect, useRef, useState } from "react";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { LearnerBack } from "./LearnerBack";
import { AcademyFavoritesPreview } from "./AcademyLearning";
import { pointNames } from "./VillageTaskCard";
import { GrowthHistoryDialog } from "./GrowthHistoryDialog";
import { formatGrowthCount, profileGrowthLevel, type ProfileWallet } from "./profileGrowth";
import { parseProfileCollection, type ProfileCollection } from "./profileBadges";
import { ProfileBadgeWall } from "./ProfileBadgeWall";
import type { Badge } from "./badgeEconomy";
import "./personalProfile.css";

export type { ProfileWallet } from "./profileGrowth";
export function ExplorationProfile({ name, onBack }: { name: string; onBack: () => void }) {
  return <div className="personal-profile">
    <div className="module-page-heading"><h1>个人主页</h1><LearnerBack onClick={onBack}>返回上一页</LearnerBack></div>
    <ModulePanel className="profile-overview">
      <div className="profile-identity">
        <div className="profile-avatar" aria-hidden="true">{Array.from(name)[0]}</div>
        <div className="profile-name"><h2>{name}</h2><p>当前学习阶段：探索营。毕业后，请使用公司飞书账号和毕业码迁移学习记录。</p></div>
      </div>
    </ModulePanel>
  </div>;
}

export function PersonalProfile({name,onBack,onAcademy,onAcademyFavorites,onBadgeShop,onBadgeCatalog,onBadgeOwned}:{name:string;onBack:()=>void;onAcademy:()=>void;onAcademyFavorites:()=>void;onBadgeShop:()=>void;onBadgeCatalog:()=>void;onBadgeOwned:()=>void}){
  const [collection,setCollection]=useState<ProfileCollection|null>(null);
  const [error,setError]=useState("");
  const pending=useRef<AbortController|null>(null);
  const refresh=useCallback(()=>{
    if(pending.current)return;
    const controller=new AbortController();
    pending.current=controller;
    setError("");
    void fetch("/api/learner/medals",{credentials:"same-origin",cache:"no-store",signal:controller.signal}).then(async response=>{
      const data=await response.json();if(!response.ok)throw Error(data.error||"成长数据读取失败，请重试。");
      const next=parseProfileCollection(data);
      if(!controller.signal.aborted)setCollection(next);
    }).catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"成长数据读取失败，请重试。")})
      .finally(()=>{if(pending.current===controller)pending.current=null;});
  },[]);
  useEffect(()=>{
    const initial=window.setTimeout(refresh,0);
    const check=()=>{if(!document.hidden)refresh();};
    const timer=window.setInterval(check,30000);
    window.addEventListener("focus",check);
    document.addEventListener("visibilitychange",check);
    return()=>{window.clearTimeout(initial);pending.current?.abort();pending.current=null;window.clearInterval(timer);window.removeEventListener("focus",check);document.removeEventListener("visibilitychange",check);};
  },[refresh]);
  function applyWallet(wallet: ProfileWallet) {
    pending.current?.abort();
    pending.current = null;
    setCollection(current => current ? { ...current, wallet } : current);
    refresh();
  }
  return <PersonalProfileView name={name} wallet={collection?.wallet??null} badges={collection?.badges??null} error={error} onExchanged={applyWallet} onRetry={refresh} onBack={onBack} onAcademy={onAcademy} onAcademyFavorites={onAcademyFavorites} onBadgeShop={onBadgeShop} onBadgeCatalog={onBadgeCatalog} onBadgeOwned={onBadgeOwned}/>;
}

export function PersonalProfileView({name,wallet,badges,error,onRetry,onExchanged,onBack,onAcademy,onAcademyFavorites,onBadgeShop,onBadgeCatalog,onBadgeOwned}:{name:string;wallet:ProfileWallet|null;badges:Badge[]|null;error:string;onRetry:()=>void;onExchanged:(wallet:ProfileWallet)=>void;onBack:()=>void;onAcademy:()=>void;onAcademyFavorites:()=>void;onBadgeShop:()=>void;onBadgeCatalog:()=>void;onBadgeOwned:()=>void}){
  const [showGrowth,setShowGrowth]=useState(false);
  const xp=formatGrowthCount(wallet?.xp);
  const growth=profileGrowthLevel(wallet?.xp);
  const levelLabel=growth?`Lv.${growth.level} · ${growth.title}`:"成长等级 · —";
  return <div className="personal-profile">
    <div className="module-page-heading"><div><h1>个人主页</h1><p>记录每一次探索，珍藏每一份成长。</p></div><button data-page-navigation className="module-secondary" onClick={onBack}>返回上一页 →</button></div>
    {error?<p role="alert">{error}{wallet&&" 当前显示上次读取的数据。"} <button className="module-secondary" onClick={onRetry}>重新加载</button></p>:!wallet&&<p role="status">正在读取成长数据…</p>}
    <ModulePanel className="profile-overview">
      <div className="profile-identity"><div className="profile-avatar" aria-hidden="true">{Array.from(name||"学员")[0]}</div><div className="profile-name"><span className="badge-eyebrow">MY GROWTH SPACE</span><h2>{name||"学员"}</h2><div className="profile-identity-tags"><span className="module-tag">{levelLabel}</span></div><p>让每一份努力，成为看得见的成长印记。</p></div></div>
      <div className="profile-summary"><div><strong>{formatGrowthCount(wallet?.ownedMedalCount)} <small>枚</small></strong><span>已拥有徽章</span></div><div><strong>{xp}</strong><span>累计成长经验</span></div><div><strong>{formatGrowthCount(wallet?.mallPoints)}</strong><span>{wallet?.mallPoints === undefined ? "商城积分 · 暂未开放" : "商城积分"}</span></div></div>
      <div className="profile-featured"><ModuleIcon file="a03b5" pack="guild" size={48}/><div><span className="badge-eyebrow">展示徽章</span><h3>暂未开放</h3></div></div>
    </ModulePanel>
    <div className="profile-experience-grid">
      <ModulePanel className="profile-experience"><div className="module-row"><div><span className="badge-eyebrow">EXPERIENCE & GROWTH</span><h2>我的经验与等级</h2></div><span className="module-tag">成长账户</span></div>
        <div className="profile-level-heading"><div className="profile-level-mark"><span>LEVEL</span><strong>{growth?.level??"—"}</strong></div><div><h3>{levelLabel}</h3><p>{growth?<>距离 Lv.{growth.nextLevel} 还需 <b>{formatGrowthCount(growth.remaining)} 经验</b></>:error?"等级数据读取失败，请重新加载。":"正在读取成长等级…"}</p></div><div className="profile-lifetime"><strong>{xp}</strong><span>累计成长经验</span></div></div>
        {growth?<><div className="profile-xp-labels"><span>Lv.{growth.level}</span><span>{growth.progress} / {growth.step} XP</span><span>Lv.{growth.nextLevel}</span></div><progress className="profile-xp-track" value={growth.progress} max={growth.step} aria-label="成长等级进度" aria-valuetext={`Lv.${growth.level}，${growth.progress} / ${growth.step} XP，距离 Lv.${growth.nextLevel} 还需 ${growth.remaining} 经验`}/></>:<><div className="profile-xp-labels"><span>等级进度待读取</span></div><div className="profile-xp-track" aria-hidden="true"/></>}
        <div className="profile-xp-balances"><div><span>可兑换经验</span><strong>{formatGrowthCount(wallet?.availableXp)} <small>XP</small></strong></div><div><span>已用于兑换</span><strong>{formatGrowthCount(wallet?.redeemedXp)} <small>XP</small></strong></div><p>累计经验决定等级。<br/>{wallet?.mallPoints === undefined ? "经验兑换暂未开放。" : "可兑换经验用于兑换商城积分。"}</p></div>
        <p className="profile-xp-rule">每累计 500 XP 升一级，经验可通过学习、完成任务和线下培训获得。</p>
        <div className="profile-growth-actions"><span>每一份成长，都有记录可查。</span><button className="module-secondary" onClick={()=>{onRetry();setShowGrowth(true);}}>查看成长明细 →</button></div>
      </ModulePanel>
      <ProfileExchange wallet={wallet} onExchanged={onExchanged} refresh={onRetry} showHistory={()=>{onRetry();setShowGrowth(true);}}/>
    </div>
    <AcademyFavoritesPreview onBrowse={onAcademy} onViewAll={onAcademyFavorites}/>
    <div className="profile-content-grid"><section><ProfileBadgeWall badges={badges} error={error} onRetry={onRetry} onShop={onBadgeShop} onOwned={onBadgeOwned}/><ModulePanel className="profile-next"><div className="profile-next-icon"><ModuleIcon file="d7bdc" size={28}/></div><div><h3>下一枚徽章，会属于怎样的你？</h3><p>从真实任务中积累经验，找到下一个成长目标。</p></div><button data-page-navigation className="module-secondary" onClick={onBadgeCatalog}>发现更多徽章 →</button></ModulePanel></section>
      <aside className="profile-aside"><ModulePanel className="profile-capabilities"><span className="badge-eyebrow">MY EXPLORATION</span><h3>能力足迹</h3><p>暂未开放</p></ModulePanel><ModulePanel className="profile-wallet"><div className="module-row"><h3>成长补给站</h3><ModuleIcon file="a03b5" pack="guild" size={24}/></div>{wallet?Object.entries(pointNames).map(([id,label])=><div className="module-badge-allocation" key={id}><span>{label}徽章点</span><span>{wallet.badgeBalances[id]??0} 点</span></div>):<p>{error?"数据读取失败":"正在读取徽章点…"}</p>}<p>完成任务并通过审核后，获得对应类型的徽章点。</p><button data-page-navigation className="module-secondary" onClick={onBadgeShop}>去兑换徽章 →</button></ModulePanel></aside>
    </div>
    {showGrowth&&<GrowthHistoryDialog onClose={()=>setShowGrowth(false)} onRefreshSummary={onRetry}/>}
  </div>;
}
