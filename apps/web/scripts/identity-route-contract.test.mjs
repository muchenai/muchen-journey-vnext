import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const proxySource = readFileSync(new URL("../src/proxy.ts", import.meta.url), "utf8");

test("local browser verification does not upgrade HTTP fixture assets", () => {
  assert.match(proxySource, /const isLocal = process\.env\.APP_ENV === "local";/);
  assert.match(
    proxySource,
    /isDevelopment \|\| isLocal \? \[\] : \["upgrade-insecure-requests"\]/,
  );
  assert.match(
    proxySource,
    /const stylePolicy = isLocal \? "style-src 'self'"/,
  );
});
const contentLoginSource = readFileSync(
  new URL("../src/app/content/login/page.tsx", import.meta.url),
  "utf8",
);
const reviewLoginSource = readFileSync(
  new URL("../src/app/review/login/page.tsx", import.meta.url),
  "utf8",
);
const opsLoginSource = readFileSync(
  new URL("../src/app/ops/login/page.tsx", import.meta.url),
  "utf8",
);
const apiSource = readFileSync(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");

test("anonymous ops browser entry recovers without weakening JSON denial", () => {
  assert.match(proxySource, /const isOpsLogin = pathname === "\/ops\/login";/);
  assert.match(proxySource, /if \(isOpsRoute && !isOpsLogin && !hasSession\)/);
  assert.match(proxySource, /request\.headers\.get\("accept"\)\?\.includes\("text\/html"\)/);
  assert.match(proxySource, /request\.headers\.has\("next-action"\)/);
  assert.match(
    proxySource,
    /NextResponse\.redirect\(new URL\("\/ops\/login", request\.url\), 303\)/,
  );
  assert.match(proxySource, /code: "AUTH_REQUIRED"/);
  assert.match(proxySource, /\{ status: 401 \}/);
  assert.match(opsLoginSource, />\s*进入运营工作台\s*</);
  assert.match(opsLoginSource, />\s*使用飞书进入\s*</);
  assert.match(opsLoginSource, /href="\/auth\/feishu\?return_to=%2Fops"/);
});

test("anonymous and wrong-role review entry recover through a dedicated login page", () => {
  assert.match(proxySource, /const isReviewLogin = pathname === "\/review\/login";/);
  assert.match(proxySource, /if \(isReviewRoute && !isReviewLogin && !hasSession\)/);
  assert.match(
    proxySource,
    /NextResponse\.redirect\(new URL\("\/review\/login", request\.url\), 303\)/,
  );
  assert.match(reviewLoginSource, />\s*进入主管评审\s*</);
  assert.match(reviewLoginSource, />\s*使用飞书进入\s*</);
  assert.match(
    reviewLoginSource,
    /href="\/auth\/feishu\?return_to=%2Freview"/,
  );
  assert.match(apiSource, /redirect\("\/review\/login\?auth_error=FORBIDDEN"\)/);
  assert.match(apiSource, /redirect\("\/review\/login\?auth_error=SESSION_EXPIRED"\)/);
});

test("anonymous content routes recover through the dedicated same-origin login page", () => {
  assert.match(
    proxySource,
    /const isContentLogin = pathname === "\/content\/login";/,
  );
  assert.match(
    proxySource,
    /if \(isContentRoute && !isContentLogin && !hasSession\)/,
  );
  assert.match(
    proxySource,
    /NextResponse\.redirect\(new URL\("\/content\/login", request\.url\), 303\)/,
  );
  assert.match(proxySource, /response\.headers\.set\("Cache-Control", "no-store"\)/);
  assert.match(contentLoginSource, />\s*使用飞书进入\s*</);
  assert.match(
    contentLoginSource,
    /href="\/auth\/feishu\?return_to=%2Fcontent"/,
  );
});
