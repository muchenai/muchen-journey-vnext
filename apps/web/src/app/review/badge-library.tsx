"use client";
import type { CSSProperties } from 'react';
import { BADGES, type AdminTask } from './admin-types';
import { Icon } from './admin-ui';
export default function BadgeLibrary({tasks,open}:{tasks:AdminTask[];open:(id:string)=>void}) {
 return <><div className="card badge-rules"><div><span className="eyebrow">成长体系</span><h2>每一份投入，都有积累</h2><p>任务经验值按 10 : 1 换算为徽章点，再按任务配置的占比分配。</p></div><div className="badge-level-steps"><span><strong>100</strong>点亮 1 级</span><i/><span><strong>200</strong>达到 2 级</span><i/><span><strong>300</strong>达到 3 级</span></div></div>
 <div className="section-heading"><h2>标签与徽章 <span className="count-pill">8</span></h2><span className="muted">固定八种徽章 · 每个任务关联 1～2 种</span></div>
 <div className="badge-grid">{BADGES.map(b=><button className="card badge-summary-card" key={b.id} data-badge-view={b.id} onClick={()=>open(b.id)}><div className="badge-card-heading"><span className="badge-emblem" style={{'--badge-color':b.color} as CSSProperties}><Icon name="award" size={20}/></span><span className="tag tag-neutral">最高 3 级</span></div><h3>{b.name}徽章</h3><p>完成关联任务，积累专属徽章点</p><div className="badge-card-stats"><span><strong>{tasks.filter(t=>t.badges.some(x=>x.id===b.id)).length}</strong>关联任务</span><span><strong>—</strong>已发徽章点</span><span><strong>—</strong>已点亮人数</span></div><div className="badge-card-footer">查看收集情况 <span>→</span></div></button>)}</div><div className="inline-note">徽章点累计保留，达到 100 / 200 / 300 点分别获得 1 / 2 / 3 级。奖励通过后全额发放，每名学员每个任务只领取一次。</div></>;
}
