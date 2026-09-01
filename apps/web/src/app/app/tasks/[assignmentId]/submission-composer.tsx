"use client";

import { startTransition, useActionState, useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { saveSubmissionDraft, submitAssignment, type SubmissionActionState } from "@/app/actions";
import { FactLabel } from "@/app/human-experience";
import type { Attachment } from "@/lib/server/api";

const INITIAL_STATE: SubmissionActionState = {};
const FEISHU_EVIDENCE_PREFIX = "飞书文档：";

function splitInitialBody(initialBody: string) {
  if (!initialBody.startsWith(FEISHU_EVIDENCE_PREFIX)) {
    return { evidenceUrl: "", notes: initialBody };
  }
  const [firstLine, ...remaining] = initialBody.split("\n");
  return {
    evidenceUrl: firstLine.slice(FEISHU_EVIDENCE_PREFIX.length).trim(),
    notes: remaining.join("\n").replace(/^\s*补充说明：\s*/u, "").trimStart(),
  };
}

const FIRST_WIN_DIAGNOSTICS = {
  direction: { label: "方向很多，不知道先做什么", judgement: "你现在缺的不是更多选项，而是一个可验证的优先级。", experiment: "选出影响最大的一个问题；写下 24 小时内能找到的最小证据，并约定何时回看。" },
  evidence: { label: "有判断，但不知道怎么验证", judgement: "你的起点判断已经存在，下一步要把它变成别人也能核对的证据。", experiment: "把判断改写成“如果……那么……”；找一条支持证据和一条反例，明天同一时间复核。" },
  uncertainty: { label: "遇到不确定，容易自己硬猜", judgement: "真正的风险不是不确定，而是没有把已知、未知和求助问题分开。", experiment: "下一次卡住时只写三行：已知事实、我的初判、需要谁回答的一个具体问题。" },
  action: { label: "知道很多，但迟迟没有行动", judgement: "你需要的不是更完整的计划，而是一个小到今天能结束的动作。", experiment: "把目标缩成 20 分钟版本；完成后只记录结果、意外和下一次要改的一件事。" },
} as const;

type FirstWinKey = keyof typeof FIRST_WIN_DIAGNOSTICS;
type LocalDraft = { body: string; evidenceUrl: string; attachmentIds: string[]; savedAt: string };

function snapshot(body: string, evidenceUrl: string, attachmentIds: string[]) {
  return JSON.stringify({ body, evidenceUrl, attachmentIds: [...attachmentIds].sort() });
}

function subscribeToNetworkState(onChange: () => void) {
  window.addEventListener("offline", onChange);
  window.addEventListener("online", onChange);
  return () => {
    window.removeEventListener("offline", onChange);
    window.removeEventListener("online", onChange);
  };
}

function onlineSnapshot() {
  return window.navigator.onLine;
}

function serverOnlineSnapshot() {
  return true;
}

export function SubmissionComposer({
  assignmentId,
  assignmentRevision,
  command,
  initialBody,
  initialAttachmentIds,
  attachments,
  submissionIdempotencyKey,
  initialDraftRevision,
  initialDraftUpdatedAt,
  responseSections,
  requiresReview,
  isFirstStation,
  taskVersion,
  rubricVersion,
  reviewerName,
  visibility,
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
  initialDraftRevision: number | null;
  initialDraftUpdatedAt: string | null;
  responseSections: string[];
  requiresReview: boolean;
  isFirstStation: boolean;
  taskVersion: number;
  rubricVersion: number;
  reviewerName: string;
  visibility: string;
  expectsExternalDocument: boolean;
  taskActionUrl: string | null;
}) {
  const initial = splitInitialBody(initialBody);
  const isRevision = command === "submit_revision";
  const documentLaunchUrl = isRevision && initial.evidenceUrl
    ? initial.evidenceUrl
    : taskActionUrl;
  const storageKey = `muchen-journey:draft:${assignmentId}:${assignmentRevision}`;
  const formRef = useRef<HTMLFormElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const confirmationHeadingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const pendingSnapshot = useRef<string | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState(snapshot(initial.notes, initial.evidenceUrl, initialAttachmentIds));
  const [body, setBody] = useState(initial.notes);
  const [evidenceUrl, setEvidenceUrl] = useState(initial.evidenceUrl);
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState(initialAttachmentIds);
  const [firstWinKey, setFirstWinKey] = useState<FirstWinKey | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<LocalDraft | null>(null);
  const [storageReady, setStorageReady] = useState(false);
  const isOnline = useSyncExternalStore(subscribeToNetworkState, onlineSnapshot, serverOnlineSnapshot);
  const [learnerAiUsed, setLearnerAiUsed] = useState(false);
  const [learnerAiPurpose, setLearnerAiPurpose] = useState("");
  const [learnerAiModelVersion, setLearnerAiModelVersion] = useState("");
  const [learnerAiPromptVersion, setLearnerAiPromptVersion] = useState("");
  const [submitState, submitAction, submitPending] = useActionState(submitAssignment, INITIAL_STATE);
  const [draftState, draftAction, draftPending] = useActionState(saveSubmissionDraft, INITIAL_STATE);
  const currentSnapshot = snapshot(body, evidenceUrl, selectedAttachmentIds);
  const errorState = submitState.error ? submitState : draftState;
  const firstWin = firstWinKey ? FIRST_WIN_DIAGNOSTICS[firstWinKey] : null;

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const stored = window.localStorage.getItem(storageKey);
        if (stored) {
          const parsed = JSON.parse(stored) as LocalDraft;
          if (typeof parsed.body === "string" && typeof parsed.evidenceUrl === "string" && Array.isArray(parsed.attachmentIds) && snapshot(parsed.body, parsed.evidenceUrl, parsed.attachmentIds) !== savedSnapshot) {
            setRecovery(parsed);
          }
        }
      } catch {
        // Invalid old data or unavailable storage must not block the server-backed flow.
      }
      setStorageReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [savedSnapshot, storageKey]);

  useEffect(() => {
    if (!storageReady || currentSnapshot === savedSnapshot) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ body, evidenceUrl, attachmentIds: selectedAttachmentIds, savedAt: new Date().toISOString() } satisfies LocalDraft));
    } catch {
      // The explicit server save remains available when local storage is unavailable.
    }
  }, [body, currentSnapshot, evidenceUrl, savedSnapshot, selectedAttachmentIds, storageKey, storageReady]);

  const saveDraft = useCallback(() => {
    if (!formRef.current || !isOnline || draftPending || currentSnapshot === savedSnapshot) return;
    const data = new FormData(formRef.current);
    data.set("body", body);
    data.set("evidence_url", evidenceUrl);
    data.set("draft_idempotency_key", crypto.randomUUID());
    data.delete("attachment_ids");
    selectedAttachmentIds.forEach((id) => data.append("attachment_ids", id));
    pendingSnapshot.current = currentSnapshot;
    startTransition(() => draftAction(data));
  }, [body, currentSnapshot, draftAction, draftPending, evidenceUrl, isOnline, savedSnapshot, selectedAttachmentIds]);

  useEffect(() => {
    if (!storageReady || !isOnline || confirming || currentSnapshot === savedSnapshot) return;
    const timer = window.setTimeout(saveDraft, 1_200);
    return () => window.clearTimeout(timer);
  }, [confirming, currentSnapshot, isOnline, saveDraft, savedSnapshot, storageReady]);

  useEffect(() => {
    if (!draftState.savedAt || !pendingSnapshot.current) return;
    const committedSnapshot = pendingSnapshot.current;
    setSavedSnapshot(committedSnapshot);
    pendingSnapshot.current = null;
    if (currentSnapshot === committedSnapshot) {
      try {
        window.localStorage.removeItem(storageKey);
      } catch {
        // A stale copy will be offered for explicit recovery on a later visit.
      }
    }
  }, [currentSnapshot, draftState.savedAt, storageKey]);

  useEffect(() => {
    if (confirming) confirmationHeadingRef.current?.focus();
  }, [confirming]);

  useEffect(() => {
    if (localError || errorState.error) errorRef.current?.focus();
  }, [errorState.error, localError]);

  function beginConfirmation() {
    if ((!expectsExternalDocument && body.trim().length < 40) || body.length > 8_000) {
      setLocalError("提交内容需为 40–8000 个字符；当前内容仍保留。");
      return;
    }
    if (expectsExternalDocument && !evidenceUrl.trim()) {
      setLocalError("请先粘贴飞书文档链接，再提交给 Reviewer。");
      return;
    }
    if (learnerAiUsed && (!learnerAiPurpose.trim() || !learnerAiModelVersion.trim() || !learnerAiPromptVersion.trim())) {
      setLocalError("使用 AI 时必须填写用途、模型版本和 Prompt 版本。");
      return;
    }
    setLocalError(null);
    setConfirming(true);
  }

  function restoreLocalDraft() {
    if (!recovery) return;
    setBody(recovery.body);
    setEvidenceUrl(recovery.evidenceUrl);
    setSelectedAttachmentIds(recovery.attachmentIds.filter((id) => attachments.some((attachment) => attachment.id === id)));
    setRecovery(null);
    window.requestAnimationFrame(() => bodyRef.current?.focus());
  }

  function returnToEditing() {
    setConfirming(false);
    window.requestAnimationFrame(() => bodyRef.current?.focus());
  }

  return (
    <form ref={formRef} action={submitAction} className="submission-composer">
      <input type="hidden" name="assignment_id" value={assignmentId} />
      <input type="hidden" name="revision" value={assignmentRevision} />
      <input type="hidden" name="submission_idempotency_key" value={submissionIdempotencyKey} />
      <input type="hidden" name="learner_ai_used" value={learnerAiUsed ? "on" : ""} />
      <input type="hidden" name="learner_ai_purpose" value={learnerAiPurpose} />
      <input type="hidden" name="learner_ai_model_version" value={learnerAiModelVersion} />
      <input type="hidden" name="learner_ai_prompt_version" value={learnerAiPromptVersion} />
      <input type="hidden" name="evidence_url_required" value={expectsExternalDocument ? "true" : "false"} />

      {recovery ? (
        <aside className="draft-recovery" role="status">
          <strong>本浏览器有一份未同步副本</strong>
          <p>保存于 {new Date(recovery.savedAt).toLocaleString("zh-CN")}。它不会自动覆盖服务器草稿。</p>
          <div className="action-row">
            <button className="button secondary" type="button" onClick={restoreLocalDraft}>恢复本地副本</button>
            <button className="button secondary" type="button" onClick={() => setRecovery(null)}>保留服务器版本</button>
          </div>
        </aside>
      ) : null}

      {!confirming ? (
        <>
          {isFirstStation ? (
            <fieldset className="first-win-diagnostic">
              <legend><span>60 秒起点判断</span>你现在最真实的卡点是什么？</legend>
              <p>选一个最接近的处境。这里不评分，也不会作为绩效结论。</p>
              <div className="first-win-options">
                {(Object.entries(FIRST_WIN_DIAGNOSTICS) as Array<[FirstWinKey, (typeof FIRST_WIN_DIAGNOSTICS)[FirstWinKey]]>).map(([key, item]) => (
                  <button className={firstWinKey === key ? "is-selected" : ""} type="button" aria-pressed={firstWinKey === key} onClick={() => setFirstWinKey(key)} key={key}>{item.label}</button>
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
            <section className="response-map" aria-labelledby="response-map-title">
              <strong id="response-map-title">输出结构</strong>
              <ol>{responseSections.map((section) => <li key={section}>{section}</li>)}</ol>
            </section>
          ) : null}

          {isRevision ? (
            <div className="revision-edit-ready" role="status">
              <span aria-hidden="true">✓</span>
              <div>
                <strong>上次提交已经为你载入</strong>
                <small>保留正确的部分，只修改 Reviewer 指出的内容。</small>
              </div>
            </div>
          ) : null}

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
                  <small>{isRevision ? "打开你上次提交的文档，按 Reviewer 反馈修改。" : "先打开本主题题面，再在飞书中创建自己的副本。"}</small>
                  {documentLaunchUrl ? (
                    <a className="external-document-launch" href={documentLaunchUrl} target="_blank" rel="noreferrer">
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
                  <small>{isRevision ? "确认下方链接仍能打开，再提交给 Reviewer。" : "从浏览器地址栏复制完整链接，粘贴到下方。"}</small>
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

          <label htmlFor="submission-body">{expectsExternalDocument ? "补充说明（可选）" : requiresReview ? "你的作答" : "你的学习记录"}</label>
          <textarea ref={bodyRef} id="submission-body" name="body" minLength={expectsExternalDocument ? undefined : 40} maxLength={8000} required={!expectsExternalDocument} aria-describedby="submission-body-help submission-save-status" placeholder={expectsExternalDocument ? "可选：告诉 Reviewer 最需要关注哪一部分" : responseSections.join("\n\n")} value={body} onChange={(event) => setBody(event.target.value)} />
          <p id="submission-body-help" className="status-meta">40–8000 字符。编辑会先保留本地副本，再尝试同步服务器草稿。</p>

          <section className="ai-self-check-gated" aria-labelledby="ai-self-check-title">
            <FactLabel kind="ai" />
            <h3 id="ai-self-check-title">AI 自查（当前不可用）</h3>
            <p>尚未绑定经批准的模型、Prompt 和版本记录，因此失败关闭；不会生成评价，也不会改变任务状态。</p>
            <dl>
              <div><dt>模型版本</dt><dd>模型版本：未绑定</dd></div>
              <div><dt>Prompt 版本</dt><dd>Prompt 版本：未绑定</dd></div>
            </dl>
            <button className="button secondary" type="button" onClick={() => document.querySelector<HTMLButtonElement>("#review-submission")?.focus()}>跳过 AI 自查</button>
          </section>

          <details className="fixed-references">
            <summary>披露你是否使用过其他 AI</summary>
            <label className="attachment-choice"><input type="checkbox" checked={learnerAiUsed} onChange={(event) => setLearnerAiUsed(event.target.checked)} /><span>我在本次作答中使用了 AI；AI 输出只是建议，最终内容由我确认。</span></label>
            <label>AI 用途<input value={learnerAiPurpose} onChange={(event) => setLearnerAiPurpose(event.target.value)} maxLength={200} /></label>
            <label>模型版本<input value={learnerAiModelVersion} onChange={(event) => setLearnerAiModelVersion(event.target.value)} maxLength={200} /></label>
            <label>Prompt 版本<input value={learnerAiPromptVersion} onChange={(event) => setLearnerAiPromptVersion(event.target.value)} maxLength={200} /></label>
            <p className="status-meta">勾选使用 AI 后，三项来源必须全部填写。</p>
          </details>

          {attachments.length > 0 ? (
            <fieldset>
              <legend>本次使用的 READY 附件</legend>
              {attachments.map((attachment) => (
                <label className="attachment-choice" key={attachment.id}>
                  <input type="checkbox" name="attachment_ids" value={attachment.id} checked={selectedAttachmentIds.includes(attachment.id)} onChange={(event) => setSelectedAttachmentIds((current) => event.target.checked ? [...current, attachment.id] : current.filter((id) => id !== attachment.id))} />
                  <span>{attachment.original_filename} · {Math.ceil(attachment.size_bytes / 1024)} KiB</span>
                </label>
              ))}
            </fieldset>
          ) : null}
        </>
      ) : (
        <section className="submission-confirmation" aria-labelledby="submission-confirmation-title">
          <FactLabel kind="system" />
          <p className="section-label">最终确认</p>
          <h3 ref={confirmationHeadingRef} id="submission-confirmation-title" tabIndex={-1}>确认提交的是固定版本</h3>
          <p>{requiresReview ? "提交后进入人工审核，等待具名 Reviewer 结论。" : "提交后形成本阶段的完成事实，不产生人才结论。"}</p>
          <dl>
            <div><dt>任务版本</dt><dd>v{taskVersion}</dd></div>
            <div><dt>Rubric 版本</dt><dd>v{rubricVersion}</dd></div>
            <div><dt>Reviewer</dt><dd>{reviewerName}</dd></div>
            <div><dt>可见范围</dt><dd>{visibility}</dd></div>
            <div><dt>附件</dt><dd>{selectedAttachmentIds.length} 个 READY 文件</dd></div>
            <div><dt>AI 披露</dt><dd>{learnerAiUsed ? `${learnerAiPurpose} · ${learnerAiModelVersion} · ${learnerAiPromptVersion}` : "未使用"}</dd></div>
          </dl>
          <div className="submission-preview"><strong>提交正文</strong><p>{body}</p></div>
          {evidenceUrl ? <div className="submission-preview"><strong>飞书文档</strong><p>{evidenceUrl}</p></div> : null}
          <input type="hidden" name="body" value={body} />
          <input type="hidden" name="evidence_url" value={evidenceUrl} />
          {selectedAttachmentIds.map((id) => <input key={id} type="hidden" name="attachment_ids" value={id} />)}
        </section>
      )}

      {localError || errorState.error ? (
        <div ref={errorRef} className="inline-error" role="alert" tabIndex={-1}>
          <strong>操作没有完成</strong><span>{localError ?? errorState.error}</span>
          {errorState.requestId ? <code>request ID: {errorState.requestId}</code> : null}
        </div>
      ) : null}

      <p id="submission-save-status" className="draft-save-status" role="status" aria-live="polite">
        {!isOnline ? "当前离线：修改已保留为本浏览器未同步副本；恢复网络后再保存或正式提交。" : draftPending ? "正在自动保存到服务器…" : draftState.savedAt ? `已自动保存到服务器 · 草稿 revision ${draftState.draftRevision} · ${new Date(draftState.savedAt).toLocaleString("zh-CN")}` : initialDraftUpdatedAt ? `服务器草稿 revision ${initialDraftRevision} · ${new Date(initialDraftUpdatedAt).toLocaleString("zh-CN")}` : "尚未保存；编辑后会自动保存到服务器，并保留本地恢复副本。"}
      </p>

      <div className="action-row">
        {!isOnline ? <span className="sticky-action-status" aria-hidden="true">离线 · 正式提交已暂停</span> : null}
        {confirming ? (
          <>
            <button className="button primary" type="submit" disabled={submitPending || draftPending || !isOnline}>{submitPending ? "正在提交…" : "确认正式提交"}</button>
            <button className="button secondary" type="button" onClick={returnToEditing} disabled={submitPending}>返回修改</button>
          </>
        ) : (
          <>
            <button
              id="review-submission"
              className="button primary"
              type="button"
              onClick={(event) => {
                event.preventDefault();
                beginConfirmation();
              }}
              disabled={submitPending || draftPending}
            >
              检查并提交
            </button>
            <button className="button secondary" type="button" onClick={saveDraft} disabled={submitPending || draftPending || !isOnline || currentSnapshot === savedSnapshot}>{draftPending ? "正在保存…" : "保存草稿"}</button>
          </>
        )}
      </div>
      <p className="status-meta">{command === "submit_revision" ? "本次会追加修订版本；旧版本保持只读。" : "正式提交会创建不可变 SubmissionVersion。"}</p>
    </form>
  );
}
