import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { hasLearnerSession } from "@/lib/server/api";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Muchen Journey",
    template: "%s · Muchen Journey",
  },
  description: "一段没有标准答案、但每一步都留下真实证据的探索旅程。",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // A per-request CSP nonce cannot be attached to statically generated
  // framework scripts. Keep the whole application request-rendered so Next.js
  // can apply the nonce supplied by proxy.ts.
  await connection();
  const learnerSession = await hasLearnerSession();

  return (
    <html lang="zh-CN">
      <body>
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        <header className="site-header">
          <Link className="brand" href="/">
            Muchen Journey
          </Link>
          {learnerSession ? (
            <nav aria-label="主要导航">
              <Link href="/app">我的旅程</Link>
            </nav>
          ) : null}
        </header>
        <main id="main-content" className="page-shell">
          {children}
        </main>
        <footer className="site-footer">Muchen Journey <span>It&apos;s a long game.</span></footer>
      </body>
    </html>
  );
}
