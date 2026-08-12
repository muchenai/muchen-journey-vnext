import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const proxySource = readFileSync(new URL("../src/proxy.ts", import.meta.url), "utf8");
const contentLoginSource = readFileSync(
  new URL("../src/app/content/login/page.tsx", import.meta.url),
  "utf8",
);
const reviewLoginSource = readFileSync(
  new URL("../src/app/review/login/page.tsx", import.meta.url),
  "utf8",
);
const apiSource = readFileSync(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");

test("ops still rejects anonymous requests before rendering", () => {
  assert.match(
    proxySource,
    /\["\/ops"\]\.some\(/,
  );
  assert.match(proxySource, /code: "AUTH_REQUIRED"/);
  assert.match(proxySource, /\{ status: 401 \}/);
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
