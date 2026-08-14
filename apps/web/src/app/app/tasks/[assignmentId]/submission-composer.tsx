"use client";

import { useActionState, useState } from "react";

import {
  saveSubmissionDraft,
  submitAssignment,
  SubmissionActionState,
} from "@/app/actions";
import { Attachment } from "@/lib/server/api";

const INITIAL_STATE: SubmissionActionState = {};
const FEISHU_EVIDENCE_PREFIX = "飞书文档：";

function splitInitialBody(initialBody: string) {
  if (!initialBody.startsWith(FEISHU_EVIDENCE_PREFIX)) {
    return { evidenceUrl: "", notes: initialBody };
  }
  const [firstLine, ...remaining] = initialBody.split("\n");
  const notes = remaining.join("\n").replace(/^\s*补充说明：\s*/u, "").trimStart();
  return {
    evidenceUrl: firstLine.slice(FEISHU_EVIDENCE_PREFIX.length).trim(),
    notes,
  };
}

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
  expectsExternalDocument,
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
  expectsExternalDocument: boolean;
}) {
  const initial = splitInitialBody(initialBody);
  const [body, setBody] = useState(initial.notes);
  const [evidenceUrl, setEvidenceUrl] = useState(initial.evidenceUrl);
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
      <input
        type="hidden"
        name="evidence_url_required"
        value={expectsExternalDocument ? "true" : "false"}
      />
      {responseSections.length > 0 ? (
        <details className="response-map">
          <summary>查看作答结构</summary>
          <ol>
            {responseSections.map((section) => <li key={section}>{section}</li>)}
          </ol>
        </details>
      ) : null}
      {expectsExternalDocument ? (
        <section className="external-document-path" aria-labelledby="external-document-title">
          <p className="section-label">交付入口</p>
          <h3 id="external-document-title">把你的飞书文档交到这里</h3>
          <ol>
            <li>打开题面提供的飞书文件；需要独立编辑时，在飞书中创建自己的副本。</li>
            <li>完成作答后，从浏览器地址栏复制完整文档链接。</li>
            <li>粘贴到下方并提交；Reviewer 将从该链接查看固定作答。</li>
          </ol>
          <label htmlFor="evidence-url">飞书文档链接</label>
          <input
            id="evidence-url"
            name="evidence_url"
            type="url"
            inputMode="url"
            autoComplete="off"
            placeholder="https://…feishu.cn/…"
            value={evidenceUrl}
            onChange={(event) => setEvidenceUrl(event.target.value)}
            required
          />
        </section>
      ) : null}
      <label htmlFor="submission-body">
        {expectsExternalDocument
          ? "补充说明（可选）"
          : requiresReview
            ? "你的作答"
            : "你的学习记录"}
      </label>
      <textarea
        id="submission-body"
        name="body"
        minLength={expectsExternalDocument ? undefined : 40}
        maxLength={8000}
        required={!expectsExternalDocument}
        placeholder={expectsExternalDocument ? "可补充说明文档中的重点或需要 Reviewer 特别关注的内容" : responseSections.join("\n\n")}
        value={body}
        onChange={(event) => setBody(event.target.value)}
      />
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
