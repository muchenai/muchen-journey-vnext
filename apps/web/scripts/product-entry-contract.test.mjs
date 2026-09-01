import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const home = await readFile(new URL("../src/app/page.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");
const layout = await readFile(new URL("../src/app/layout.tsx", import.meta.url), "utf8");
const actions = await readFile(new URL("../src/app/actions.ts", import.meta.url), "utf8");
const api = await readFile(new URL("../src/lib/server/api.ts", import.meta.url), "utf8");
const learnerLayout = await readFile(
  new URL("../src/app/app/layout.tsx", import.meta.url),
  "utf8",
);
const product = JSON.parse(
  await readFile(new URL("../../../config/muchen_journey_product.json", import.meta.url), "utf8"),
);
const generatedProduct = JSON.parse(
  await readFile(
    new URL("../src/lib/muchen-journey-product.generated.json", import.meta.url),
    "utf8",
  ),
);
const controlledRelease = JSON.parse(
  await readFile(
    new URL("../../../config/muchen_journey_2026_09_01_controlled_release.json", import.meta.url),
    "utf8",
  ),
);
const generatedControlledRelease = JSON.parse(
  await readFile(
    new URL("../src/lib/muchen-journey-controlled-release.generated.json", import.meta.url),
    "utf8",
  ),
);
const contract = JSON.parse(
  await readFile(
    new URL("../../../outputs/controller-integration/shared-home/contract.json", import.meta.url),
    "utf8",
  ),
);

test("shared home is bound to the product contract and controlled release overlay", () => {
  assert.equal(contract.surface, "/");
  assert.equal(contract.owner, "muchen-journey-program-control");
  assert.match(home, /muchen-journey-product\.generated\.json/);
  assert.match(home, /muchen-journey-controlled-release\.generated\.json/);
  assert.match(home, /CONTROLLED_MODULE_KEYS/);
  assert.match(home, /journeyProduct\.current_map/);
  assert.match(home, /People AI 成长系统/);
  assert.match(home, /四个模块，共用一条真实任务闭环/);
  assert.doesNotMatch(home, /五张地图|Career Map|认证竞技场/);
  assert.doesNotMatch(home, /当前只开放探索营|探索营 · P0|探索营路线预览/);
});

test("the deployable web projection cannot drift from the controller product contract", () => {
  assert.equal(generatedProduct.generated_from, "config/muchen_journey_product.json");
  assert.equal(generatedProduct.current_map, product.current_map);
  assert.deepEqual(
    generatedProduct.maps,
    product.maps.map(({ order, key, name, mission, people_ai_output }) => ({
      order,
      key,
      name,
      mission,
      people_ai_output,
    })),
  );
  assert.deepEqual(
    generatedProduct.approved_product_modules,
    {
      model: product.approved_product_modules.model,
      recorded_on: product.approved_product_modules.recorded_on,
      modules: product.approved_product_modules.modules,
    },
  );
});

test("public entry uses the approved visual-first journey proposition", () => {
  assert.match(home, /这里，没有标准答案/);
  assert.match(home, /It&apos;s a long game/);
  assert.match(home, /继续旅程/);
  assert.match(home, /从专属邀请开始/);
  assert.match(home, /data-hint/);
  assert.doesNotMatch(home, /探索营 · P0|飞书登录进入运营|固定版本|系统保留事实/);
});

test("staff tools stay out of the public learner entry", () => {
  assert.match(learnerLayout, /href="\/app">我的旅程/);
  assert.doesNotMatch(layout, /href="\/app">我的旅程/);
  assert.doesNotMatch(layout, /return_to=%2Fops|>运营</);
  assert.doesNotMatch(home, /return_to=%2F(?:review|ops)/);
});

test("the deployable controlled release projection cannot expand the frozen owner scope", () => {
  assert.equal(
    generatedControlledRelease.generated_from,
    "config/muchen_journey_2026_09_01_controlled_release.json",
  );
  assert.deepEqual(generatedControlledRelease.modules, controlledRelease.modules);
  assert.deepEqual(
    generatedControlledRelease.shared_vertical_slice,
    controlledRelease.shared_vertical_slice,
  );
  assert.equal(generatedControlledRelease.cohort_limit, 25);
  assert.equal(generatedControlledRelease.full_product_release, false);
  assert.equal(generatedControlledRelease.release_authorized, false);
});

test("all canonical maps and growth missions remain ordered in the shared product contract", () => {
  assert.deepEqual(
    product.maps.map(({ order, key, name }) => ({ order, key, name })),
    [
      { order: 1, key: "exploration-camp", name: "探索营" },
      { order: 2, key: "newcomer-village", name: "新手村" },
      { order: 3, key: "ai-academy", name: "AI学院" },
      { order: 4, key: "delivery-guild", name: "交付线工会" },
      { order: 5, key: "certification-arena", name: "认证竞技场" },
    ],
  );
  assert.ok(product.maps.every((map) => map.mission && map.people_ai_output));
  assert.match(home, /map\.mission/);
  assert.doesNotMatch(home, /BOSS副本/);
});

test("the four contract states each resolve to their one exact primary action", () => {
  const expectedActions = new Map(
    contract.experience_states.map((state) => [state.id, state.primary_action]),
  );
  assert.equal(expectedActions.get("visitor-without-session"), "我已有专属邀请");
  assert.equal(expectedActions.get("learner-with-active-session"), "继续当前旅程");
  assert.equal(expectedActions.get("learner-with-expired-session"), "使用重新进入链接");
  assert.equal(expectedActions.get("learner-with-next-map-unlocked"), "进入下一张地图");
  for (const action of expectedActions.values()) assert.match(home, new RegExp(action));

  assert.match(home, /type HomeState = "visitor" \| "active" \| "expired" \| "unlocked" \| "unavailable"/);
  assert.match(home, /session\.status === "INVALID" \|\| authError === "LEARNER_SESSION_EXPIRED"/);
  assert.match(home, /currentMapIndex > PRODUCT_CURRENT_MAP_INDEX \? "unlocked" : "active"/);
});

test("visitor and expired states validate complete invitation links on the homepage", () => {
  assert.match(home, /action=\{exchangeInvite\}/);
  assert.match(home, /name="token"/);
  assert.match(home, /type="url"/);
  assert.match(home, /完整专属邀请链接/);
  assert.match(home, /一次性重新进入链接/);
  assert.doesNotMatch(home, /href="\/join"/);
  assert.match(actions, /new URL\(token\)/);
  assert.match(actions, /inviteUrl\.hash/);
  assert.doesNotMatch(actions, /inviteUrl\.searchParams\.get\("token"\)/);
});

test("returning states use verified server facts and avoid authentication prefetch", () => {
  assert.match(home, /resolveLearnerSessionState/);
  assert.match(home, /apiRequest<CurrentAction>\("\/api\/v1\/me\/current-action", "LEARNER"\)/);
  assert.match(home, /action\.journey\?\.stable_key/);
  assert.match(home, /stableKey\.includes\(map\.key\)/);
  assert.match(home, /prefetch=\{false\}/);
  assert.match(home, /href="\/app"/);
  assert.match(api, /roles\.includes\("LEARNER"\)/);
  assert.match(api, /status: "UNAVAILABLE"/);
  assert.doesNotMatch(home, /localStorage|sessionStorage|document\.cookie|NEXT_MAP_UNLOCKED/);
});

test("homepage styles expose three responsive widths, focus, touch, and reduced motion", () => {
  assert.match(styles, /\.shared-home/);
  assert.match(styles, /@media \(max-width: 900px\)/);
  assert.match(styles, /@media \(max-width: 640px\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: no-preference\)/);
  assert.match(styles, /\.home-primary-action \{[^}]*min-height: 52px/s);
  assert.match(styles, /:focus-visible/);
  assert.match(styles, /min-width: 0/);
});

test("staff and build-stage language do not compete with the learner action", () => {
  assert.doesNotMatch(layout, /href="\/app">我的旅程/);
  assert.doesNotMatch(home, /Reviewer|return_to=%2Fops|>运营</);
  assert.doesNotMatch(layout, /vNext|Alpha/);
});
