const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { mkdirSync } = require("node:fs");
const { chromium, request } = require(
  process.env.PLAYWRIGHT_CORE || "playwright-core",
);

const api = process.env.LOGOUT_TEST_API || "http://127.0.0.1:58061";
const web = process.env.LOGOUT_TEST_WEB || "http://127.0.0.1:5312";
const browserExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
const output = process.env.LOGOUT_TEST_SCREENSHOTS;
const apiContainer = process.env.LOGOUT_TEST_API_CONTAINER;

for (const value of [api, web]) {
  assert.equal(new URL(value).hostname, "127.0.0.1", "Logout browser checks are loopback-only");
}
if (apiContainer) {
  assert.match(apiContainer, /^journey-logout-feedback-api$/);
}
if (output) mkdirSync(output, { recursive: true });

async function waitForApi() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${api}/health/ready`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Synthetic API did not recover in time");
}

async function createLearnerContext(browser, label) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const call = async (path, data, headers = {}) => {
    const response = await context.request.post(`${api}${path}`, {
      data,
      headers: { "Idempotency-Key": crypto.randomUUID(), ...headers },
    });
    assert(response.ok(), `${path}: ${response.status()} ${await response.text()}`);
    return (await response.json()).data;
  };
  const invite = await call(
    "/api/v1/ops/invites",
    {
      purpose: `Synthetic logout feedback check ${label}`,
      expires_in_hours: 1,
      role: "LEARNER",
      reviewer_id: "10000000-0000-4000-8000-000000000003",
      task_version_id: "10000000-0000-4000-8000-00000000000c",
      target_user_id: null,
    },
    { "X-Fixture-Role": "OPERATOR" },
  );
  const exchange = await call("/api/v1/join/exchange", {
    token: invite.invite_token,
    return_to: "/app",
  });
  await call(
    "/api/v1/identity/confirm",
    { display_name: `Synthetic ${label}`, accepted_purpose: true, return_to: "/app" },
    { "X-CSRF-Token": exchange.csrf_token },
  );
  return context;
}

function observe(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  return errors;
}

async function assertExitSurface(page, suffix) {
  await page.goto(`${web}/app`, { waitUntil: "networkidle" });
  const region = page.getByRole("region", { name: "结束本次使用" });
  await region.scrollIntoViewIfNeeded();
  await page.getByText(/只退出当前浏览器会话/).waitFor();
  await page.getByText(/不会删除旅程进度、提交版本或评审记录/).waitFor();
  if (output) await page.screenshot({ path: `${output}/${suffix}.png`, fullPage: true });
}

async function successScenario(browser) {
  const context = await createLearnerContext(browser, "success");
  const page = await context.newPage();
  const errors = observe(page);
  await assertExitSurface(page, "1280-before");
  for (const [width, height] of [[768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.getByRole("region", { name: "结束本次使用" }).scrollIntoViewIfNeeded();
    if (output) await page.screenshot({ path: `${output}/${width}-before.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  let actionRequests = 0;
  page.on("request", (incoming) => {
    if (incoming.method() === "POST" && incoming.url().startsWith(`${web}/app`)) actionRequests += 1;
  });
  await page.route(`${web}/app`, async (route) => {
    if (route.request().method() === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    await route.continue();
  });
  const button = page.getByRole("button", { name: "退出 vNext 会话" });
  const dispatched = button.evaluate((element) => {
    element.click();
    element.click();
  });
  await page.getByRole("button", { name: "正在安全退出……" }).waitFor();
  await page.getByRole("status").filter({ hasText: "正在撤销当前会话" }).waitFor();
  if (output) await page.screenshot({ path: `${output}/pending.png`, fullPage: true });
  await dispatched;
  await page.waitForURL(`${web}/?session=logged_out`, { timeout: 15_000 });
  assert.equal(actionRequests, 1, "rapid double click must dispatch one logout action");
  await page.getByRole("status").filter({ hasText: "服务端已确认" }).waitFor();
  await page.getByText("旅程进度、历史提交和评审记录均已保留。").waitFor();
  await page.getByLabel("一次性重新进入链接").waitFor();
  assert.equal(await page.getByLabel("完整专属邀请链接").count(), 0);
  assert.equal((await context.cookies()).some((cookie) => cookie.name === "journey_next_session"), false);
  assert.equal((await context.request.get(`${api}/api/v1/session`)).status(), 401);

  for (const [width, height] of [[1280, 900], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height });
    if (output) await page.screenshot({ path: `${output}/${width}-success.png`, fullPage: true });
  }
  await page.reload({ waitUntil: "networkidle" });
  await page.getByText("旅程进度、历史提交和评审记录均已保留。").waitFor();
  assert.deepEqual(errors, []);
  await context.close();
}

async function staleCookieScenario(browser) {
  const context = await createLearnerContext(browser, "stale-cookie");
  const page = await context.newPage();
  const errors = observe(page);
  await assertExitSurface(page, "stale-cookie-before");
  const cookies = await context.cookies();
  const csrf = cookies.find((cookie) => cookie.name === "journey_next_csrf");
  assert(csrf);
  const isolatedRequest = await request.newContext({
    extraHTTPHeaders: {
      Cookie: cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; "),
      "X-CSRF-Token": csrf.value,
    },
  });
  const revoked = await isolatedRequest.post(`${api}/api/v1/session/logout`);
  assert(revoked.ok(), await revoked.text());
  await isolatedRequest.dispose();

  await page.getByRole("button", { name: "退出 vNext 会话" }).click();
  await page.waitForURL(`${web}/?session=logged_out`, { timeout: 15_000 });
  await page.getByText("旅程进度、历史提交和评审记录均已保留。").waitFor();
  assert.equal((await context.cookies()).some((cookie) => cookie.name === "journey_next_session"), false);
  assert.deepEqual(errors, []);
  await context.close();
}

async function failureScenario(browser) {
  assert(apiContainer, "LOGOUT_TEST_API_CONTAINER is required for the isolated failure scenario");
  const context = await createLearnerContext(browser, "failure");
  const page = await context.newPage();
  const errors = observe(page);
  await assertExitSurface(page, "failure-before");
  execFileSync("docker", ["stop", apiContainer], { stdio: "ignore" });
  try {
    await page.getByRole("button", { name: "退出 vNext 会话" }).click();
    const alert = page.getByRole("alert");
    await alert.waitFor({ timeout: 15_000 });
    await page.getByText("退出没有完成，当前会话仍然有效。请稍后重试。").waitFor();
    await page.getByText(/请求 ID：未生成/).waitFor();
    assert.equal(new URL(page.url()).pathname, "/app");
    assert.equal((await context.cookies()).some((cookie) => cookie.name === "journey_next_session"), true);
    assert.equal(await page.getByText("已安全退出 vNext 会话").count(), 0);
    if (output) await page.screenshot({ path: `${output}/failure.png`, fullPage: true });
  } finally {
    execFileSync("docker", ["start", apiContainer], { stdio: "ignore" });
    await waitForApi();
  }
  assert.equal((await context.request.get(`${api}/api/v1/session`)).status(), 200);
  assert.deepEqual(errors, []);
  await context.close();
}

(async () => {
  const browser = await chromium.launch({ executablePath: browserExecutable, headless: true });
  try {
    await successScenario(browser);
    await staleCookieScenario(browser);
    await failureScenario(browser);
    console.log(JSON.stringify({ result: "PASS", success: true, staleCookie: true, failure: true }));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
