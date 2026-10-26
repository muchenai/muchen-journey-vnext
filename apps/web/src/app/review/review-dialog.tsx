"use client";
import { useState } from "react";
import type { ReviewDetail } from "@/lib/server/api";
import type { AdminReview } from "./admin-types";
import { decideAdminReview } from "./admin-actions";
import { Icon, Modal, TextLinks, time, statusLabel } from "./admin-ui";
const REASONS = ["提交材料不完整", "答案错误", "未达到任务要求", "依据或论证不足", "其他"];
const AI_LABELS = { NOT_FOUND: "尚未进行 AI 自查", RUNNING: "AI 自查中", SENDING: "正在写入评论", UNCERTAIN: "评论状态待核对", FAILED: "自查未完成", COMPLETED: "自查已完成" };
export default function ReviewDialog({ detail: d, item, close, done }: { detail: ReviewDetail; item: AdminReview; close: () => void; done: () => void }) {
 const prior = d.evaluation ?? d.coaching_feedback;
 const [feedback, setFeedback] = useState(prior?.overall_feedback ?? "");
 const [score, setScore] = useState(item.score === null ? '' : String(item.score));
 const [reasons, setReasons] = useState<string[]>(item.reasons), [busy, setBusy] = useState(false), [error, setError] = useState('');
 const [scores, setScores] = useState<Record<string, string>>(()=>Object.fromEntries((prior?.rubric_evaluations??[]).map(r=>[r.dimension_key,r.score===null?'':String(r.score)])));
 const [ratings, setRatings] = useState<Record<string, string>>(()=>Object.fromEntries((prior?.rubric_evaluations??[]).map(r=>[r.dimension_key,r.rating])));
 const editable = (d.status === 'ASSIGNED' || d.status === 'IN_REVIEW') && d.allowed_commands.some(c=>['start','approve','request_revision'].includes(c));
 async function decide(decision: "APPROVE" | "REQUEST_REVISION") {
  if (busy) return;
  if (decision === 'REQUEST_REVISION' && (!reasons.length || Array.from(feedback.replace(/\s/gu, '')).length < 5)) {setError('退回时至少选择一项原因，并填写至少 5 个字的具体修改建议（空格和换行不计入）。');return;}
  const evaluations = d.rubric.dimensions.filter(x=>x.required).map(dim => ({dimension_key:dim.dimension_key,
   rating:dim.max_points ? (ratings[dim.dimension_key] ?? 'MEETS') : decision === 'APPROVE' ? 'MEETS' : 'NEEDS_WORK',
   feedback:Array.from(feedback.trim()).length >= 5 ? feedback.trim().slice(0,500) : '已核对任务要求与提交内容，本次任务完成情况符合要求。',
   ...(dim.max_points ? {score:Number(scores[dim.dimension_key])} : {})}));
  if (d.rubric.dimensions.some(dim => dim.max_points && (!scores[dim.dimension_key] || Number(scores[dim.dimension_key]) > dim.max_points || Number(scores[dim.dimension_key]) < 0))) {setError('请完整填写历史任务的固定评分维度。');return;}
  setBusy(true);setError('');
  const result = await decideAdminReview(d.id,{expected_revision:d.revision,decision,feedback,score:score === '' ? null : Number(score),reasons,rubric_evaluations:evaluations},crypto.randomUUID());
  setBusy(false);
  if (result.ok) done(); else setError(result.error);
 }
 return <Modal title="详情" className="review-modal" close={close} busy={busy}><div className="review-detail">
 <div className="review-detail-heading"><div><div className="eyebrow">MANUAL REVIEW</div><h2>{editable?'审核学员答案':'提交详情'}</h2><p className="muted">{d.learner_name} · {time(d.submitted_at)}</p></div></div>
 <div className="review-detail-meta"><strong>{d.task_title}</strong><span className={`badge ${item.decision==='PASS'?'badge-green':item.decision?'badge-red':'badge-purple'}`}>{item.decision==='PASS'?'审核通过':item.decision?'审核未通过':'待人工审核'}</span><span className="badge badge-neutral">人工审核</span><span className="badge badge-neutral">{item.camp==='novice'?'新手村':'探索营'}</span></div>
 <div className="review-detail-grid"><div className="review-answer-column">
 <section className="detail-section"><h3>学员提交答案</h3><div className="answer-text answer-box"><TextLinks text={d.submission_body}/></div>{d.materials.attachments.length===0?<p className="muted">本次提交无附件</p>:<div className="file-list">{d.materials.attachments.map(a=>a.status==='READY'&&a.scan_status==='CLEAN'?<a className="file-chip" href={`/review/${d.id}/attachments/${a.id}`} key={a.id}><Icon name="file" size={16}/><span>{a.original_filename}</span><Icon name="download" size={16}/></a>:<span className="file-chip" key={a.id}><Icon name="file" size={16}/><span>{a.original_filename}</span><span className="muted file-meta">附件待处理</span></span>)}</div>}</section>
 <details className="review-reference"><summary>任务要求与学习材料<Icon name="chevronDown" size={16}/></summary><div className="review-reference-content"><h4>任务要求</h4><div className="review-task-question"><strong>{d.task_title}</strong><TextLinks text={d.task_purpose}/><TextLinks text={d.completion_criteria.join('；')}/></div><h4>学习材料</h4><div className="file-list">{d.task_learning_materials?.map(m=>m.url?<a className="file-chip" key={m.key} href={m.url} target="_blank" rel="noreferrer"><Icon name="file" size={16}/><span>{m.title}</span><Icon name="external" size={16}/></a>:<div key={m.key}><strong>{m.title}</strong><TextLinks text={m.body??''}/></div>)}</div></div></details>
 {d.submission_history.length>1&&<details className="review-reference"><summary>历史提交（{d.submission_history.length}）<Icon name="chevronDown" size={16}/></summary><div className="review-reference-content">{d.submission_history.map(h=><article key={h.id}><h4>第 {h.version_no} 版 · {time(h.created_at)}</h4><TextLinks text={h.body}/></article>)}</div></details>}
 </div><div className="review-evaluation-column">
 {d.document_ai_checks.map((check,i)=><section className="detail-section" key={check.document_url}><div className="section-title-row"><h3><Icon name="sparkles" size={18}/>AI 评测</h3><span className="muted">{AI_LABELS[check.status]}</span></div><div className="ai-comment"><strong>AI 评语</strong>{check.result&&<TextLinks text={check.result}/>}<p className="muted">{time(check.generated_at)}</p><a className="text-btn" href={check.document_url} target="_blank" rel="noreferrer">答题文档 {i+1}<Icon name="external" size={16}/></a></div>{check.history.length>0&&<details className="review-reference"><summary>历史自查记录（{check.history.length}）<Icon name="chevronDown" size={16}/></summary><div className="review-reference-content">{check.history.map((h,n)=><article key={`${h.record_id}-${n}`}><h4>{time(h.generated_at)} · 文档版本 {h.document_revision}</h4><TextLinks text={h.result??''}/></article>)}</div></details>}</section>)}
 <section className="detail-section review-rewards"><h3>通过后奖励</h3><div className="reward-inline"><span><strong>—</strong> 经验值</span><span><strong>—</strong> 任务点</span></div><div className="review-badge-rewards"/><p className="small muted">当前任务未关联奖励发放规则。</p></section>
 </div></div>
 <section className="review-final-section"><div className="section-title-row"><h3>最终审核</h3>{prior&&<span className="muted">{statusLabel(item.decision??d.status)}</span>}</div><fieldset className="editor-fieldset" disabled={busy||!editable}><div className="review-final-grid"><label className="form-field"><span>审核得分 <span className="muted">选填</span></span><div className="input-suffix"><input className="form-input" type="number" min="0" max="100" step="1" value={score} onChange={e=>setScore(e.target.value)} placeholder="可不填写" aria-label="审核得分（选填）"/><span>/ 100</span></div><small>由导师直接决定是否通过，不设通过分数线。</small></label><label className="form-field"><span>审核评语 <span className="muted">通过时选填，退回时至少 5 个字</span></span><textarea className="form-textarea" rows={3} maxLength={2000} value={feedback} onChange={e=>setFeedback(e.target.value)} placeholder="通过时可不填写；退回时请填写至少 5 个字的修改建议，空格和换行不计入"/></label></div>
 {d.rubric.dimensions.filter(x=>x.max_points).map(dim=><div key={dim.dimension_key} className="review-final-grid"><label className="form-field"><span>{dim.title}（0–{dim.max_points}）</span><input type="number" min="0" max={dim.max_points} value={scores[dim.dimension_key]??''} onChange={e=>setScores({...scores,[dim.dimension_key]:e.target.value})}/></label><label className="form-field"><span>维度结论</span><select value={ratings[dim.dimension_key]??'MEETS'} onChange={e=>setRatings({...ratings,[dim.dimension_key]:e.target.value})}><option value="MEETS">达到要求</option><option value="NEEDS_WORK">需修改</option></select></label></div>)}
 <fieldset className="return-reason-options"><legend>退回原因 <span className="muted">退回时至少选择一项</span></legend>{REASONS.map(reason=><label key={reason}><input type="checkbox" checked={reasons.includes(reason)} onChange={e=>setReasons(e.target.checked?[...reasons,reason]:reasons.filter(x=>x!==reason))}/><span>{reason}</span></label>)}</fieldset></fieldset><p className="inline-error" role="alert" hidden={!error}>{error}</p></section>
 <div className="modal-footer"><button className="btn btn-secondary" onClick={close} disabled={busy}>{editable?'取消':'关闭'}</button>{editable&&<div className="button-group"><button className="btn btn-danger" disabled={busy} onClick={()=>void decide('REQUEST_REVISION')}>退回修改</button><button className="btn btn-primary" disabled={busy} onClick={()=>void decide('APPROVE')}><Icon name="check" size={16}/>{busy?'正在保存…':'确认通过'}</button></div>}</div>
 </div></Modal>;
}
