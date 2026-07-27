"use client";

import { FormEvent, useState } from "react";
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("attachment");
    if (!(input instanceof HTMLInputElement) || !input.files?.[0]) return;
    const file = input.files[0];
    setPending(true);
    setError(undefined);
    setRequestId(undefined);
    try {
      const sha256 = await sha256Hex(file);
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
        return;
      }
      if (created.intent.upload_url.startsWith("/")) {
        const uploaded = await uploadLocalSubmissionAttachment(created.intent.id, file);
        if (uploaded.error) {
          setError(uploaded.error);
          setRequestId(uploaded.requestId);
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
          return;
        }
      }
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
        return;
      }
      form.reset();
      router.replace(`/app/tasks/${assignmentId}?attachment=ready`);
      router.refresh();
    } catch {
      setError("附件上传没有完成，请稍后重试。");
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
        required
      />
      <button className="button secondary" type="submit" disabled={pending}>
        {pending ? "正在上传与校验…" : "上传并校验附件"}
      </button>
      {error ? (
        <div className="inline-error" role="alert">
          <strong>附件没有上传</strong>
          <span>{error}</span>
          <span>正文与服务端草稿不受影响；可重新选择文件后重试。</span>
          {requestId ? <code>request ID: {requestId}</code> : null}
        </div>
      ) : null}
    </form>
  );
}
