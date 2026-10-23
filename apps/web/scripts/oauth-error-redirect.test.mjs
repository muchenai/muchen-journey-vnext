import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import { NextRequest, NextResponse } from "next/server.js";

const require = createRequire(import.meta.url);
function compile(relative, overrides, globals = {}) {
  const source = readFileSync(new URL(relative, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText;
  const compiled = { exports: {} };
  vm.runInNewContext(code, {
    module: compiled, exports: compiled.exports,
    require: (name) => name in overrides ? overrides[name] : require(name),
    URL, Headers, Response, process, ...globals,
  });
  return compiled.exports;
}

async function failedCallback(entry, error = "IDENTITY_NOT_LINKED", status = 403, raw = false) {
  const proxy = compile("../src/lib/server/oauth-proxy.ts", {
    "server-only": {}, "next/server": { NextRequest, NextResponse },
  }, {
    fetch: async (_url, options) => {
      assert.equal(options.headers.get("X-Identity-Return-To"), null);
      return new Response(raw ? "not-json" : JSON.stringify({ error: { code: error } }), {
        status, headers: entry === null ? {} : { "X-Identity-Return-To": entry },
      });
    },
  });
  const { GET } = compile("../src/app/auth/feishu/callback/route.ts", {
    "@/lib/server/oauth-proxy": proxy, "next/server": { NextRequest, NextResponse },
  });
  return GET(new NextRequest(`http://localhost:3000/auth/feishu/callback?code=example&state=${"s".repeat(43)}&return_to=/review`, {
    headers: { "X-Identity-Return-To": "/review" },
  }));
}

test("non-admin and revoked staff callbacks stay on management login without issuing a session", async () => {
  for (const error of ["IDENTITY_NOT_LINKED", "FORBIDDEN", "IDENTITY_REVOKED", "OAUTH_STATE_EXPIRED", "OAUTH_STATE_REPLAY"]) {
    const response = await failedCallback("/review", error);
    assert.equal(response.status, 303);
    assert.equal(response.headers.get("location"), `/review/login?auth_error=${error}`);
    assert.equal(response.headers.get("set-cookie"), null);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.equal(response.headers.get("referrer-policy"), "no-referrer");
  }
});

test("each verified entry keeps its own login destination", async () => {
  for (const [entry, login] of [["/ops", "/ops/login"], ["/content", "/content/login"], ["/app", "/join"]]) {
    const response = await failedCallback(entry);
    assert.equal(response.headers.get("location"), `${login}?auth_error=IDENTITY_NOT_LINKED`);
  }
});

test("missing or untrusted entry cannot redirect externally or use browser-supplied intent", async () => {
  for (const entry of [null, "https://evil.example", "//evil.example", "/review?next=evil", "/review/login", "__proto__"]) {
    const response = await failedCallback(entry);
    assert.equal(response.headers.get("location"), "/?auth_error=IDENTITY_NOT_LINKED");
  }
});

test("malformed provider replies retain verified review context and sanitize error codes", async () => {
  assert.equal((await failedCallback("/review", "bad", 502, true)).headers.get("location"),
    "/review/login?auth_error=IDENTITY_PROVIDER_UNAVAILABLE");
  assert.equal((await failedCallback("/review", "<script>bad</script>")).headers.get("location"),
    "/review/login?auth_error=IDENTITY_LOGIN_FAILED");
});

test("review login renders a management authorization notice and the review retry entry", async () => {
  const { GET } = compile("../src/app/review/login/route.ts", {
    "next/headers": { headers: async () => new Headers() },
  });
  for (const error of ["IDENTITY_NOT_LINKED", "FORBIDDEN"]) {
    const response = await GET(new Request(`http://localhost:3000/review/login?auth_error=${error}`));
    const html = await response.text();
    assert.match(html, /当前飞书账号尚未获得管理权限，请联系超级管理员授权后再登录。/);
    assert.match(html, /登录管理系统/);
    assert.match(html, /\/auth\/feishu\?return_to=%2Freview/);
    assert.doesNotMatch(html, /登录并开始探索/);
  }
});
