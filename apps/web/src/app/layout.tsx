import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Muchen Journey",
    template: "%s · Muchen Journey",
  },
  description: "一个清晰连接当前任务、主管反馈与下一步的成长闭环。",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // A per-request CSP nonce cannot be attached to statically generated
  // framework scripts. Keep the whole application request-rendered so Next.js
  // can apply the nonce supplied by proxy.ts.
  await connection();

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
          <nav aria-label="主要导航">
            <Link href="/app">我的行动</Link>
          </nav>
        </header>
        <main id="main-content" className="page-shell">
          {children}
        </main>
        <footer className="site-footer">Muchen Journey · 让下一步更清晰</footer>
      </body>
    </html>
  );
}
