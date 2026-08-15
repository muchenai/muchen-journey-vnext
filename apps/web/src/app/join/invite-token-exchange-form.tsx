"use client";

import { useEffect, useSyncExternalStore } from "react";

import { acceptInvite } from "@/app/actions";

let capturedToken = "";
let capturedFlow = "";

function readFragmentState(): string {
  if (typeof window !== "undefined") {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const fragmentToken = fragment.get("token") ?? "";
    if (fragmentToken) capturedToken = fragmentToken;
    if (fragment.get("flow") === "reentry") capturedFlow = "reentry";
  }
  return `${capturedToken}\n${capturedFlow}`;
}

function subscribeToFragment(onChange: () => void): () => void {
  const notify = () => onChange();
  const pendingUpdate = window.setTimeout(notify, 0);
  window.addEventListener("hashchange", notify);
  return () => {
    window.clearTimeout(pendingUpdate);
    window.removeEventListener("hashchange", notify);
  };
}

export function InviteTokenExchangeForm() {
  const fragmentState = useSyncExternalStore(subscribeToFragment, readFragmentState, () => "\n");
  const [token, flow] = fragmentState.split("\n");
  const isReentry = flow === "reentry";

  useEffect(() => {
    if (token) {
      window.history.replaceState(null, "", "/join");
    }
    return () => {
      capturedToken = "";
      capturedFlow = "";
    };
  }, [token]);

  if (!token) {
    return <p className="notice">请使用完整邀请链接进入。</p>;
  }

  return (
    <form action={acceptInvite} className="join-pass">
      <input type="hidden" name="token" value={token} />
      <span className="join-pass-label">Muchen Journey · 邀请</span>
      <h2>{isReentry ? "继续未完成的旅程" : "准备好，从第一站开始"}</h2>
      {!isReentry ? (
        <>
          <label htmlFor="display-name">你希望显示的称呼</label>
          <input id="display-name" name="display_name" minLength={1} maxLength={120} required />
        </>
      ) : (
        <p className="status-meta">恢复原有进度，不会创建新的学习记录。</p>
      )}
      <label className="consent-row">
        <input type="checkbox" name="accepted_purpose" value="yes" required />
        我确认这是我的邀请
      </label>
      <button className="button primary" type="submit">
        {isReentry ? "回到旅程" : "走进第一站"}
      </button>
    </form>
  );
}
