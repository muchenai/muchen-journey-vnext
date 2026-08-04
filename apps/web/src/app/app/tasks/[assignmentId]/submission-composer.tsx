"use client";

import { useActionState, useState } from "react";

import {
  saveSubmissionDraft,
  submitAssignment,
  SubmissionActionState,
} from "@/app/actions";
import { Attachment } from "@/lib/server/api";

const INITIAL_STATE: SubmissionActionState = {};

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
}) {
  const [body, setBody] = useState(initialBody);
  const [submitState, submitAction, submitPending] = useActionState(
    submitAssignment,
    INITIAL_STATE,
  );
  const [draftState, draftAction, draftPending] = useActionState(
    saveSubmissionDraft,
    INITIAL_STATE,
  );
  const errorState = submitState.error ? submitState : draftState;

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
