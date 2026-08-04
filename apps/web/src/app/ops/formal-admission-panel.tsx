"use client";

import { useActionState } from "react";

import {
  AdmissionPreviewActionState,
  createFormalAdmissionDecision,
  previewFormalAdmission,
} from "@/app/actions";

const INITIAL_STATE: AdmissionPreviewActionState = {};

const SCORE_FIELDS = [
  ["attendance_discipline", "出勤与纪律"],
  ["muchener_understanding", "Muchener 理解"],
  ["ai_data_fundamentals", "AI 数据基础"],
  ["project_organization_fit", "项目与组织适配"],
] as const;

export function FormalAdmissionPanel({ enrollmentId }: { enrollmentId: string }) {
  const [state, previewAction, pending] = useActionState(
    previewFormalAdmission,
    INITIAL_STATE,
  );

  if (!state.scores || state.totalScore === undefined) {
    return (
      <form action={previewAction} className="ops-command-form admission-form">
        <input type="hidden" name="enrollment_id" value={enrollmentId} />
        <div className="admission-score-grid">
          {SCORE_FIELDS.map(([key, label]) => (
            <label key={key}>
              {label}（0–10）
              <input name={key} type="number" min={0} max={10} step={1} required />
            </label>
          ))}
        </div>
        <button className="button secondary compact" type="submit" disabled={pending}>
          {pending ? "正在计算…" : "只读预览 100 分评分"}
        </button>
        {state.error ? <p className="inline-error" role="alert">{state.error}</p> : null}
      </form>
    );
  }

  return (
    <form action={createFormalAdmissionDecision} className="ops-command-form admission-form">
      <input type="hidden" name="enrollment_id" value={enrollmentId} />
      {SCORE_FIELDS.map(([key]) => (
        <input key={key} type="hidden" name={key} value={state.scores?.[key]} />
      ))}
      <div className="admission-preview" role="status">
        <strong>{state.totalScore} / 100 · {state.recommendationTier} 档</strong>
        <span>系统建议：{state.recommendedDecision}（仅供人工参考）</span>
      </div>
      <label>
        四项人工分的事实依据
        <textarea name="score_evidence" minLength={20} maxLength={2000} required />
      </label>
      <label>
        人工准入结论
        <select name="decision" required defaultValue={state.recommendedDecision}>
          <option value="ADMIT">准入下一阶段</option>
          <option value="DEFER">暂缓，补充人工复核</option>
          <option value="NOT_ADMIT">本次不准入</option>
        </select>
      </label>
      <label>
        决定理由
        <textarea name="decision_reason" minLength={20} maxLength={2000} required />
      </label>
      <label>
        与系统建议不一致时的覆盖理由
        <textarea name="override_reason" minLength={20} maxLength={2000} />
      </label>
      <label className="checkbox-row">
        <input name="human_judgement_acknowledged" type="checkbox" required />
        我确认分数只是证据之一；该不可变准入结论由我本人作出并承担责任
      </label>
      <button className="button primary compact" type="submit">记录不可变人工结论</button>
    </form>
  );
}
