import { useEffect, useState } from "react";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { FavoriteKnowledge } from "./FavoriteKnowledge";
import { pointNames } from "./VillageTaskCard";
import "./personalProfile.css";

export type ProfileWallet={xp:number;badgeBalances:Record<string,number>};
export function PersonalProfile({name,onBack,onAcademy}:{name:string;onBack:()=>void;onAcademy:()=>void}){
  const [wallet,setWallet]=useState<ProfileWallet|null>(null);
  const [error,setError]=useState("");
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    void fetch("/api/learner/profile",{cache:"no-store",signal:controller.signal}).then(async response=>{
      const data=await response.json();if(!response.ok)throw Error(data.error||"成长数据读取失败，请重试。");
      if(!controller.signal.aborted)setWallet(data);
    }).catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"成长数据读取失败，请重试。")});
    return()=>controller.abort();
  },[attempt]);
  return <PersonalProfileView name={name} wallet={wallet} error={error} onRetry={()=>{setError("");setWallet(null);setAttempt(n=>n+1)}} onBack={onBack} onAcademy={onAcademy}/>;
}

export function PersonalProfileView({name,wallet,error,onRetry,onBack,onAcademy}:{name:string;wallet:ProfileWallet|null;error:string;onRetry:()=>void;onBack:()=>void;onAcademy:()=>void}){
  const [notice,setNotice]=useState("");
  const unavailable=()=>setNotice("暂未开放");
  const xp=wallet?wallet.xp.toLocaleString():"—";
  return <div className="personal-profile">
    <div className="module-page-heading"><div><h1>个人主页</h1><p>记录每一次探索，珍藏每一份成长。</p></div><button data-page-navigation className="module-secondary" onClick={onBack}>返回上一页 →</button></div>
    {error?<p role="alert">{error} <button className="module-secondary" onClick={onRetry}>重新加载</button></p>:!wallet&&<p role="status">正在读取成长数据…</p>}
    <ModulePanel className="profile-overview">
      <div className="profile-identity"><div className="profile-avatar" aria-hidden="true">{Array.from(name||"学员")[0]}</div><div className="profile-name"><span className="badge-eyebrow">MY GROWTH SPACE</span><h2>{name||"学员"}</h2><div className="profile-identity-tags"><span className="module-tag">成长等级 · 暂未开放</span></div><p>让每一份努力，成为看得见的成长印记。</p></div></div>
      <div className="profile-summary"><div><strong>—</strong><span>已拥有徽章 · 暂未开放</span></div><div><strong>{xp}</strong><span>累计新手村经验</span></div><div><strong>—</strong><span>商城积分 · 暂未开放</span></div></div>
      <div className="profile-featured"><ModuleIcon file="a03b5" pack="guild" size={48}/><div><span className="badge-eyebrow">展示徽章</span><h3>暂未开放</h3></div></div>
    </ModulePanel>
    <FavoriteKnowledge compact courses={[]} favoriteIds={[]} onToggle={unavailable} onOpen={unavailable} onBrowse={onAcademy} onShowAll={onAcademy}/>
    <div className="profile-experience-grid">
      <ModulePanel className="profile-experience"><div className="module-row"><div><span className="badge-eyebrow">EXPERIENCE & GROWTH</span><h2>我的经验与等级</h2></div><span className="module-tag">成长账户</span></div>
        <div className="profile-level-heading"><div className="profile-level-mark"><span>LEVEL</span><strong>—</strong></div><div><h3>成长等级暂未开放</h3><p>经验来自已审核通过的新手村任务。</p></div><div className="profile-lifetime"><strong>{xp}</strong><span>累计新手村经验</span></div></div>
        <div className="profile-xp-labels"><span>等级进度暂未开放</span></div><div className="profile-xp-track" aria-hidden="true"/>
        <div className="profile-xp-balances"><div><span>可兑换经验</span><strong>— <small>XP</small></strong></div><div><span>已用于兑换</span><strong>— <small>XP</small></strong></div><p>经验兑换暂未开放。</p></div>
      </ModulePanel>
      <ModulePanel className="profile-mall-points"><div className="module-row"><div><span className="badge-eyebrow">MUCHEN REWARDS</span><h3>沐晨商城积分</h3></div><ModuleIcon file="d7bdc" size={28}/></div><div className="profile-mall-number"><strong>—</strong><span>暂未开放</span></div><p>把成长积累，兑换成更多美好。<br/>商城积分与各类型徽章点分开计算。</p><div className="profile-exchange-rate"><span>兑换比例</span><b>暂未开放</b></div><button className="module-primary" onClick={unavailable}>经验兑换商城积分 →</button><button className="profile-exchange-history" onClick={unavailable}>查看兑换记录</button></ModulePanel>
    </div>
    <div className="profile-content-grid"><section><ModulePanel className="profile-badge-panel"><div className="profile-section-heading"><div><span className="badge-eyebrow">MY BADGE COLLECTION</span><h2>我的徽章墙</h2><p>这是属于你的成长收藏。</p></div><button className="module-secondary" onClick={unavailable}>前往徽章商城 →</button></div><div className="profile-badge-empty"><ModuleIcon file="a03b5" pack="guild" size={40}/><h3>暂未开放</h3><p>个人徽章展示功能暂未开放。</p></div></ModulePanel><ModulePanel className="profile-next"><div className="profile-next-icon"><ModuleIcon file="d7bdc" size={28}/></div><div><h3>下一枚徽章，会属于怎样的你？</h3><p>从真实任务中积累经验，找到下一个成长目标。</p></div><button className="module-secondary" onClick={unavailable}>发现更多徽章 →</button></ModulePanel></section>
      <aside className="profile-aside"><ModulePanel className="profile-capabilities"><span className="badge-eyebrow">MY EXPLORATION</span><h3>能力足迹</h3><p>暂未开放</p></ModulePanel><ModulePanel className="profile-wallet"><div className="module-row"><h3>成长补给站</h3><ModuleIcon file="a03b5" pack="guild" size={24}/></div>{wallet?Object.entries(pointNames).map(([id,label])=><div className="module-badge-allocation" key={id}><span>{label}徽章点</span><span>{wallet.badgeBalances[id]??0} 点</span></div>):<p>{error?"数据读取失败":"正在读取徽章点…"}</p>}<p>完成任务并通过审核后，获得对应类型的徽章点。</p><button className="module-secondary" onClick={unavailable}>去兑换徽章 →</button></ModulePanel></aside>
    </div>
    {notice&&<div className="module-toast" role="status">{notice}<button onClick={()=>setNotice("")} aria-label="关闭提示"> ×</button></div>}
  </div>;
}
