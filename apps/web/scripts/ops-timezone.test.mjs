import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptsDirectory = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptsDirectory, "..");

test("client-rendered operations times use one explicit timezone", async () => {
  for (const relativePath of [
    "src/app/ops/invite-management-panel.tsx",
    "src/app/ops/learner-reentry-panel.tsx",
    "src/app/ops/identity-access-panel.tsx",
  ]) {
    const source = await readFile(path.join(webRoot, relativePath), "utf8");
    assert.match(source, /timeZone: "Asia\/Shanghai"/);
  }
});

test("server-rendered journey workspaces share the explicit product timezone", async () => {
  const formatter = await readFile(path.join(webRoot, "src/lib/date-time.ts"), "utf8");
  assert.match(formatter, /timeZone: PRODUCT_TIME_ZONE/);
  assert.match(formatter, /PRODUCT_TIME_ZONE = "Asia\/Shanghai"/);

  for (const relativePath of [
    "src/app/review/page.tsx",
    "src/app/review/[reviewId]/page.tsx",
    "src/app/ops/page.tsx",
    "src/app/app/tasks/[assignmentId]/page.tsx",
  ]) {
    const source = await readFile(path.join(webRoot, relativePath), "utf8");
    assert.match(source, /formatProductDateTime/);
    assert.doesNotMatch(source, /new Intl\.DateTimeFormat\("zh-CN"/);
  }

  const formatterUrl = pathToFileURL(path.join(webRoot, "src/lib/date-time.ts")).href;
  const probe = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import { formatProductDateTime } from ${JSON.stringify(formatterUrl)}; process.stdout.write(formatProductDateTime("2026-09-18T06:47:00.000Z"));`,
    ],
    {
      encoding: "utf8",
      env: { ...process.env, TZ: "UTC" },
    },
  );
  assert.equal(probe.status, 0, probe.stderr);
  assert.equal(probe.stdout, "2026年9月18日 14:47");
});
