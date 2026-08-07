import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const proxySource = readFileSync(new URL("../src/proxy.ts", import.meta.url), "utf8");
const contentLoginSource = readFileSync(
  new URL("../src/app/content/login/page.tsx", import.meta.url),
  "utf8",
);

test("ops and review still reject anonymous requests before rendering", () => {
  assert.match(
    proxySource,
    /\["\/ops", "\/review"\]\.some\(/,
  );
  assert.match(proxySource, /code: "AUTH_REQUIRED"/);
  assert.match(proxySource, /\{ status: 401 \}/);
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
