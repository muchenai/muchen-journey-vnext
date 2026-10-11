"use client";

import { useEffect, useSyncExternalStore } from "react";

import { exchangeInvite } from "@/app/actions";

import { JoinSubmitButton } from "./join-submit-button";
import type { JoinLocale } from "./language-switcher";

let capturedToken = "";
function readFragmentToken(): string {
  if (typeof window !== "undefined") {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const fragmentToken = fragment.get("token") ?? "";
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

export function InviteTokenExchangeForm({
  orientationDescriptionId,
  locale,
}: {
  orientationDescriptionId: string;
  locale: JoinLocale;
}) {
  const token = useSyncExternalStore(subscribeToFragment, readFragmentToken, () => "");
  const isEnglish = locale === "en";

  useEffect(() => {
    if (token) {
      const query = new URLSearchParams(window.location.search);
      if (query.get("lang") === "en") window.history.replaceState(null, "", "/join?lang=en");
      else window.history.replaceState(null, "", "/join");
    }
    return () => {
      capturedToken = "";
    };
  }, [token]);

  if (!token) {
    return (
      <form
        action={exchangeInvite}
        className="join-token-form"
        aria-describedby={orientationDescriptionId}
      >
        <label htmlFor="invite-token">
          {isEnglish ? "Your private invitation" : "你的专属邀请"}
        </label>
        <p id="invite-token-hint">
          {isEnglish
            ? "Paste the complete invitation link. Its credential will be removed from the address bar."
            : "粘贴完整邀请链接；链接中的凭证不会留在浏览器地址栏。"}
        </p>
        <input
          id="invite-token"
          name="token"
          type="text"
          minLength={32}
          maxLength={2048}
          autoComplete="off"
          aria-describedby="invite-token-hint"
          placeholder="https://…/join#token=…"
          spellCheck={false}
          required
        />
        <JoinSubmitButton
          idleLabel={isEnglish ? "Verify and start exploring" : "验证专属邀请并开始探索"}
          pendingLabel={isEnglish ? "Verifying…" : "正在验证…"}
        />
      </form>
    );
  }

  return (
    <form
      action={exchangeInvite}
      className="join-token-form"
      aria-describedby={orientationDescriptionId}
    >
      <input type="hidden" name="token" value={token} />
      <p className="join-ready-copy">
        <strong>{isEnglish ? "Invitation received" : "邀请已读取"}</strong>
        <span>{isEnglish ? "You will confirm your identity next." : "验证后还会由你本人确认身份。"}</span>
      </p>
      <JoinSubmitButton
        idleLabel={isEnglish ? "Verify and start exploring" : "验证专属邀请并开始探索"}
        pendingLabel={isEnglish ? "Verifying…" : "正在验证…"}
      />
    </form>
  );
}
