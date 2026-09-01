"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  completeSubmissionAttachmentUpload,
  createSubmissionAttachmentUpload,
  uploadLocalSubmissionAttachment,
} from "@/app/actions";

async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function AttachmentUploader({ assignmentId }: { assignmentId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [requestId, setRequestId] = useState<string>();
  const [status, setStatus] = useState("尚未选择附件。");
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("attachment");
    if (!(input instanceof HTMLInputElement) || !input.files?.[0]) return;
    if (!window.navigator.onLine) {
      setError("当前离线，附件没有开始上传。恢复网络后可重试；正文与草稿不受影响。");
      setStatus("附件未上传；当前离线。");
      return;
    }
    const file = input.files[0];
    setPending(true);
    setError(undefined);
    setRequestId(undefined);
    setStatus("正在计算文件指纹…");
    try {
      const sha256 = await sha256Hex(file);
      setStatus("文件指纹已计算，正在创建受控上传凭证…");
      const created = await createSubmissionAttachmentUpload({
        assignmentId,
        originalFilename: file.name,
        contentType: file.type,
        sizeBytes: file.size,
        sha256,
      });
      if (!created.intent) {
        setError(created.error ?? "上传凭证没有生成，请重试。");
        setRequestId(created.requestId);
        setStatus("附件未上传；上传凭证创建失败。");
        return;
      }
      setStatus("正在上传文件…");
      if (created.intent.upload_url.startsWith("/")) {
        const uploaded = await uploadLocalSubmissionAttachment(created.intent.id, file);
        if (uploaded.error) {
          setError(uploaded.error);
          setRequestId(uploaded.requestId);
          setStatus("附件未就绪；文件上传失败。");
          return;
        }
      } else {
        const response = await fetch(created.intent.upload_url, {
          method: "PUT",
          headers: created.intent.upload_headers,
          body: file,
          credentials: "omit",
          redirect: "error",
          referrerPolicy: "no-referrer",
        });
        if (!response.ok) {
          setError("对象存储没有接受附件；文件仍未绑定，可重新上传。");
          setStatus("附件未就绪；对象存储未接受文件。");
          return;
        }
      }
      setStatus("文件已上传，正在完成安全校验…");
      const completed = await completeSubmissionAttachmentUpload(
        assignmentId,
        created.intent.id,
        file.type,
        file.size,
        sha256,
      );
      if (completed.error) {
        setError(completed.error);
        setRequestId(completed.requestId);
        setStatus("附件未就绪；安全校验未完成。");
        return;
      }
      setStatus("附件已就绪，正在刷新可用附件列表…");
      form.reset();
      router.replace(`/app/tasks/${assignmentId}?attachment=ready`);
      router.refresh();
    } catch {
      setError("附件上传没有完成，请稍后重试。");
      setStatus("附件未就绪；上传过程意外中断。");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <label htmlFor="submission-attachment">选择附件</label>
      <input
        id="submission-attachment"
        name="attachment"
        type="file"
        accept="text/plain,application/pdf,image/png,image/jpeg"
        aria-describedby="attachment-upload-status"
        required
      />
      <p id="attachment-upload-status" className="status-meta" role="status" aria-live="polite">{status}</p>
      <button className="button secondary" type="submit" disabled={pending}>
        {pending ? "正在上传与校验…" : "上传并校验附件"}
      </button>
      {error ? (
        <div ref={errorRef} className="inline-error" role="alert" tabIndex={-1}>
          <strong>附件没有上传</strong>
          <span>{error}</span>
          <span>正文与服务端草稿不受影响；可重新选择文件后重试。</span>
          {requestId ? <code>request ID: {requestId}</code> : null}
        </div>
      ) : null}
    </form>
  );
}
