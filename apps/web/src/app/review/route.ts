import { readFile } from "node:fs/promises";
import path from "node:path";
import { headers } from "next/headers";
import { identityPageRequest } from "@/lib/server/api";

export const dynamic = "force-dynamic";
export async function GET() {
  await identityPageRequest("/api/v1/reviews?kind=FORMAL_EVALUATION", "REVIEWER");
  const nonce = (await headers()).get("x-nonce") ?? "";
  const source = await readFile(path.join(process.cwd(), "public/review-native/index.html"), "utf8");
  const html = source.replace("<head>", '<head><base href="/review-native/">')
    .replace(/<script\b/g, `<script nonce="${nonce.replace(/[^a-zA-Z0-9+/=]/g, "")}"`);
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}
