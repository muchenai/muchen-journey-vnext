"use client";

import { useEffect, useTransition } from "react";
import { useRouter } from "next/navigation";

export type JoinLocale = "zh-CN" | "en";

export function LanguageSwitcher({ locale }: { locale: JoinLocale }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  return (
    <label className="join-language-switcher">
      <span aria-hidden="true" className="join-language-icon">◎</span>
      <span className="sr-only">{locale === "zh-CN" ? "选择页面语言" : "Select page language"}</span>
      <select
        aria-label={locale === "zh-CN" ? "页面语言" : "Page language"}
        value={locale}
        disabled={isPending}
        onChange={(event) => {
          const nextLocale = event.target.value === "en" ? "en" : "zh-CN";
          document.cookie = `journey_locale=${nextLocale}; Path=/; Max-Age=31536000; SameSite=Lax`;
          document.documentElement.lang = nextLocale;
          const nextUrl = new URL(window.location.href);
          if (nextLocale === "en") nextUrl.searchParams.set("lang", "en");
          else nextUrl.searchParams.delete("lang");
          startTransition(() => router.replace(`${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`));
        }}
      >
        <option value="zh-CN">简体中文</option>
        <option value="en">English</option>
      </select>
    </label>
  );
}
