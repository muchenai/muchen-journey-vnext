"use client";

import { FormEvent, useActionState, useEffect, useRef } from "react";

import { logoutSession, LogoutActionState } from "@/app/actions";

const INITIAL_STATE: LogoutActionState = {};

export function LogoutControl() {
  const [state, formAction, pending] = useActionState(logoutSession, INITIAL_STATE);
  const submittingRef = useRef(false);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!state.error) return;
    submittingRef.current = false;
    errorRef.current?.focus();
  }, [state]);

  function preventDuplicateSubmission(event: FormEvent<HTMLFormElement>) {
    if (submittingRef.current) {
      event.preventDefault();
      return;
    }
    submittingRef.current = true;
  }

  return (
    <section className="quiet-exit" aria-labelledby="logout-session-title">
      <div>
        <h2 id="logout-session-title">结束本次使用</h2>
        <p id="logout-session-help">
          只退出当前浏览器会话，不会删除旅程进度、提交版本或评审记录。再次进入时，请使用运营提供的有效重新进入链接。
        </p>
      </div>
      <form action={formAction} onSubmit={preventDuplicateSubmission}>
        <button
          aria-describedby={`logout-session-help${state.error ? " logout-session-error" : ""}`}
          className="button secondary"
          disabled={pending}
          type="submit"
        >
          {pending ? "正在安全退出……" : "退出 vNext 会话"}
        </button>
      </form>
      <p className="logout-progress" role="status" aria-live="polite">
        {pending ? "正在撤销当前会话，请不要重复点击。" : ""}
      </p>
      {state.error ? (
        <div
          className="inline-error logout-error"
          id="logout-session-error"
          ref={errorRef}
          role="alert"
          tabIndex={-1}
        >
          <strong>{state.error}</strong>
          <span>
            请求 ID：{state.requestId ?? "未生成（请求未到达服务端）"}
          </span>
        </div>
      ) : null}
    </section>
  );
}
