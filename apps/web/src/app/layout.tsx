import type { Metadata } from "next";
import { connection } from "next/server";
import { headers } from "next/headers";
import { canvasScaleBootstrap } from "./project29/canvas-scale";

import "./globals.css";
import "./project29/canvasScale.css";


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
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    // The bootstrap owns the root scale style before React hydrates the page.
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: canvasScaleBootstrap }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
