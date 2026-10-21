"use client";
import type { AdminReview } from "./admin-types";
import { Icon } from "./admin-ui";

const TABS = [['pending','待人工审核'],['ai','AI 自测结果'],['passed','已审核'],['failed','审核未通过']];
export function matchesReview(r: AdminReview, tab: string) { return tab === 'pending' ? ['ASSIGNED','IN_REVIEW'].includes(r.status) : tab === 'ai' ? r.ai_statuses.length > 0 : tab === 'passed' ? r.decision === 'PASS' : r.decision === 'REVISION_REQUIRED'; }
export default function ReviewQueue({reviews,camp,tab,setTab,search,setSearch,busy,openReview}:{reviews:AdminReview[];camp:string;tab:string;setTab:(s:string)=>void;search:string;setSearch:(s:string)=>void;busy:boolean;openReview:(r:AdminReview)=>void}) {
 const rows=reviews.filter(r=>matchesReview(r,tab)&&`${r.task_title} ${r.learner_name} ${r.learner_id}`.toLowerCase().includes(search.toLowerCase()));
 const count=(key:string)=>reviews.filter(r=>matchesReview(r,key)).length;
 const notes:Record<string,string>={pending:'查看学员答案，确认通过或退回修改。',ai:'查看 AI 自测结果与评测进度。',passed:'查看已经审核的学员提交。',failed:'查看未通过原因与学员重新提交的记录。'};
 const campName=camp==='exploration'?'探索营':'新手村';
 return <div className="page-content review-page" data-review-page="">
  <div className="stats-grid">{[['pending','待人工审核','等待导师审核学员答案'],['ai','AI 自测结果','自测结果与评测进度'],['passed','已审核','已审核通过的提交'],['failed','审核未通过','等待学员修改重提']].map(([key,label,note])=><div className="stat-card" key={key}><span className="stat-label">{label}</span><div className="stat-value">{count(key)}<span className="stat-unit">份</span></div><span className="stat-note">{note}</span></div>)}</div>
  <section className="card review-card">
   <div className="card-header review-toolbar"><div className="tabs">{TABS.map(([key,label])=><button className={`tab ${tab===key?'active':''}`} type="button" data-review-tab={key} key={key} onClick={()=>setTab(key)}>{label}<span className="count-badge">{count(key)}</span></button>)}</div><div className="search-field"><Icon name="search" size={16}/><input className="search-input" type="search" aria-label="搜索任务或学员" placeholder="搜索任务或学员" value={search} onChange={e=>setSearch(e.target.value)}/></div></div>
   <div className="review-tab-note"><span className="status-dot dot-purple"/>{notes[tab]}</div>
   <div className="table-wrap" data-review-table=""><table className="data-table"><thead><tr>{['学员','任务','评分','提交时间','状态','未通过原因','操作'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={r.id}>
    <td><div className="student-cell"><span className="avatar avatar-small">{r.learner_name.slice(-2)}</span><div><strong>{r.learner_name}</strong><span className="cell-subtext">{r.learner_id.slice(0,8)}</span></div></div></td>
    <td><strong className="table-task-title">{r.task_title}</strong><span className="table-subtitle">{r.domain} · 人工审核</span></td>
    <td>{r.score===null?<span className="muted">{matchesReview(r,'pending')?'待导师审核':'—'}</span>:<span className="score-text">{r.score}<span className="score-denominator"> /100</span></span>}</td>
    <td className="muted">{new Date(r.submitted_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})}</td>
    <td><span className={`badge ${r.decision==='PASS'?'badge-green':r.decision?'badge-red':'badge-purple'}`}>{r.decision==='PASS'?'审核通过':r.decision?'审核未通过':'待人工审核'}</span></td>
    <td className="muted">{r.reasons.length?r.reasons.join('、'):r.decision==='REVISION_REQUIRED'?r.feedback:'—'}</td>
    <td><button className="text-btn" disabled={busy} onClick={()=>openReview(r)}>{matchesReview(r,'pending')&&tab!=='ai'?'去审核':'查看详情'}<Icon name="arrowRight" size={16}/></button></td>
   </tr>)}{!rows.length&&<tr><td colSpan={7}><div className="empty-state review-empty"><div className="empty-icon"><Icon name="grid" size={16}/></div><strong>{search?'没有符合条件的记录':`${campName}暂无${tab==='pending'?'待审核答案':tab==='ai'?'自测结果':tab==='passed'?'已审核记录':'未通过记录'}`}</strong><p>{search?'请尝试其他搜索条件。':'学员提交后，记录将在这里展示。'}</p></div></td></tr>}</tbody></table></div>
   <div className="table-footer"><span data-review-count="">共 {rows.length} 条记录</span><span className="muted">审核通过后发放经验、任务点与徽章点</span></div>
  </section>
 </div>;
}
