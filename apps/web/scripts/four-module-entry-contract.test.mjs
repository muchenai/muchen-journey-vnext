import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../../../", import.meta.url);
const index = JSON.parse(
  await readFile(new URL("config/module-content-packages/module-content-package-index.v1.json", root), "utf8"),
);
const bindings = JSON.parse(
  await readFile(new URL("../src/lib/muchen-journey-module-bindings.generated.json", import.meta.url), "utf8"),
);
const overview = await readFile(new URL("../src/app/app/program-overview.tsx", import.meta.url), "utf8");
const detail = await readFile(new URL("../src/app/app/maps/[mapKey]/page.tsx", import.meta.url), "utf8");
const modules = await readFile(new URL("../src/lib/journey-program.ts", import.meta.url), "utf8");

const expectedKeys = [
  "exploration-camp",
  "newcomer-village",
  "ai-academy",
  "delivery-guild",
];

test("the runtime projection is an exact hash-bound view of the four canonical packages", async () => {
  assert.equal(bindings.source_index_sha256, index.index_sha256);
  assert.deepEqual(bindings.modules.map(({ module_key }) => module_key), expectedKeys);
  assert.deepEqual(index.packages.map(({ module_key }) => module_key), expectedKeys);

  for (const indexed of index.packages) {
    const bytes = await readFile(new URL(indexed.path, root));
    assert.equal(createHash("sha256").update(bytes).digest("hex"), indexed.file_sha256);
    const canonical = JSON.parse(bytes.toString("utf8"));
    const projected = bindings.modules.find(({ module_key }) => module_key === indexed.module_key);
    assert.ok(projected);
    assert.equal(projected.package_sha256, indexed.package_sha256);
    assert.equal(projected.package_sha256, canonical.sha256);
    assert.equal(projected.version, canonical.version);
    assert.equal(projected.owner_name, canonical.owner.person_name);
    assert.equal(projected.owner_decision, "APPROVED");
    assert.equal(projected.task_version_count, canonical.task_versions.length);
    assert.equal(projected.rubric_count, canonical.rubrics.length);
    assert.equal(projected.reviewer_pool_ref, canonical.reviewer_policy.pool_ref);
    assert.deepEqual(projected.data_policy, canonical.data_policy);
  }
});

test("the four entries expose assignment truth, binding facts and a reachable next action", () => {
  assert.match(overview, /currentJourneyKey/);
  assert.match(overview, /正式任务已分配/);
  assert.match(overview, /未分配 · 当前不可启动/);
  assert.match(overview, /查看开放条件与数据边界/);
  assert.match(detail, /contentBinding\.packageSha256/);
  assert.match(detail, /学习输入预计/);
  assert.match(detail, /Reviewer 配置/);
  assert.match(detail, /原始客户数据/);
  assert.match(detail, /正式任务尚未分配/);
});

test("unapproved extensions cannot enter the runtime route projection", () => {
  assert.match(modules, /CONTROLLED_RELEASE_MODULE_KEYS/);
  assert.match(modules, /getJourneyModule/);
  assert.doesNotMatch(bindings.modules.map(({ module_key }) => module_key).join(" "), /certification-arena|career-map/);
});
