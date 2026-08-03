import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/app/layout.tsx", import.meta.url), "utf8");

test("public entry focuses on the learner's next action", () => {
  assert.match(home, /把一个真实问题，变成清晰的下一步/);
  assert.match(home, /继续我的行动/);
  assert.match(home, /一次只走好一步/);
  assert.doesNotMatch(home, /探索营 · P0|飞书登录进入运营|固定版本|系统保留事实/);
});

test("operations stays out of public navigation while reviewer access remains available", () => {
  assert.match(layout, /href="\/app">我的行动/);
  assert.doesNotMatch(layout, /return_to=%2Fops|>运营</);
  assert.match(home, /return_to=%2Freview/);
  assert.doesNotMatch(home, /return_to=%2Fops/);
});

test("production chrome does not expose build-stage language", () => {
  assert.doesNotMatch(layout, /vNext|Alpha/);
});
