"use client";

import type { ExplorationTreasureId, ExplorationTreasures } from "@/lib/exploration-treasures";
import "./explorationGraduationTaskCard.css";

const treasureIds = new Set<ExplorationTreasureId>(["compass", "crystal", "starmap", "key"]);

export function ExplorationGraduationTaskCard({ order, treasures, onOpen, loading = false }: {
  order: number;
  treasures?: ExplorationTreasures;
  onOpen: () => void;
  loading?: boolean;
}) {
  const owned = new Set((treasures?.items ?? []).filter(drop => treasureIds.has(drop.treasureId)).map(drop => drop.treasureId)).size;
  const graduation = treasures?.graduation;
  const ready = !loading && graduation?.status === "READY" && !!graduation.code?.trim();
  const available = !loading && owned === 4 && graduation?.status === "AVAILABLE";
  const migrated = !loading && graduation?.status === "MIGRATED";
  const formalAccount = !loading && graduation?.status === "NOT_REQUIRED";
  const status = loading ? "正在读取" : migrated ? "迁移完成" : formalAccount ? "正式账号" : ready ? "已解锁" : available ? "可解锁" : "未解锁";
  const position = Number.isInteger(order) && order > 0 ? order : 1;
  const description = loading ? "正在确认学习与宝藏进度，可以先查看毕业码解锁规则。"
    : available ? "全部任务已完成，四件宝藏已集齐。解锁专属毕业码，开启新的成长之旅。"
    : migrated ? "历史数据已迁移至公司飞书账号。"
    : formalAccount ? "当前为公司飞书账号，无需使用毕业码。"
    : graduation?.blockReason || "完成全部学习、测试审核与培训签退，并集齐 4 件探索宝藏后解锁。";
  const action = migrated || formalAccount ? "查看账号状态 →" : ready ? "查看毕业码 →" : available ? "去解锁 →" : "查看规则 →";
  return <button type="button"
     className={`journey-task-card journey-completion-card exploration-graduation-task-card ${ready || migrated || formalAccount ? "journey-task-completed" : available ? "journey-task-active" : "journey-task-pending"}`}
     data-graduation-order={position} data-graduation-status={loading ? "LOADING" : migrated || formalAccount ? graduation?.status : ready ? "READY" : available ? "AVAILABLE" : "LOCKED"}
    aria-label={`探索营毕业码，${status}，${ready ? "查看毕业码" : available ? "前往解锁" : "查看解锁规则"}`}
    aria-busy={loading || undefined}
    onClick={event => { event.stopPropagation(); onOpen(); }}>
    <span className="journey-task-icon exploration-graduation-task-icon" aria-hidden="true"><svg viewBox="0 0 52 52" fill="none">
      <circle cx="26" cy="26" r="24" stroke="currentColor" strokeOpacity=".3" />
      <circle cx="26" cy="26" r="20" stroke="currentColor" strokeOpacity=".15" strokeDasharray="2 4" />
      <path d="m8 21 18-8 18 8-18 8-18-8Z" fill="currentColor" fillOpacity=".13" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M15 25v10c7 5 15 5 22 0V25m7-4v12m-1 0h2v5h-2v-5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="m26 17 8 4-8 3-8-3 8-4Z" fill="currentColor" fillOpacity=".4" />
    </svg></span>
    <span className="journey-task-status">{status}</span>
    <span className="journey-task-number">{String(position).padStart(2, "0")}</span>
    <span className="journey-task-title">探索营毕业码</span>
    <span className="journey-task-description">{ready ? <><span>毕业码已解锁，点击查看或复制。</span><code className="exploration-graduation-task-code">{graduation?.code}</code></> : description}</span>
    <span className="journey-task-footer"><span>{loading ? "学习进度读取中" : graduation?.totalTasks != null ? `学习 ${graduation.completedTasks ?? 0}/${graduation.totalTasks} · 宝藏 ${owned}/4` : `已探索 ${owned}/4 件宝藏`}</span><strong>{action}</strong></span>
  </button>;
}
