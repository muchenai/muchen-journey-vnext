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
  taskActionUrl,
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
  taskActionUrl: string | null;
}) {
  const initial = splitInitialBody(initialBody);
  const isRevision = command === "submit_revision";
  const documentLaunchUrl = isRevision && initial.evidenceUrl
    ? initial.evidenceUrl
    : taskActionUrl;
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
  const answerPlan = responseSections.length > 0
    ? responseSections
    : ["先写下你的判断", "补上支持判断的证据", "说明下一步或停止条件"];

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
      {isRevision ? (
        <div className="revision-edit-ready" role="status">
          <span aria-hidden="true">✓</span>
          <div>
            <strong>上次提交已经为你载入</strong>
            <small>保留正确的部分，只修改 Reviewer 指出的内容。</small>
          </div>
        </div>
      ) : null}
      <section className="response-map" aria-labelledby="response-map-title">
          <p className="section-label">作答地图</p>
          <h3 id="response-map-title">按这三步，把想法变成证据</h3>
          <ol>
            {answerPlan.map((section, index) => (
              <li key={section}>
                <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                {section}
              </li>
            ))}
          </ol>
      </section>
      {expectsExternalDocument ? (
        <section className="external-document-path" aria-labelledby="external-document-title">
          <p className="section-label">交付通道</p>
          <h3 id="external-document-title">
            {isRevision ? "修改原文档，再提交新版本" : "完成文档，再把链接交给 Reviewer"}
          </h3>
          <ol>
            <li>
              <span aria-hidden="true">01</span>
              <strong>{isRevision ? "继续修改" : "创建副本"}</strong>
              <small>
                {isRevision
                  ? "打开你上次提交的文档，按 Reviewer 反馈修改。"
                  : "先打开本主题题面，再在飞书中创建自己的副本。"}
              </small>
              {documentLaunchUrl ? (
                <a
                  className="external-document-launch"
                  href={documentLaunchUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {isRevision ? "打开我上次提交的文档" : "打开本主题题面"} <i aria-hidden="true">↗</i>
                </a>
              ) : null}
            </li>
            <li>
              <span aria-hidden="true">02</span>
              <strong>{isRevision ? "完成修订" : "完成作答"}</strong>
              <small>{isRevision ? "只改需要调整的部分，不必从头重做。" : "按照上方作答地图写完，不要修改原始题面。"}</small>
            </li>
            <li>
              <span aria-hidden="true">03</span>
              <strong>交付链接</strong>
              <small>
                {isRevision
                  ? "确认下方链接仍能打开，再提交给 Reviewer。"
                  : "从浏览器地址栏复制完整链接，粘贴到下方。"}
              </small>
            </li>
          </ol>
          {documentLaunchUrl ? <p className="external-document-login-hint">首次打开需使用企业飞书登录。</p> : null}
          <label htmlFor="evidence-url">你的飞书文档链接</label>
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
        placeholder={expectsExternalDocument ? "可选：告诉 Reviewer 最需要关注哪一部分" : answerPlan.join("\n\n")}
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
