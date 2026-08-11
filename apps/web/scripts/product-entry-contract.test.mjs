import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/app/layout.tsx", import.meta.url), "utf8");

test("public entry uses the approved visual-first journey proposition", () => {
  assert.match(home, /这里，没有标准答案/);
  assert.match(home, /It&apos;s a long game/);
  assert.match(home, /继续旅程/);
  assert.match(home, /从专属邀请开始/);
  assert.match(home, /data-hint/);
  assert.doesNotMatch(home, /探索营 · P0|飞书登录进入运营|固定版本|系统保留事实/);
});

test("staff tools stay out of the public learner entry", () => {
  assert.match(layout, /href="\/app">我的旅程/);
  assert.doesNotMatch(layout, /return_to=%2Fops|>运营</);
  assert.doesNotMatch(home, /return_to=%2F(?:review|ops)/);
});

test("production chrome does not expose build-stage language", () => {
  assert.doesNotMatch(layout, /vNext|Alpha/);
});
