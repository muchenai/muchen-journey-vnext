"use client";

import { useEffect, useSyncExternalStore } from "react";

import { exchangeInvite } from "@/app/actions";

let capturedToken = "";

function readFragmentToken(): string {
  if (typeof window !== "undefined") {
    const fragmentToken = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
    if (fragmentToken) capturedToken = fragmentToken;
  }
  return capturedToken;
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
  const token = useSyncExternalStore(subscribeToFragment, readFragmentToken, () => "");

  useEffect(() => {
    if (token) {
      window.history.replaceState(null, "", "/join");
    }
    return () => {
      capturedToken = "";
    };
  }, [token]);

  if (!token) {
    return <p className="notice">请使用完整邀请链接进入。</p>;
  }

  return (
    <form action={exchangeInvite}>
      <input type="hidden" name="token" value={token} />
      <p className="status-meta">通行证已安全读取。</p>
      <button className="button primary" type="submit">打开通行证</button>
    </form>
  );
}
