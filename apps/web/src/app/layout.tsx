import type { Metadata } from "next";
import { connection } from "next/server";

import "./globals.css";
import "./project9/project9.css";

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
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
