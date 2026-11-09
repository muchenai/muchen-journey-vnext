import { useEffect, useRef, useState } from "react";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { badgePointLabel } from "./badgeEconomy";
import type { PreviewIdentity } from "./previewStorage";
import {
  beginDeliveryLab, buildDeliveryArchive, canSubmitDeliveryLab, completeLabStage,
  deliveryLabRewards, deliveryLabSamples, deliveryLabStages, handlingOptions, intentOptions,
  productionSamples, submitDeliveryLab, updateLabAnswer, updateLabHandling, updateLabLabel,
  withdrawDeliveryLab, type DeliveryLabSession, type DeliveryStageId,
} from "./deliveryLabModel";
import "./deliveryLab.css";

type LabTab = "materials" | "work" | "event";
const tabs: { id: LabTab; label: string }[] = [
  { id: "materials", label: "任务材料" }, { id: "work", label: "阶段成果" }, { id: "event", label: "异常事件" },
];

function SampleWorkbench({ session, stageId, onChange }: {
  session: DeliveryLabSession;
  stageId: DeliveryStageId;
  onChange: (session: DeliveryLabSession) => void;
}) {
  const preparing = stageId === "prepare";
  const rows = preparing ? deliveryLabSamples : productionSamples(session).slice(0, stageId === "pilot" ? 5 : undefined);
  const filled = rows.filter(row => preparing ? session.handling[row.id] : session.labels[row.id]).length;
  return <section className="delivery-lab-samples" aria-label="样本练习台">
    <div className="module-row"><h3>样本练习台</h3><span>{filled} / {rows.length} 条已{preparing ? "处理" : "分类"}</span></div>
    <p>{preparing ? "逐条确认数据去向。所有内容均为合成样本，不含真实个人信息。" : stageId === "pilot" ? "先为前 5 条保留样本试标，形成统一规则，再进入批量生产。" : "试生产结果已沿用。继续完成所有保留样本；修改试标标签会使相关阶段需要重新自查。"}</p>
    {rows.length ? <div className="delivery-lab-table-scroll" tabIndex={0} role="region" aria-label="可滚动的合成样本表">
      <table>
        <thead><tr><th scope="col">样本 ID</th><th scope="col">合成对话</th><th scope="col">{preparing ? "处理方式" : "意图分类"}</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.id}>
          <td>{row.id}</td>
          <td>{!preparing && session.handling[row.id] === "redact" ? row.text.replace(/\[待脱敏[^\]]+\]/g, "[已脱敏]") : row.text}</td>
          <td><select aria-label={`${row.id}${preparing ? "处理方式" : "意图分类"}`}
            disabled={session.status !== "active"}
            value={(preparing ? session.handling[row.id] : session.labels[row.id]) || ""}
            onChange={event => onChange(preparing ? updateLabHandling(session, row.id, event.target.value) : updateLabLabel(session, row.id, event.target.value))}>
            <option value="" disabled>请选择</option>
            {(preparing ? handlingOptions : intentOptions).map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select></td>
        </tr>)}</tbody>
      </table>
    </div> : <div className="delivery-lab-sample-empty">先在「03 数据准备」中选择至少 5 条保留样本，练习台将自动生成。</div>}
  </section>;
}

export function DeliveryLab({ identity, session, onChange, query, onClearSearch }: {
  identity: PreviewIdentity;
  session: DeliveryLabSession;
  onChange: (session: DeliveryLabSession) => void;
  query: string;
  onClearSearch: () => void;
}) {
  const [tab, setTab] = useState<LabTab>("materials");
  const [errors, setErrors] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const modal = useRef<HTMLDialogElement>(null);
  const errorBox = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const stage = deliveryLabStages.find(item => item.id === session.activeStage)!;
  const index = deliveryLabStages.indexOf(stage);
  const answer = session.answers[stage.id];
  const editable = session.status === "active";
  const ready = canSubmitDeliveryLab(session);
  const submitted = session.status === "submitted";
  const completed = session.completed.length;
  const selectedDecision = stage.event?.options.find(option => option.id === answer.decision);
  const matches = deliveryLabStages.filter(item => `${item.title} ${item.deliverable} ${item.brief}`.toLowerCase().includes(query.trim().toLowerCase()));

  useEffect(() => {
    const timer = window.setTimeout(() => { setTab("materials"); setErrors([]); }, 0);
    content.current?.scrollTo({ top: 0 });
    return () => window.clearTimeout(timer);
  }, [session.activeStage]);
  useEffect(() => { content.current?.scrollTo({ top: 0 }); }, [tab]);
  useEffect(() => { const timer = window.setTimeout(() => setErrors([]), 0); return () => window.clearTimeout(timer); }, [answer, session.handling, session.labels]);
  useEffect(() => { if (errors.length) errorBox.current?.focus(); }, [errors]);
  useEffect(() => {
    const element = modal.current;
    const timer = reviewOpen ? window.setTimeout(() => setConfirmed(false), 0) : undefined;
    if (reviewOpen) element?.showModal();
    else element?.close();
    return () => { window.clearTimeout(timer); element?.close(); };
  }, [reviewOpen]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const selectStage = (id: DeliveryStageId) => {
    setErrors([]);
    onChange({ ...session, activeStage: id });
  };
  const continueTask = () => {
    if (session.status === "available") {
      onChange(beginDeliveryLab(session));
      setNotice("已领取模拟任务，可从需求澄清开始。练习仅保留在本次会话。");
    } else if (submitted || ready) setReviewOpen(true);
    else selectStage(deliveryLabStages.find(item => !session.completed.includes(item.id))!.id);
  };
  const complete = () => {
    const result = completeLabStage(session, stage.id);
    setErrors(result.errors);
    if (result.errors.length) return;
    onChange(result.session);
    setNotice(index === 8 ? "九个阶段已完成自查。请预览档案后模拟提交。" : `「${stage.title}」已完成自查，进入下一阶段。`);
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([buildDeliveryArchive(session, identity)], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `delivery-lab-${identity}.md`;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return <div className="delivery-lab">
    <div className="delivery-lab-heading">
      <div><span className="module-eyebrow">DELIVERY SIMULATION LAB</span><h1>模拟实验室</h1></div>
      <div className="delivery-lab-environment"><i />前端模拟环境<span>当前身份 {identity}</span></div>
    </div>

    <ModulePanel className="delivery-lab-hero">
      <div className="delivery-lab-hero-copy">
        <div className="delivery-lab-hero-kicker"><span>LAB-001</span><span>一项任务 · 九个阶段 · 完整交付闭环</span></div>
        <h2>从客户需求到验收，<span>完成一次数据交付</span></h2>
        <p>担任交付负责人，在合成项目中完成需求、生产、质检与验收。<br />不是走完流程，而是留下每一次判断的依据。</p>
      </div>
      <div className="delivery-lab-hero-meta">
        <span className="module-tag">挑战</span><span>90 分钟</span><span>NPC 最终审核（待接入）</span>
        <div><strong>150 <small>XP</small></strong><i /><strong>15 <small>徽章点</small></strong></div>
        <small>预期奖励，仅展示，不实际发放</small>
      </div>
      <div className="delivery-lab-hero-action">
        <span className="module-status" data-status={submitted ? "pending" : editable ? "active" : "available"}>{submitted ? "模拟待审核" : editable ? "演练进行中" : "已发布 · 可直接领取"}</span>
        <button className="module-primary" onClick={continueTask}>{session.status === "available" ? "领取模拟任务" : submitted ? "查看交付档案" : ready ? "预览并模拟提交" : "继续我的演练"}<ModuleIcon file="b5042" size={17} /></button>
        <small>不消耗点数，不影响真实任务进度</small>
      </div>
    </ModulePanel>

    {submitted && <div className="delivery-lab-submitted" role="status"><ModuleIcon file="eec40" /><span>第 {session.submissionCount} 次模拟提交已生成，尚未发送至 NPC 管理端，也未发放奖励。</span><button onClick={() => { onChange(withdrawDeliveryLab(session)); setNotice("已撤回本次模拟提交，成果保留，可修改后重新模拟提交。"); }}>撤回模拟提交并修改</button></div>}

    <div className="delivery-lab-workspace">
      <ModulePanel className="delivery-lab-roadmap">
        <div className="delivery-lab-panel-heading"><span className="module-eyebrow">PROJECT WORKFLOW</span><h3>交付流程</h3><p>{query ? `搜索匹配 ${matches.length} 个阶段` : "可自由预览，按顺序完成自查"}</p></div>
        <nav className="delivery-lab-stage-list" aria-label="数据交付九阶段">
          {matches.map(item => {
            const number = deliveryLabStages.indexOf(item);
            const done = session.completed.includes(item.id);
            return <button key={item.id} data-lab-stage={item.id} className={`delivery-lab-step${stage.id === item.id ? " is-active" : ""}${done ? " is-done" : ""}`}
              aria-current={stage.id === item.id ? "step" : undefined} onClick={() => selectStage(item.id)}>
              <span className="delivery-lab-step-number">{String(number + 1).padStart(2, "0")}</span>
              <span><strong>{item.title}</strong><small>{done ? "已完成自查" : stage.id === item.id ? "当前阶段" : item.deliverable}</small></span>
              <span className="delivery-lab-step-dot" />
            </button>;
          })}
          {!matches.length && <div className="delivery-lab-no-results"><p>没有匹配的阶段</p><button className="module-secondary" onClick={onClearSearch}>清空搜索</button></div>}
        </nav>
        <div className="delivery-lab-roadmap-foot"><ModuleIcon file="eec40" size={14} /><span>9 个阶段合为一份交付档案</span></div>
      </ModulePanel>

      <ModulePanel className="delivery-lab-stage-panel">
        <div className="delivery-lab-stage-heading"><div><span className="module-eyebrow">STAGE {String(index + 1).padStart(2, "0")} / 09</span><h2>{stage.title}</h2><p>{stage.subtitle}</p></div><span className="delivery-lab-role">{stage.role}</span></div>
        <div className="delivery-lab-tabs" role="tablist" aria-label="阶段内容" onKeyDown={event => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const enabled = tabs.filter(item => item.id !== "event" || stage.event);
          const current = enabled.findIndex(item => item.id === tab);
          const next = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + enabled.length) % enabled.length;
          setTab(enabled[next].id);
          event.currentTarget.querySelector<HTMLButtonElement>(`[data-lab-tab="${enabled[next].id}"]`)?.focus();
        }}>
          {tabs.map(item => <button key={item.id} id={`delivery-tab-${item.id}`} data-lab-tab={item.id} role="tab"
            aria-selected={tab === item.id} aria-controls="delivery-stage-content" tabIndex={tab === item.id ? 0 : -1}
            disabled={item.id === "event" && !stage.event} onClick={() => setTab(item.id)}>
            {item.label}{item.id === "event" && stage.event && <span>1</span>}
          </button>)}
        </div>
        {errors.length > 0 && <div ref={errorBox} className="delivery-lab-errors" role="alert" tabIndex={-1}><strong>还有几项需要补充</strong><ul>{errors.map(error => <li key={error}>{error}</li>)}</ul>{stage.event && <button onClick={() => setTab("event")}>查看本阶段异常事件 →</button>}</div>}

        <div ref={content} id="delivery-stage-content" className="delivery-lab-stage-content" role="tabpanel" aria-labelledby={`delivery-tab-${tab}`} tabIndex={0}>
          {tab === "materials" ? <>
            <p className="delivery-lab-lead">{stage.brief}</p>
            <div className="delivery-lab-materials">{stage.materials.map((material, number) => <article key={material.title}>
              <div><ModuleIcon file="eec40" size={16} /><h3>{material.title}</h3><small>材料 {String(number + 1).padStart(2, "0")}</small></div><p>{material.content}</p>
            </article>)}</div>
            <section className="delivery-lab-deliverable"><span className="module-eyebrow">YOUR DELIVERABLE</span><h3>{stage.deliverable}</h3><ol>{stage.prompts.map(prompt => <li key={prompt}>{prompt}</li>)}</ol></section>
            {["prepare", "pilot", "produce"].includes(stage.id) && <div className="delivery-lab-material-hint"><ModuleIcon pack="guild" file="a03b5" size={15} /><span>这一阶段包含样本操作，请到「阶段成果」中的练习台完成。</span></div>}
          </> : tab === "work" ? <>
            {!editable && <p className="delivery-lab-readonly">{submitted ? "本次档案已模拟提交。撤回后可继续编辑，阅读材料不受影响。" : "先领取顶部的模拟任务，即可填写成果和操作样本。"}</p>}
            {["prepare", "pilot", "produce"].includes(stage.id) && <SampleWorkbench session={session} stageId={stage.id} onChange={onChange} />}
            <fieldset disabled={!editable} className="delivery-lab-fieldset">
              <legend className="sr-only">{stage.deliverable}</legend>
              <div className="delivery-lab-field-heading"><label htmlFor={`delivery-artifact-${stage.id}`}>{stage.deliverable}</label><span>{answer.artifact.length} / 6,000 字</span></div>
              <ol className="delivery-lab-writing-prompts">{stage.prompts.map(prompt => <li key={prompt}>{prompt}</li>)}</ol>
              <textarea id={`delivery-artifact-${stage.id}`} value={answer.artifact} maxLength={6000} rows={7}
                placeholder="写下你的方案、判断依据、负责人和下一步动作。至少 60 字；不要粘贴真实客户数据。"
                onChange={event => onChange(updateLabAnswer(session, stage.id, { artifact: event.target.value }))} />
              <div className="delivery-lab-checks"><h3>阶段自查</h3>{stage.checks.map(check => <label key={check}><input type="checkbox" checked={answer.checks.includes(check)}
                onChange={event => onChange(updateLabAnswer(session, stage.id, { checks: event.target.checked ? [...answer.checks, check] : answer.checks.filter(item => item !== check) }))} /><span>{check}</span></label>)}</div>
            </fieldset>
            <p className="delivery-lab-integrity-note">这里只检查填写完整性，不代表 AI 评分或 NPC 验收。修改已自查的内容，会使相关阶段及后续阶段需要重新自查。</p>
          </> : stage.event ? <>
            <div className="delivery-lab-event-heading"><span>模拟事件 · 需要你的决策</span><h3>{stage.event.title}</h3><p>{stage.event.message}</p></div>
            <fieldset className="delivery-lab-fieldset" disabled={!editable}>
              <legend>你会如何处理？</legend>
              <div className="delivery-lab-decisions">{stage.event.options.map(option => <label key={option.id}><input type="radio" name={`delivery-decision-${stage.id}`} value={option.id} checked={answer.decision === option.id} onChange={() => onChange(updateLabAnswer(session, stage.id, { decision: option.id }))} /><span>{option.label}</span></label>)}</div>
              {selectedDecision && <div className="delivery-lab-feedback" role="status"><span>规则提示 · 非 AI 评审</span><p>{selectedDecision.feedback}</p></div>}
              <label className="delivery-lab-rationale-label" htmlFor={`delivery-rationale-${stage.id}`}>判断依据与闭环动作 <small>{answer.rationale.length} / 2,000 字</small></label>
              <textarea id={`delivery-rationale-${stage.id}`} maxLength={2000} rows={6} value={answer.rationale} placeholder="至少 30 字。说明影响、备选方案、确认人、证据及下一步动作。"
                onChange={event => onChange(updateLabAnswer(session, stage.id, { rationale: event.target.value }))} />
            </fieldset>
          </> : <p className="delivery-lab-lead">本阶段没有额外异常事件，请继续阅读材料和填写阶段成果。</p>}
        </div>
        <div className="delivery-lab-stage-footer">
          <button className="module-secondary" disabled={index === 0} onClick={() => selectStage(deliveryLabStages[index - 1].id)}>上一阶段</button>
          <span>交付物：{stage.deliverable}</span>
          <button className="module-primary" disabled={!editable} onClick={tab === "work" ? complete : () => setTab("work")}>{tab !== "work" ? "填写阶段成果" : index === 8 ? "完成自查 · 整理档案" : "完成自查 · 下一阶段"}<ModuleIcon file="b5042" size={16} /></button>
        </div>
      </ModulePanel>

      <aside className="delivery-lab-aside" aria-label="项目简报与整体进度">
        <ModulePanel className="delivery-lab-progress">
          <div className="module-row"><h3>整体进度</h3><span className="module-tag">单项主任务</span></div>
          <div className="delivery-lab-progress-number"><strong>{String(completed).padStart(2, "0")}</strong><span>/ 09 阶段自查</span></div>
          <progress max={9} value={completed} aria-label="已完成自查的阶段数" />
          <p>{submitted ? "已生成模拟待审核状态；未发送到后台。" : ready ? "阶段成果已齐备，请检查档案后模拟提交。" : `还需完成 ${9 - completed} 个阶段的自查。`}</p>
          <button className="module-primary" disabled={!ready && !submitted} onClick={() => setReviewOpen(true)}>{submitted ? "查看交付档案" : "预览并模拟提交"}<ModuleIcon file="eec40" size={16} /></button>
          <button className="delivery-lab-export" disabled={session.status === "available"} onClick={download}>下载当前档案 · Markdown</button>
        </ModulePanel>
        <ModulePanel className="delivery-lab-brief">
          <div className="module-row"><h3>项目简报</h3><ModuleIcon file="eec40" size={17} /></div>
          <span className="delivery-lab-project-code">SG / INTENT CLASSIFICATION</span>
          <dl><div><dt>模拟客户</dt><dd>星港客服中心</dd></div><div><dt>项目规模</dt><dd>1,000 条中文对话</dd></div><div><dt>练习样本</dt><dd>20 条合成数据</dd></div><div><dt>约定交期</dt><dd>T+5 工作日</dd></div><div><dt>交付格式</dt><dd>UTF-8 / JSONL</dd></div></dl>
          <div className="delivery-lab-baseline"><strong>本案例暂定验收基线</strong><span>分类正确率 ≥ 95%</span><span>格式合规率 100%</span><span>禁止明文敏感信息</span></div>
          <p>客户、数据、预算与报表均为虚构。当前按通用流程演练，尚未对齐飞书正式 SOP。</p>
        </ModulePanel>
        <ModulePanel className="delivery-lab-rewards"><h3>完成后的预期奖励</h3><div><span>成长经验</span><strong>150 XP</strong></div>{deliveryLabRewards.map(reward => <div key={reward.type}><span>{badgePointLabel(reward.type)}</span><strong>+{reward.amount}</strong></div>)}<p>正式审核通过后应一次性结算。本次练习不接审核、不发奖。</p></ModulePanel>
      </aside>
    </div>

    <div className="delivery-lab-session-note" role="status">{notice || "练习仅保留在当前身份的本次页面会话；刷新或重新登录会清除。不会覆盖探索营或既有任务记录。"}</div>

    <dialog ref={modal} className="module-dialog journey-dialog delivery-lab-dialog" aria-labelledby="delivery-archive-title" onCancel={() => setReviewOpen(false)}>
      <JourneyDialogSurface>
        <div className="module-dialog-heading"><span className="module-eyebrow">PROJECT DELIVERY ARCHIVE</span><button onClick={() => setReviewOpen(false)} aria-label="关闭交付档案">关闭</button></div>
        <h2 id="delivery-archive-title">完整项目，完整交付</h2>
        <p className="delivery-lab-dialog-subtitle">{submitted ? "模拟提交已生成，尚未进入真实审核。" : "请检查九个阶段的成果、异常处理和样本记录。"}</p>
        <div className="delivery-lab-archive-summary"><span><strong>{completed}/9</strong>阶段自查</span><span><strong>{Object.keys(session.handling).length}/20</strong>样本处理</span><span><strong>{productionSamples(session).filter(sample => session.labels[sample.id]).length}/{productionSamples(session).length}</strong>保留样本分类</span></div>
        <div className="delivery-lab-archive-preview" tabIndex={0} role="region" aria-label="可滚动的阶段成果档案">
          {deliveryLabStages.map((item, number) => <details key={item.id}><summary><span>{String(number + 1).padStart(2, "0")} · {item.deliverable}</span><small>{session.completed.includes(item.id) ? "已自查" : "待补充"}</small></summary><p>{session.answers[item.id].artifact || "尚未填写"}</p>{item.event && <div><strong>{item.event.title}</strong><p>{item.event.options.find(option => option.id === session.answers[item.id].decision)?.label || "尚未选择"}</p><p>{session.answers[item.id].rationale || "尚未填写"}</p></div>}</details>)}
        </div>
        <p className="delivery-lab-dialog-warning">这是前端模拟档案，不会发送至 NPC 管理端，不代表审核通过，也不会发放经验或徽章点。完整样本明细可随档案下载。</p>
        {!submitted && <label className="delivery-lab-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /><span>我已核对本次成果，并理解这是模拟提交。</span></label>}
        <div className="delivery-lab-dialog-actions"><button className="module-secondary" onClick={download}>下载完整档案</button><button className="module-primary" disabled={submitted || !ready || !confirmed} onClick={() => {
          if (!confirmed) return;
          onChange(submitDeliveryLab(session, new Date().toISOString()));
          setReviewOpen(false);
          setNotice("已生成模拟待审核状态。尚未发送至后台，不会发放奖励。");
        }}>{submitted ? "已模拟提交" : "确认模拟提交"}</button></div>
      </JourneyDialogSurface>
    </dialog>
  </div>;
}
