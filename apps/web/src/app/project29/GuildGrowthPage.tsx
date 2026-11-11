import { useEffect, useRef, useState } from "react";
import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { BadgeArtworkImage } from "./BadgeArtworkImage";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { badgeCatalogGroups } from "./badgeCatalog";
import type { Badge } from "./badgeEconomy";
import { Medal } from "./BadgeShop";
import { useGuildGrowth } from "./useGuildGrowth";
import {
  guildCapabilityLabel, guildCapabilityRows, guildCertificationRules, guildCanApply, guildBadgeGrade,
  guildLevelNames, guildStageNames, guildOwnedBadges, guildPendingRequest, guildActiveHall,
  guildSubmission, guildTaskScope, guildTaskValidation, type GuildView, type GuildTaskDraft, type GuildRequest,
} from "./guildGrowthModel";
import "./guildGrowth.css";

const gradeNames = ["未获得", "一级 · 蓝色", "二级 · 紫色", "三级 · 金色"];
const arenaMemberNames = ["", "见习成员", "正式成员", "公会骨干"];
const guildHallIconPacks: Record<string, "academy" | "guild"> = {
  "42cb2": "academy", "d7bdc": "academy", "eec40": "academy", "8c48a": "academy",
};
const views: { id: GuildView; title: string; description: string; icon: string }[] = [
  { id: "certification", title: "能力地图", description: "汇集徽章与任务成果，查看每一级的认证要求。", icon: "a03b5" },
  { id: "arena", title: "认证竞技场", description: "查看逐级门槛，满足要求后认证晋级。", icon: "a6862" },
];
export function GuildGrowthPage({ view, identity, onView, onBadges, onAcademy, onLab, query, active = true }: {
  view: GuildView; identity: string; active?: boolean;
  onView: (view: GuildView) => void; onBadges: () => void;
  onAcademy: () => void; onLab: () => void; query: string;
}) {
  const [group, setGroup] = useState("points");
  const [focused, setFocused] = useState("product");
  const [selection, setSelection] = useState<{ guildId: string; level: 1 | 2 | 3 } | null>(null);
  const [message, setMessage] = useState("");
  const [taskDrafts, setTaskDrafts] = useState<Record<string, GuildTaskDraft>>({});
  const [taskError, setTaskError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const { snapshot, account, error, busy, refreshing, refresh, join, saveTask, submit } = useGuildGrowth(identity, active);
  const target = selection && selection.guildId === snapshot?.joinedGuild ? selection.level : null;
  const closeTarget = () => setSelection(null);
  const openTarget = (level: 1 | 2 | 3) => {
    if (!snapshot?.joinedGuild) { onView("hall"); return; }
    setTaskError("");
    setSelection({ guildId: snapshot.joinedGuild, level });
  };
  useEffect(() => {
    const element = dialog.current;
    if (target && active) element?.showModal();
    else element?.close();
    return () => element?.close();
  }, [target, selection?.guildId, active]);
  useEffect(() => { const timer = window.setTimeout(() => { setSelection(null); setTaskDrafts({}); setMessage(""); }, 0); return () => window.clearTimeout(timer); }, [identity]);
  useEffect(() => { scroll.current?.scrollTo({ top: 0 }); }, [view]);
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(""), 5000);
    return () => window.clearTimeout(timer);
  }, [message]);
  if (!snapshot || !account) return <div className="guild-growth-page"><div className="guild-growth-heading"><div><span className="module-eyebrow">DELIVERY / GUILD GROWTH</span><h1>{views.find(item => item.id === view)?.title || "交付线公会"}</h1></div></div><ModulePanel className="guild-empty"><p role={error ? "alert" : "status"}>{error || "正在读取你的公会认证和徽章凭证…"}</p>{error && <button className="module-secondary" disabled={refreshing} onClick={() => void refresh()}>{refreshing ? "正在读取…" : "重新读取"}</button>}</ModulePanel></div>;
  const { badges, wallet } = account;
  const activeGuild = guildActiveHall(snapshot);
  const current = activeGuild ? snapshot.level : 0;
  const owned = guildOwnedBadges(badges, wallet.owned);
  const capabilities = guildCapabilityRows(badges, wallet.owned);
  const covered = capabilities.filter(row => row.acquired.length).length;
  const next = current < 3 ? (current + 1) as 1 | 2 | 3 : null;
  const nextStatus = snapshot.requirements.find(item => item.level === next);
  const check = snapshot.requirements.find(item => item.level === target);
  const pending = guildPendingRequest(snapshot);
  const activeRequests = snapshot.requests.filter(record => record.guildId === activeGuild?.id);
  const activeRecords = activeRequests.filter(record => record.status === "approved");
  const targetTask = snapshot.tasks.find(task => task.level === target);
  const submittedTask = activeGuild && target ? guildSubmission(snapshot, activeGuild.id, target) : undefined;
  const scope = activeGuild && target ? guildTaskScope(activeGuild.id, target) : "";
  const taskDraft = (!pending && target !== null && current < target ? taskDrafts[scope] : undefined) || { artifact: submittedTask?.artifact || "", checks: submittedTask?.checks || [], revision: submittedTask?.revision || 0 };
  const taskChanged = taskDraft.artifact !== (submittedTask?.artifact || "") || targetTask?.checks.some(item => taskDraft.checks.includes(item) !== (submittedTask?.checks || []).includes(item));
  const draftConflict = taskDraft.revision !== (submittedTask?.revision || 0);
  const canApply = target !== null && guildCanApply(snapshot, target) && !taskChanged && !draftConflict;
  const canEdit = !!activeGuild && !!check?.entryEligible && !pending && target !== null && current < target;
  const search = query.trim().toLowerCase();
  const matchingOwned = owned.filter(badge => `${badge.name} ${badge.category}`.toLowerCase().includes(search));
  const mapRows = capabilities.filter(row => row.group === group);
  const selected = mapRows.find(row => row.id === focused) || mapRows[0];
  const evidence = (check?.grades || []).flatMap(grade => { const match = owned.find(badge => guildBadgeGrade(badge) === grade); return match ? [match] : []; });
  const badgePicture = (badge: Badge, large = false) => <Medal badge={badge} large={large} />;
  const selectGuild = async (id: string, openArena = false) => {
    if (await join(id)) {
      closeTarget();
      setMessage(`当前已进入「${snapshot.halls.find(hall => hall.id === id)?.title || "公会"}」。各公会成果与认证进度独立保存。`);
      if (openArena) onView("arena");
    }
  };
  const updateDraft = (patch: Partial<GuildTaskDraft>) => {
    setTaskError("");
    setTaskDrafts(previous => ({ ...previous, [scope]: { ...taskDraft, ...patch } }));
  };
  const persistTask = async (submitResult: boolean) => {
    if (!activeGuild || !target || !targetTask) return;
    const invalid = submitResult ? guildTaskValidation(targetTask, taskDraft) : "";
    if (invalid) { setTaskError(invalid); return; }
    const savedScope = scope;
    if (await saveTask(activeGuild.id, target, taskDraft, submitResult)) {
      setTaskDrafts(previous => { const updated = { ...previous }; delete updated[savedScope]; return updated; });
      setTaskError("");
      setMessage(submitResult ? "任务成果已提交，请核对后提交认证申请。" : "本公会本阶段的成果草稿已保存。");
    }
  };
  const requirements = (level: 1 | 2 | 3) => {
    const status = snapshot.requirements.find(item => item.level === level);
    if (!status) return <p className="guild-muted">认证条件暂不可用，请重新读取。</p>;
    return <ul className="guild-requirements">
      <li data-met={!!activeGuild}><span className="guild-requirement-mark" />已加入一个目标公会<small>{activeGuild?.title || "尚未加入"}</small></li>
      <li data-met={status.previousMet}><span className="guild-requirement-mark" />{level === 1 ? "当前公会可从规范实践任务开始" : `本公会已完成「${guildStageNames[level - 1]}」阶段`}<small>{status.previousMet ? "已满足" : "未满足"}</small></li>
      {status.grades.map(grade => { const count = status.counts?.find(item => item.grade === grade)?.count ?? owned.filter(badge => guildBadgeGrade(badge) === grade).length; return <li key={grade} data-met={count > 0}><span className="guild-requirement-mark" />至少 1 枚{gradeNames[grade]}徽章<small>已获 {count} 枚</small></li>; })}
      <li data-met={status.taskSubmitted}><span className="guild-requirement-mark" />完成本阶段认证任务<small>{status.taskSubmitted ? "成果已提交" : "尚未完成"}</small></li>
    </ul>;
  };
  const evidencePanel = <ModulePanel className="guild-evidence-panel"><div className="module-row"><h3>已获得的徽章凭证</h3><span>{owned.length} 枚 · 来自当前身份徽章账户</span></div><p className="guild-muted">余额足够、预览外观和课程学习，都不等于获得徽章；只读取实际已拥有的徽章 ID。</p>
    <div className="guild-evidence-list">{matchingOwned.map(badge => <div key={badge.id} className="guild-evidence-item">{badgePicture(badge)}<div><strong>{badge.name}</strong><span>{badge.category}</span></div><small data-grade={guildBadgeGrade(badge)}>{gradeNames[guildBadgeGrade(badge)]}</small></div>)}</div>
    {!matchingOwned.length && <div className="guild-empty">{owned.length ? "没有匹配的徽章，请调整顶部搜索词。" : "还没有已获得的徽章。先去新手村完成任务，再按发布条件兑换徽章。"}</div>}
    <button className="module-secondary" onClick={onBadges}>查看我的徽章与兑换条件 <ModuleIcon file="b5042" size={15} /></button>
  </ModulePanel>;
  const renderRecord = (record: GuildRequest, legacy = false) => <div key={record.id} className="guild-record">
    <div className="module-row"><strong>{legacy ? `旧版全局认证 · L${record.level}` : `${guildStageNames[record.level]} · ${guildLevelNames[record.level]}`}</strong><span className="guild-review-status" data-status={record.status}>{record.status === "pending" ? "申请待审核" : record.status === "approved" ? "审核已通过" : "已退回"}</span></div>
    <small>{legacy ? "旧版全局记录" : activeGuild?.title} · 提交于 {new Date(record.submittedAt).toLocaleString("zh-CN", { hour12: false })}</small>
    <p>{record.evidence.map(item => item.name).join("、")}</p>
    {record.task && <p>认证任务：{record.task.title}</p>}
    {record.reviewedAt && <small>{record.reviewerName || "管理员"} · {new Date(record.reviewedAt).toLocaleString("zh-CN", { hour12: false })}</small>}
    {record.reason && <p className="guild-review-reason">{record.status === "returned" ? "退回原因：" : "审核说明："}{record.reason}</p>}
    {!legacy && record.status === "returned" && current + 1 === record.level && !pending && <button className="module-secondary" disabled={busy} onClick={() => openTarget(record.level)}>修改成果并重新申请</button>}
  </div>;
  const historyPanel = <ModulePanel className="guild-record-panel"><div className="module-row"><h3>我的公会认证</h3><button className="guild-refresh" disabled={busy || refreshing} onClick={() => void refresh()}>{refreshing ? "读取中…" : "刷新结果"}</button></div><p className="guild-muted">管理员审核通过后才升级；不因获得徽章或提交成果自动晋级。</p>
    {!activeGuild ? <div className="guild-empty">尚未加入公会<br /><small>请先在公会大厅选择一个公会加入，再进行三阶认证。</small></div> : !activeRequests.length ? <div className="guild-empty">{activeGuild.title} · 尚未提交认证申请<br /><small>完成徽章条件和本阶段任务后，提交成果并申请认证。</small></div> : activeRequests.map(record => renderRecord(record))}
  </ModulePanel>;
  const legacyPanel = snapshot.legacyRequests.length > 0 && <ModulePanel className="guild-record-panel guild-legacy-records"><h3>旧版全局认证记录</h3><p className="guild-muted">保留原有申请与审核结果，独立展示；不计入任何新公会的三阶进度。</p>{snapshot.legacyRequests.map(record => renderRecord(record, true))}</ModulePanel>;
  return <div className="guild-growth-page" data-view={view}>
    <div className="guild-growth-heading"><div><span className="module-eyebrow">DELIVERY / GUILD GROWTH</span><h1>{views.find(item => item.id === view)?.title || "交付线公会"}</h1></div><div className="guild-growth-heading-actions">{view === "arena" && activeGuild && <button className="module-secondary" onClick={() => onView("hall")}>切换公会</button>}<span className="guild-session-label">学员 {identity} · {activeGuild ? `已加入：${activeGuild.title}` : "请先选择并加入公会"}</span></div></div>
    <ModulePanel className="guild-growth-hero">
      <div className="guild-rank-emblem" data-grade={current}><span>GUILD PROGRESS</span><strong>{activeGuild ? guildStageNames[current] : "未加入公会"}</strong><small>{activeGuild ? guildLevelNames[current] : "先选择目标公会"}</small></div>
      <div className="guild-growth-intro">{view === "arena" && activeGuild ? <h2>当前公会 · <span>{activeGuild.title}</span></h2> : <><span className="module-eyebrow">{activeGuild ? `当前公会 · ${activeGuild.title}` : "先加入公会，再开始三阶认证"}</span><h2>让每一次进阶，<span>都有任务成果作证。</span></h2></>}<p>{activeGuild ? `当前在「${activeGuild.title}」内按规范实践、协同攻坚、复杂交付三阶推进。` : "请先在下方 8 个公会中选择一个加入，进入对应公会的认证竞技场。"}<br />各公会认证进度独立记录，认证不会扣点或重复发奖。</p></div>
      <div className="guild-growth-numbers"><div><strong>{owned.length}</strong><span>已获得徽章</span></div><div><strong>{covered}<small> / {capabilities.length}</small></strong><span>已有徽章依据的领域</span></div><div><strong>{activeRecords.length}<small> / 3</small></strong><span>当前公会已认证阶段</span></div></div>
      <div className="guild-growth-hero-action">{view !== "arena" && <span>{!activeGuild ? "尚未加入公会 · 共 8 个公会可选" : next ? `下一目标「${guildStageNames[next]}」· 徽章条件 ${nextStatus!.fulfilled}/${nextStatus!.required}` : "已完成当前公会全部阶段"}</span>}<button className="module-primary" disabled={busy} onClick={() => !activeGuild ? onView("hall") : next ? openTarget(next) : onView("certification")}>{!activeGuild ? "先选择要加入的公会" : nextStatus?.eligible ? "核对成果并申请认证" : nextStatus?.entryEligible ? "领取本阶段认证任务" : "查看认证条件"}<ModuleIcon file="b5042" size={16} /></button>{view !== "arena" && <small>{activeGuild ? "在当前公会内逐阶认证" : "加入后开放本公会三阶认证"}</small>}</div>
    </ModulePanel>

    {error && <p className="guild-action-error" role="alert">{error} <button disabled={refreshing || busy} onClick={() => void refresh()}>重新读取</button></p>}
    <div ref={scroll} className="guild-growth-scroll" role="region" tabIndex={0} aria-label="公会内容，可滚动查看">
      {view === "hall" ? <>
        <section className="guild-halls" aria-labelledby="guild-halls-title"><div className="guild-halls-heading"><div><span className="module-eyebrow">EIGHT GUILDS / ONE DELIVERY NETWORK</span><h3 id="guild-halls-title">先选择你要加入的公会</h3><p>七条交付线与一个综合职能公会。加入后在该公会内进行规范实践、协同攻坚、复杂交付三阶认证。</p></div><span>{activeGuild ? `当前公会：${activeGuild.title}` : "尚未加入 · 共 8 个公会"}</span></div><div className="guild-halls-grid">{snapshot.halls.filter(item => `${item.title} ${item.description}`.toLowerCase().includes(search)).map(item => { const joined = snapshot.joinedGuild === item.id; const stage = item.level; return <ModulePanel key={item.id} className={`guild-hall-card${joined ? " is-joined" : ""}`}><div className="module-row"><ModuleIcon pack={guildHallIconPacks[item.icon] || "guild"} file={item.icon} size={24} /><small data-joined={joined}>{joined ? `当前公会 · ${guildStageNames[stage]}` : item.joined ? `已加入 · ${guildStageNames[stage]}` : "未加入"}</small></div><span>{item.type}</span><h4>{item.title}</h4><p>{item.description}</p><button className={joined ? "module-primary" : "module-secondary"} disabled={busy} onClick={() => void selectGuild(item.id, joined)}>{joined ? "进入本公会认证" : item.joined ? "切换回该公会" : "加入该公会"} <ModuleIcon file="b5042" size={14} /></button></ModulePanel>; })}</div>{!snapshot.halls.some(item => `${item.title} ${item.description}`.toLowerCase().includes(search)) && <p className="guild-empty">没有匹配的公会入口，请调整顶部搜索词。</p>}</section>
        <div className="guild-entry-grid">{views.map(item => <ModulePanel key={item.id} className="guild-entry"><ModuleIcon pack="guild" file={item.icon} size={28} /><h3>{item.title}</h3><p>{item.description}</p><button className="module-secondary" onClick={() => onView(item.id)}>进入{item.title} <ModuleIcon file="b5042" size={15} /></button></ModulePanel>)}</div>
        <div className="guild-two-column"><ModulePanel className="guild-next-step"><div className="module-row"><h3>{!activeGuild ? "第一步 · 先加入一个公会" : next ? `${activeGuild.title} · 下一阶段「${guildStageNames[next]}」` : `${activeGuild.title} · 三阶认证已完成`}</h3><span className="module-tag">{!activeGuild ? "待加入公会" : nextStatus?.eligible ? "待申请认证" : nextStatus?.entryEligible ? "待完成认证任务" : next ? "补齐徽章凭证" : "已完成"}</span></div>{next && requirements(next)}<p className="guild-muted">先在上方选择并加入一个公会，再在该公会内完成三阶认证任务；不同公会的认证进度分开保存。</p><div className="guild-next-actions"><button className="module-primary" disabled={!activeGuild} onClick={() => onView("arena")}>{activeGuild ? "进入本公会认证竞技场" : "请先在上方加入公会"}</button><button className="module-secondary" onClick={onBadges}>去查看徽章凭证</button><button className="module-secondary" onClick={onAcademy}>去 AI 学院补强</button></div></ModulePanel>{historyPanel}</div>
        <ModulePanel className="guild-lab-link"><div><span className="module-eyebrow">SIMULATION LAB · 保持现有内容</span><h3>从客户需求到验收 · 完成一次数据交付</h3><p>现有九阶段模拟实验室保持不变，不作为本次额外晋级门槛，也不追加奖励。</p></div><button className="module-secondary" onClick={onLab}>进入模拟实验室 <ModuleIcon file="b5042" size={16} /></button></ModulePanel>
      </> : view === "certification" || view === "capability-map" ? <>
        <ModulePanel className="guild-cert-intro"><h3>能力地图 · {activeGuild ? activeGuild.title : "请先加入公会"}</h3><p>在地图中汇集已获得的徽章，并在所加入的公会内完成当前阶段认证任务。徽章只是准入凭证，不能直接代替任务成果。</p><div><span>01 加入目标公会</span><i /><span>02 汇集徽章凭证</span><i /><span>03 完成本阶段认证任务</span></div><button className="module-primary" onClick={() => activeGuild ? openTarget(next || 3) : onView("hall")}>{!activeGuild ? "去公会大厅选择公会" : next ? `查看「${guildStageNames[next]}」任务` : "查看综合交付任务凭证"}</button></ModulePanel>
        <div className="guild-map-groups" role="group" aria-label="能力地图领域分组">{badgeCatalogGroups.filter(item => item.id !== "all").map(item => <button key={item.id} aria-pressed={group === item.id} className={group === item.id ? "is-active" : ""} onClick={() => { setGroup(item.id); setFocused(capabilities.find(row => row.group === item.id)!.id); }}>{item.name}<span>{capabilities.filter(row => row.group === item.id).length}</span></button>)}</div>
        <div className="guild-map-layout"><ModulePanel className="guild-map-panel"><div className="module-row"><h3>我的能力汇集地图</h3><span>{mapRows.filter(row => row.acquired.length).length} / {mapRows.length} 个领域已有徽章依据</span></div><p className="guild-muted">灰色未获得，蓝 / 紫 / 金分别表示一级 / 二级 / 三级徽章依据；不代表领域已正式认证。点击节点查看凭证。</p>
          <div className="guild-capability-graph">
            <svg viewBox="0 0 1000 620" preserveAspectRatio="none" aria-hidden="true"><ellipse cx="500" cy="310" rx="355" ry="215" /><ellipse cx="500" cy="310" rx="230" ry="140" />{mapRows.map((row, i) => { const angle = i / mapRows.length * Math.PI * 2 - Math.PI / 2; return <line key={row.id} x1="500" y1="310" x2={500 + 355 * Math.cos(angle)} y2={310 + 215 * Math.sin(angle)} className={row.acquired.length ? "is-lit" : ""} />; })}</svg>
            <div className="guild-map-core"><span>MY CAPABILITIES</span><strong>{guildStageNames[current]}</strong><small>{guildLevelNames[current]}</small></div>
            {mapRows.map((row, i) => {
              if (!`${row.name} ${row.entries.map(entry => entry.artwork.name).join(" ")}`.toLowerCase().includes(search)) return null;
              const angle = i / mapRows.length * Math.PI * 2 - Math.PI / 2;
              return <button key={row.id} data-capability={row.id} data-grade={row.highest} aria-pressed={focused === row.id} aria-label={`${row.name}，${gradeNames[row.highest]}，${row.acquired.length} 枚相关徽章`} title={`${row.name}：已获得 ${row.acquired.length}/${row.entries.length} 枚相关徽章`}
                className={`guild-map-node${focused === row.id ? " is-selected" : ""}`} style={{ left: `${50 + 35.5 * Math.cos(angle)}%`, top: `${50 + 34.6774 * Math.sin(angle)}%` }} onClick={() => setFocused(row.id)}>
                <span className="guild-map-orb"><img alt="" src={`/assets/journey-badges/centered-icons/${row.representative.artwork.path}.webp`} /></span><strong>{guildCapabilityLabel(row.id, row.name)}</strong>
              </button>;
            })}
          </div>
          {search && !mapRows.some(row => `${row.name} ${row.entries.map(entry => entry.artwork.name).join(" ")}`.toLowerCase().includes(search)) && <p className="guild-empty">当前分组没有匹配领域，请调整搜索或切换分组。</p>}
        </ModulePanel><ModulePanel className="guild-map-detail"><span className="module-eyebrow">CAPABILITY EVIDENCE</span><h3>{selected.name}</h3><p className="guild-muted">{selected.acquired.length} / {selected.entries.length} 枚相关徽章已获得。只按实际所有权点亮，不读取徽章点余额。</p>
          {selected.entries.map(entry => { const grade = entry.publication && wallet.owned.includes(entry.publication.id) ? guildBadgeGrade(entry.publication) : 0; return <div key={entry.artwork.id} className="guild-map-evidence"><BadgeArtworkImage path={entry.artwork.path} level={grade} /><div><strong>{entry.publication?.name || entry.artwork.name}</strong><small>{grade ? `已获得 · ${gradeNames[grade]}` : entry.publication ? "未获得" : "素材待发布"}</small></div></div>; })}
          <button className="module-secondary" onClick={onBadges}>查看完整徽章图鉴</button><button className="module-secondary" onClick={() => openTarget(next || 3)}>核对公会认证条件</button>
        </ModulePanel></div>
        <div className="guild-two-column guild-cert-evidence">{evidencePanel}{historyPanel}</div>
      </> : view === "arena" ? <>
        {!activeGuild && <div className="guild-arena-heading"><div><h3>认证竞技场 · 请先加入公会</h3><p>请先返回公会大厅，从 7 条交付线或综合职能公会中选择一个加入，再开始该公会的三阶认证。</p></div><button className="module-primary" onClick={() => onView("hall")}>去选择公会</button></div>}
        <div className="guild-arena-grid">{snapshot.tasks.filter(task => task.publicationStatus === "published").map(task => { const status = snapshot.requirements.find(item => item.level === task.level)!; return <ModulePanel key={task.id} className="guild-arena-card" ><span className="guild-arena-rank" data-grade={task.level}>{arenaMemberNames[task.level]}</span><span className="module-eyebrow">G{task.level}</span><h3>{task.title}</h3><p>{task.brief}</p>{requirements(task.level)}<div className="guild-arena-task"><strong>认证任务模板</strong><h4>本阶段实践任务</h4><span>{task.difficulty} · {task.minutes} 分钟</span><p>{task.deliverable}</p></div><div className="guild-arena-count">{status.fulfilled}/{status.required} 项徽章条件已满足 · 认证任务{status.taskSubmitted ? "已提交" : "未完成"}</div><button className={status.eligible ? "module-primary" : "module-secondary"} disabled={busy} onClick={() => openTarget(task.level)}>{current >= task.level ? "查看已认证成果" : guildPendingRequest(snapshot, task.level) ? "查看待审核申请" : status.eligible ? "核对成果 · 申请认证" : status.entryEligible ? "领取本阶段认证任务" : "查看任务准入条件"}</button></ModulePanel>; })}</div>
        <div className="guild-two-column">{evidencePanel}{historyPanel}</div>
      </> : null}
      {legacyPanel}
    </div>
    <div className="guild-growth-note" role="status">{message || "成果、申请和审核记录保存到当前账号，各公会进度独立。管理员审核通过后阶段生效；认证不扣点、不发奖。"}</div>
    <dialog ref={dialog} className="module-dialog journey-dialog guild-cert-dialog" aria-labelledby="guild-cert-title" onCancel={closeTarget}><JourneyDialogSurface>
      <div className="module-dialog-heading"><span className="module-eyebrow">GUILD CERTIFICATION</span><button aria-label="关闭公会认证" onClick={closeTarget}>关闭</button></div>
      {target && check && targetTask && <><h2 id="guild-cert-title">{activeGuild?.title} · {guildStageNames[target]} · {guildLevelNames[target]}</h2><p className="guild-dialog-subtitle">在当前公会完成本阶段认证任务，提交成果并申请；管理员审核通过后才能进入下一阶段。</p>{requirements(target)}
        <div className="guild-dialog-evidence">{evidence.map(badge => <div key={badge.id}>{badgePicture(badge)}<span>{badge.name}<small>{gradeNames[guildBadgeGrade(badge)]}</small></span></div>)}</div>
        <section className="guild-cert-task"><div className="module-row"><span className="module-eyebrow">认证任务模板 · 当前阶段实践任务</span><small>{targetTask.difficulty} · {targetTask.minutes} 分钟</small></div><h3>{targetTask.title}</h3><p>{targetTask.brief}</p><div className="guild-task-mentor">成果由管理端审核，任务模板不代表已通过认证。</div><div className="guild-task-deliverable"><strong>任务交付物</strong><p>{targetTask.deliverable}</p></div>
          <fieldset disabled={!canEdit || busy}><legend>填写认证任务成果</legend><textarea aria-label="认证任务成果" rows={6} maxLength={6000} placeholder="至少 60 字，说明方案、判断依据、责任人与下一步动作。不要填写真实客户敏感信息。" value={taskDraft.artifact} onChange={event => updateDraft({ artifact: event.target.value })} />
          </fieldset>
          <div className="guild-task-submission"><div className="guild-task-save-state" role="status">{taskDraft.artifact.length} / 6,000 字 · {taskChanged ? "有尚未保存的修改" : submittedTask?.status === "submitted" ? "成果已提交" : submittedTask ? "草稿已保存" : "尚未保存成果"}</div>
          {taskError && <p className="guild-task-error" role="alert">{taskError}</p>}
          {draftConflict && <p className="guild-task-error" role="alert">成果已在其他页面或审核后更新，请先载入最新成果。<button className="module-secondary" disabled={busy} onClick={() => { setTaskDrafts(previous => { const updated = { ...previous }; delete updated[scope]; return updated; }); setTaskError(""); }}>载入最新成果（替换未保存内容）</button></p>}
          <div className="guild-task-actions"><button className="module-secondary" disabled={!canEdit || busy || draftConflict} onClick={() => void persistTask(false)}>保存草稿</button><button className="module-secondary" disabled={!canEdit || busy || draftConflict || (submittedTask?.status === "submitted" && !taskChanged)} onClick={() => void persistTask(true)}>{submittedTask?.status === "submitted" && !taskChanged ? "认证任务成果已提交" : "提交任务成果"}</button></div>
          <small>成果保存到当前公会、本阶段；提交任务成果后仍需申请认证，并由管理员审核。</small>
          </div>
        </section>
        {(current >= target || pending || !check.entryEligible) && <p className="guild-dialog-warning">{current >= target ? "本阶段已通过审核，可查看原任务成果与认证记录。" : pending ? `「${guildStageNames[pending.level]}」认证申请正在等待管理员审核，请勿重复提交。` : !check.previousMet ? `请先在本公会通过「${guildStageNames[target - 1]}」阶段审核，不能跳过阶段。` : "徽章条件尚未满足。请先按原有任务与兑换规则获得相应徽章。"}</p>}
        {error && <p className="guild-action-error" role="alert">{error} <button disabled={refreshing || busy} onClick={() => void refresh()}>重新读取</button></p>}
        <div className="guild-dialog-actions"><button className="module-secondary" disabled={busy} onClick={() => { closeTarget(); onBadges(); }}>去查看徽章</button><button className="module-primary" disabled={!canApply || busy || !!error} onClick={async () => { if (activeGuild && submittedTask && await submit(activeGuild.id, target, submittedTask.revision)) { setMessage(`「${activeGuild.title} · ${guildStageNames[target]}」认证申请已提交，等待管理员审核。`); closeTarget(); } }}>{busy ? "正在保存…" : pending ? "申请待审核" : current >= target ? "已通过认证" : "提交认证申请"}</button></div>
      </>}
    </JourneyDialogSurface></dialog>
  </div>;
}
