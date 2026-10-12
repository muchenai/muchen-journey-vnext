import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";
import { NextRequest, NextResponse } from "next/server.js";

const require = createRequire(import.meta.url);
function compile(relative, overrides = {}) {
  const source = readFileSync(new URL(relative, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const compiled = { exports: {} };
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`)(
    (name) => name in overrides ? overrides[name] : require(name), compiled, compiled.exports);
  return compiled.exports;
}
const { isFeishuClient, isFeishuAppContainer } = compile("../src/lib/feishu-client-login.ts");
test("Feishu desktop/mobile use client auth while Chrome keeps redirect auth", () => {
  for (const ua of ["Mozilla/5.0 Lark/7.50.0", "Mozilla/5.0 Feishu/7.0.0"]) assert.equal(isFeishuClient(ua), true);
  for (const ua of ["Mozilla/5.0 Chrome/140.0 Safari/537.36", "LarkishBrowser/1.0"]) assert.equal(isFeishuClient(ua), false);
});

test("desktop Feishu browser and application containers are distinct", () => {
  assert.equal(isFeishuAppContainer("Mozilla/5.0 Lark/7.50.0"), false);
  assert.equal(isFeishuAppContainer("Mozilla/5.0 Lark/7.50.0 WebApp"), true);
  assert.equal(isFeishuAppContainer("Mozilla/5.0 Lark/3.45.0"), true);
  assert.equal(isFeishuAppContainer("Mozilla/5.0 Lark/3.46.0"), false);
  assert.equal(isFeishuAppContainer("Mozilla/5.0 Android Feishu/7.50.0"), true);
  assert.equal(isFeishuAppContainer("Mozilla/5.0 Chrome/140.0 WebApp"), false);
});

function route(handler) {
  return compile("../src/app/auth/feishu/client/route.ts", {
    "@/lib/server/oauth-proxy": {
      postIdentityApi: handler,
      appendSetCookies: (source, target) => source.headers.getSetCookie().forEach(value => target.headers.append("Set-Cookie", value)),
    },
  }).POST;
}
function request(body, headers = {}) {
  return new NextRequest("https://journey.example/auth/feishu/client", {
    method: "POST", headers: { Host: "journey.example", Origin: "https://journey.example", "Content-Type": "application/json", "X-Journey-Client-Login": "1", ...headers }, body: JSON.stringify(body),
  });
}
const state = "a".repeat(43);
test("client start exposes only public app ID/state and forwards browser-binding cookie", async () => {
  const post = route(async (_req, path, body) => {
    assert.equal(path, "/api/v1/auth/feishu/start");
    assert.deepEqual(body, { return_to: "/app" });
    return { data: { authorization_url: `https://accounts.feishu.cn/open-apis/authen/v1/authorize?client_id=cli_test&state=${state}` }, response: new Response(null, { headers: { "Set-Cookie": "oauth=bound; HttpOnly; Path=/auth/feishu" } }) };
  });
  const response = await post(request({ step: "start", return_to: "/ops" }));
  assert.deepEqual(await response.json(), { appId: "cli_test", state });
  assert.match(response.headers.get("set-cookie"), /HttpOnly/);
  assert.equal(response.headers.get("cache-control"), "no-store");
});
test("client completion uses shared callback and keeps session cookies", async () => {
  const post = route(async (_req, path, body) => {
    assert.equal(path, "/api/v1/auth/feishu/callback");
    assert.deepEqual(body, { code: "one-time-code", state, authorization_method: "client" });
    return { data: { safe_entry: "/app", csrf_token: "must-not-be-exposed" }, response: new Response(null, { headers: { "Set-Cookie": "session=verified; HttpOnly" } }) };
  });
  const response = await post(request({ step: "complete", code: "one-time-code", state }));
  assert.deepEqual(await response.json(), { entry: "/app" });
  assert.match(response.headers.get("set-cookie"), /session=verified/);
});
test("cross-site and malformed requests never reach identity API", async () => {
  const post = route(() => { throw new Error("API must not be called"); });
  assert.equal((await post(request({ step: "start" }, { Origin: "https://evil.example" }))).status, 403);
  assert.equal((await post(request({ step: "start" }, { "X-Journey-Client-Login": "" }))).status, 403);
  assert.equal((await post(request({ step: "complete", code: "x", state: "short" }))).status, 400);
  assert.equal((await post(request({ step: "start", padding: "x".repeat(2100) }))).status, 400);
});
test("provider errors are JSON and unexpected target cannot escape learner entry", async () => {
  const post = route(async () => NextResponse.redirect("https://journey.example/?auth_error=OAUTH_BROWSER_MISMATCH", 303));
  const failed = await post(request({ step: "start" }));
  assert.equal(failed.status, 400);
  assert.deepEqual(await failed.json(), { error: "OAUTH_BROWSER_MISMATCH" });
  const unexpected = route(async () => ({ data: { safe_entry: "/ops" }, response: new Response() }));
  assert.equal((await unexpected(request({ step: "complete", code: "code", state }))).status, 502);
});

function clientRuntime(authorize, configure = () => {}) {
  const calls = [];
  const navigations = [];
  const source = readFileSync(new URL("../src/lib/feishu-client-login.ts", import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const compiled = { exports: {} };
  const sandbox = {
    exports: compiled.exports, module: compiled, AbortSignal, URL,
    window: {
      navigator: { userAgent: "Mozilla/5.0 Lark/7.50.0 WebApp" },
      setTimeout, clearTimeout,
      location: { href: "https://journey.example/join?feishu_app_entry=1", assign: (url) => navigations.push(url) },
      h5sdk: { ready: (ready) => ready(), error() {} },
      tt: { requestAccess: authorize },
    },
    fetch: async (url, options) => {
      assert.equal(url, "/auth/feishu/client");
      assert.equal(options.credentials, "same-origin");
      const body = JSON.parse(options.body);
      calls.push(body);
      return { ok: true, json: async () => body.step === "start" ? { appId: "cli_test", state } : { entry: "/app" } };
    },
  };
  configure(sandbox);
  vm.runInNewContext(code, sandbox);
  return { login: compiled.exports.loginInsideFeishu, errorMessage: compiled.exports.clientLoginErrorMessage, calls, navigations };
}
test("client authorization uses only basic login scope and returns inside Journey", async () => {
  const runtime = clientRuntime((options) => {
    assert.equal(options.appID, "cli_test");
    assert.equal(options.scopeList.length, 0);
    assert.equal(options.state, state);
    options.success({ code: "native-code", state });
  });
  await runtime.login();
  assert.deepEqual(runtime.calls, [{ step: "start" }, { step: "complete", code: "native-code", state }]);
  assert.deepEqual(runtime.navigations, ["/app"]);
});
test("denied or mismatched client authorization does not exchange a code or navigate", async () => {
  for (const authorize of [(options) => options.fail(), (options) => options.success({ code: "code", state: "wrong" })]) {
    const runtime = clientRuntime(authorize);
    await assert.rejects(runtime.login());
    assert.deepEqual(runtime.calls, [{ step: "start" }]);
    assert.deepEqual(runtime.navigations, []);
  }
});

test("client failure identifies authorization stage without exposing raw provider data", async () => {
  const runtime = clientRuntime(options => options.fail({ errCode: 123, errMsg: "secret-code" }));
  await assert.rejects(runtime.login(), error => {
    const message = runtime.errorMessage(error);
    assert.match(message, /authorize\/AUTH_DENIED:123/);
    assert.doesNotMatch(message, /secret-code/);
    return true;
  });
});

test("official SDK is pinned without source modifications", () => {
  const sdk = readFileSync(new URL("../public/vendor/feishu/h5-js-sdk-1.5.26.js", import.meta.url));
  assert.equal(createHash("sha256").update(sdk).digest("hex"), "1080a3f2492ba78e7a86fb3d4f460921f68a20b44d01c80a04f0b32340859ce3");
});

test("fresh client loads same-origin SDK with CSP nonce before authorization", async () => {
  let script;
  const runtime = clientRuntime(options => options.success({ code: "native-code", state }), sandbox => {
    const { h5sdk, tt } = sandbox.window;
    delete sandbox.window.h5sdk;
    delete sandbox.window.tt;
    sandbox.document = {
      createElement: () => (script = { remove() {} }),
      querySelector: () => ({ nonce: "page-nonce" }),
      head: { appendChild: element => {
        assert.equal(element.src, "/vendor/feishu/h5-js-sdk-1.5.26.csp.js");
        assert.equal(element.nonce, "page-nonce");
        Object.assign(sandbox.window, { h5sdk, tt });
        element.onload();
      } },
    };
  });
  await runtime.login();
  assert.deepEqual(runtime.navigations, ["/app"]);
});

test("SDK download failure stays visible and does not restart authorization", async () => {
  const runtime = clientRuntime(() => {}, sandbox => {
    delete sandbox.window.h5sdk;
    delete sandbox.window.tt;
    sandbox.document = {
      createElement: () => ({ remove() {} }), querySelector: () => null,
      head: { appendChild: element => element.onerror() },
    };
  });
  await assert.rejects(runtime.login(), error => {
    assert.match(runtime.errorMessage(error), /SDK_LOAD_FAILED/);
    return true;
  });
  assert.equal(runtime.calls.length, 0);
  assert.deepEqual(runtime.navigations, []);
});

test("navigation-bar webview authorizes in its current page without an app handoff", async () => {
  const runtime = clientRuntime(() => assert.fail("must not authorize in ordinary webview"), sandbox => {
    sandbox.window.navigator.userAgent = "Mozilla/5.0 Lark/7.50.0";
    sandbox.window.location.href = "https://journey.example/join?return_to=https://evil.example&code=private";
    delete sandbox.window.h5sdk;
    delete sandbox.window.tt;
  });
  await Promise.all([runtime.login(), runtime.login()]);
  assert.deepEqual(runtime.calls, []);
  assert.deepEqual(runtime.navigations, ["/auth/feishu?return_to=%2Fapp"]);
});

test("old app-entry query does not force another window or block same-page OAuth", async () => {
  const runtime = clientRuntime(() => {}, sandbox => {
    sandbox.window.navigator.userAgent = "Mozilla/5.0 Lark/7.50.0";
    delete sandbox.window.h5sdk;
    delete sandbox.window.tt;
  });
  await runtime.login();
  assert.deepEqual(runtime.navigations, ["/auth/feishu?return_to=%2Fapp"]);
  assert.deepEqual(runtime.calls, []);
});

test("SDK with missing exports uses same-page OAuth even when UA says WebApp", async () => {
  const runtime = clientRuntime(() => assert.fail("native auth unavailable"), sandbox => {
    delete sandbox.window.h5sdk;
    delete sandbox.window.tt;
    sandbox.document = {
      createElement: () => ({ remove() {} }), querySelector: () => null,
      head: { appendChild: element => element.onload() },
    };
  });
  await runtime.login();
  assert.deepEqual(runtime.calls, []);
  assert.deepEqual(runtime.navigations, ["/auth/feishu?return_to=%2Fapp"]);
});

test("concurrent native login requests share one authorization and state exchange", async () => {
  let authorizeCount = 0;
  const runtime = clientRuntime(options => { authorizeCount++; options.success({ code: "native-code", state }); });
  await Promise.all([runtime.login(), runtime.login(), runtime.login()]);
  assert.equal(authorizeCount, 1);
  assert.deepEqual(runtime.calls, [{ step: "start" }, { step: "complete", code: "native-code", state }]);
});

test("browser never enters native authorization or application handoff", async () => {
  const runtime = clientRuntime(() => assert.fail("native auth"), sandbox => {
    sandbox.window.navigator.userAgent = "Mozilla/5.0 Chrome/140.0";
  });
  await assert.rejects(runtime.login(), error => /SDK_NOT_FEISHU_CLIENT/.test(runtime.errorMessage(error)));
  assert.deepEqual(runtime.calls, []);
  assert.deepEqual(runtime.navigations, []);
});

test("failed authorization can be retried and errno takes precedence over generic errCode", async () => {
  let attempts = 0;
  const runtime = clientRuntime(options => {
    if (++attempts === 1) options.fail({ errCode: 999, errno: 2700002 });
    else options.success({ code: "retry-code", state });
  });
  await assert.rejects(runtime.login(), error => /AUTH_DENIED:2700002/.test(runtime.errorMessage(error)));
  await runtime.login();
  assert.equal(attempts, 2);
  assert.deepEqual(runtime.navigations, ["/app"]);
});
