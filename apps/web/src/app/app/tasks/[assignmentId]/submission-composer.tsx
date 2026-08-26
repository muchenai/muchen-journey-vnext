"use client";

import { useActionState, useState } from "react";

import {
  saveSubmissionDraft,
  submitAssignment,
  SubmissionActionState,
} from "@/app/actions";
import { Attachment } from "@/lib/server/api";

const INITIAL_STATE: SubmissionActionState = {};

const FIRST_WIN_DIAGNOSTICS = {
  direction: {
    label: "方向很多，不知道先做什么",
    judgement: "你现在缺的不是更多选项，而是一个可验证的优先级。",
    experiment: "选出影响最大的一个问题；写下 24 小时内能找到的最小证据，并约定何时回看。",
  },
  evidence: {
    label: "有判断，但不知道怎么验证",
    judgement: "你的起点判断已经存在，下一步要把它变成别人也能核对的证据。",
    experiment: "把判断改写成“如果……那么……”；找一条支持证据和一条反例，明天同一时间复核。",
  },
  uncertainty: {
    label: "遇到不确定，容易自己硬猜",
    judgement: "真正的风险不是不确定，而是没有把已知、未知和求助问题分开。",
    experiment: "下一次卡住时只写三行：已知事实、我的初判、需要谁回答的一个具体问题。",
  },
  action: {
    label: "知道很多，但迟迟没有行动",
    judgement: "你需要的不是更完整的计划，而是一个小到今天能结束的动作。",
    experiment: "把目标缩成 20 分钟版本；完成后只记录结果、意外和下一次要改的一件事。",
  },
} as const;

type FirstWinKey = keyof typeof FIRST_WIN_DIAGNOSTICS;

export function SubmissionComposer({
  assignmentId,
  assignmentRevision,
  command,
  initialBody,
  initialAttachmentIds,
  attachments,
  submissionIdempotencyKey,
  draftIdempotencyKey,
  responseSections,
  requiresReview,
  isFirstStation,
}: {
  assignmentId: string;
  assignmentRevision: number;
  command: string;
  initialBody: string;
  initialAttachmentIds: string[];
  attachments: Attachment[];
  submissionIdempotencyKey: string;
  draftIdempotencyKey: string;
  responseSections: string[];
  requiresReview: boolean;
  isFirstStation: boolean;
}) {
  const [body, setBody] = useState(initialBody);
  const [firstWinKey, setFirstWinKey] = useState<FirstWinKey | null>(null);
  const [submitState, submitAction, submitPending] = useActionState(
    submitAssignment,
    INITIAL_STATE,
  );
  const [draftState, draftAction, draftPending] = useActionState(
    saveSubmissionDraft,
    INITIAL_STATE,
  );
  const errorState = submitState.error ? submitState : draftState;
  const firstWin = firstWinKey ? FIRST_WIN_DIAGNOSTICS[firstWinKey] : null;

  return (
    <form action={submitAction}>
      <input type="hidden" name="assignment_id" value={assignmentId} />
      <input type="hidden" name="revision" value={assignmentRevision} />
      <input
        type="hidden"
        name="submission_idempotency_key"
        value={submissionIdempotencyKey}
      />
      <input type="hidden" name="draft_idempotency_key" value={draftIdempotencyKey} />
      {isFirstStation ? (
        <fieldset className="first-win-diagnostic">
          <legend><span>60 秒起点判断</span>你现在最真实的卡点是什么？</legend>
          <p>选一个最接近的处境。这里不评分，也不会作为绩效结论。</p>
          <div className="first-win-options">
            {(Object.entries(FIRST_WIN_DIAGNOSTICS) as Array<[FirstWinKey, typeof FIRST_WIN_DIAGNOSTICS[FirstWinKey]]>).map(([key, item]) => (
              <button
                className={firstWinKey === key ? "is-selected" : ""}
                type="button"
                aria-pressed={firstWinKey === key}
                onClick={() => setFirstWinKey(key)}
                key={key}
              >
                {item.label}
              </button>
            ))}
          </div>
          {firstWin ? (
            <div className="first-win-result" role="status">
              <p><span>起点判断</span><strong>{firstWin.judgement}</strong></p>
              <p><span>今天的实验</span><strong>{firstWin.experiment}</strong></p>
              <small>把这个实验写进下方学习记录；完成后再用真实结果修正判断。</small>
            </div>
          ) : null}
        </fieldset>
      ) : null}
      {responseSections.length > 0 ? (
        <div className="response-map" aria-labelledby="response-map-title">
          <strong id="response-map-title">输出结构</strong>
          <ol>
            {responseSections.map((section) => <li key={section}>{section}</li>)}
          </ol>
        </div>
      ) : null}
      <label htmlFor="submission-body">{requiresReview ? "你的作答" : "你的学习记录"}</label>
      <textarea
        id="submission-body"
        name="body"
        minLength={40}
        maxLength={8000}
        required
        placeholder={responseSections.join("\n\n")}
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
      <p className="status-meta">草稿会安全保存；提交后保留原始版本。</p>

      <details className="fixed-references">
        <summary>AI 使用披露</summary>
        <label className="attachment-choice">
          <input type="checkbox" name="learner_ai_used" />
          <span>我在本次作答中使用了 AI；AI 输出只是建议，最终内容由我确认。</span>
        </label>
        <label>AI 用途<input name="learner_ai_purpose" maxLength={200} /></label>
        <label>模型版本<input name="learner_ai_model_version" maxLength={200} /></label>
        <label>Prompt 版本<input name="learner_ai_prompt_version" maxLength={200} /></label>
        <p className="status-meta">勾选使用 AI 后，三项来源必须全部填写。</p>
      </details>

      {attachments.length > 0 ? (
        <fieldset>
          <legend>本次使用的 READY 附件</legend>
          {attachments.map((attachment) => (
            <label className="attachment-choice" key={attachment.id}>
              <input
                type="checkbox"
                name="attachment_ids"
                value={attachment.id}
                defaultChecked={initialAttachmentIds.includes(attachment.id)}
              />
              <span>
                {attachment.original_filename} · {Math.ceil(attachment.size_bytes / 1024)} KiB
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {errorState.error ? (
        <div className="inline-error" role="alert">
          <strong>操作没有完成</strong>
          <span>{errorState.error}</span>
          {errorState.requestId ? <code>request ID: {errorState.requestId}</code> : null}
        </div>
      ) : null}

      <div className="action-row">
        <button className="button primary" type="submit" disabled={submitPending || draftPending}>
          {submitPending
            ? "正在提交…"
            : command === "submit_revision"
              ? "提交修订版本"
              : requiresReview
                ? "交给 Reviewer"
                : "完成这一站"}
        </button>
        <button
          className="button secondary"
          type="submit"
          formAction={draftAction}
          formNoValidate
          disabled={submitPending || draftPending}
        >
          {draftPending ? "正在保存…" : "保存草稿"}
        </button>
      </div>
    </form>
  );
}
