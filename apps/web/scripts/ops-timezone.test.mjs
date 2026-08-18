import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

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
