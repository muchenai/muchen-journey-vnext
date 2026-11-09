import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRequire } from "node:module";

const cache = new Map();
function load(name) {
  const file = name.endsWith(".json") ? name : `${name.replace(/\.ts$/, "")}.ts`;
  if (cache.has(file)) return cache.get(file);
  const text = readFileSync(new URL(file, import.meta.url), "utf8");
  if (file.endsWith(".json")) return JSON.parse(text);
  const source = ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports, require: dependency => load(dependency) });
  cache.set(file, compiledModule.exports);
  return compiledModule.exports;
}
const model = load("./guildGrowthModel");
const economy = load("./badgeEconomy");
const medal = (id, style = "blue", artworkId = "product-1") => ({ id, name: id, style, artworkId, image: "", description: "", revision: 1, stock: null, costs: [{ badgeId: "product", points: 20 }] });
const receipt = item => ({ ...item, id: `receipt-${item.id}`, medalId: item.id, medalName: item.name, redeemedAt: "2026-11-09T00:00:00Z" });
const hallDefinitions = [
  ["multilingual", "多语种数据交付线"], ["agent-trajectories", "Agent 交付与行为轨迹交付线"],
  ["code-reasoning", "代码推理交付线"], ["quality-data", "高质量数据构建交付线"],
  ["multimodal", "多模态数据交付线"], ["model-evaluation", "通用模型测评交付线"],
  ["dialect-speech", "方言语音交付线"], ["functional", "综合职能工会"],
];
const hallIcons = ["ce04e", "9aa97", "a6862", "a03b5", "42cb2", "d7bdc", "eec40", "8c48a"];
const taskTitles = ["需求澄清与验收边界", "质检返修与进度调整", "复杂交付变更与验收复盘"];
const snapshot = (level = 0) => ({ joinedGuild: "multilingual", level, levelName: model.guildLevelNames[level],
  halls: hallDefinitions.map(([id, title], index) => ({ id, title, type: index === 7 ? "职能工会" : "交付线工会", description: "真实工会进度", icon: hallIcons[index], joined: index === 0, level: index === 0 ? level : 0 })),
  tasks: taskTitles.map((title, index) => ({ id: `task-${index + 1}`, level: index + 1, title, minutes: 60, difficulty: "进阶", brief: "服务端任务内容", deliverable: "交付实践方案", publicationStatus: "published", source: "project39-template", version: 1, checks: ["需求", "质量", "验收"] })),
  submissions: [], legacyRequests: [],
  requirements: [1, 2, 3].map(item => ({ level: item, grades: [1, 2, 3].slice(0, item), previousMet: level >= item - 1, eligible: item === level + 1, entryEligible: item === level + 1, taskSubmitted: item === level + 1, fulfilled: item, required: item })), requests: [] });

test("published artwork and wallet balance alone never illuminate a capability", () => {
  const { badges, wallet } = economy.adaptMedals({ medals: [medal("real-publication")], redemptions: [], wallet: { badgeBalances: { product: 99999 } } });
  assert.equal(model.guildOwnedBadges(badges, wallet.owned).length, 0);
  const rows = model.guildCapabilityRows(badges, wallet.owned);
  assert.equal(rows.length, 29);
  assert.equal(rows.filter(row => row.group === "delivery").length, 7);
  assert.ok(rows.every(row => row.highest === 0));
});

test("actual arbitrary publication IDs illuminate the correct artwork and highest owned grade", () => {
  const blue = medal("actual-blue-id"), gold = medal("actual-gold-id", "gold");
  const { badges, wallet } = economy.adaptMedals({ medals: [blue, gold], redemptions: [receipt(blue), receipt(gold)], wallet: { badgeBalances: {} } });
  const rows = model.guildCapabilityRows(badges, wallet.owned);
  assert.equal(model.guildOwnedBadges(badges, [...wallet.owned, blue.id, "unknown"]).length, 2);
  assert.equal(rows.find(row => row.id === "product").highest, 3);
  assert.equal(rows.find(row => row.id === "product").representative.publication.id, gold.id);
  assert.equal(rows.filter(row => row.highest > 0).length, 1);
});

test("delisted but redeemed medals remain evidence for their capability", () => {
  const { badges, wallet } = economy.adaptMedals({ medals: [], redemptions: [receipt(medal("delisted-medal", "purple", "tech-1"))], wallet: { badgeBalances: {} } });
  assert.equal(model.guildOwnedBadges(badges, wallet.owned).length, 1);
  assert.equal(model.guildCapabilityRows(badges, wallet.owned).find(row => row.id === "tech").highest, 2);
});

test("guild evidence retains the redeemed name, artwork and grade when publication changes", () => {
  const original = { ...receipt(medal("edited", "blue", "tech-1")), medalName: "原始凭证", artworkLevel: 2 };
  const current = medal("edited", "gold", "product-1");
  const data = { medals: [current], redemptions: [original], wallet: { badgeBalances: {} } };
  const { badges, wallet } = model.adaptGuildMedals(data);
  const held = model.guildOwnedBadges(badges, wallet.owned)[0];
  assert.equal(held.name, "原始凭证");
  assert.equal(held.tone, "violet");
  assert.equal(held.artworkId, "tech-1");
  assert.equal(model.guildCapabilityRows(badges, wallet.owned).find(row => row.id === "tech").highest, 2);
  assert.equal(model.guildCapabilityRows(badges, wallet.owned).find(row => row.id === "product").highest, 0);
  assert.equal(economy.adaptMedals(data).badges[0].tone, "gold");
});

test("the server eligibility and sequential approved level both gate applications", () => {
  const state = snapshot(1);
  assert.equal(model.guildCanApply(state, 1), false);
  assert.equal(model.guildCanApply(state, 2), true);
  assert.equal(model.guildCanApply(state, 3), false);
  state.requirements[1].eligible = false;
  assert.equal(model.guildCanApply(state, 2), false);
  assert.equal(state.level, 1);
});

test("pending blocks duplicate applications and returned requests permit retry without granting a rank", () => {
  const state = snapshot();
  state.requests.push({ id: "request-1", guildId: "multilingual", level: 1, status: "pending", evidence: [], submittedAt: "2026-11-09T00:00:00Z" });
  assert.equal(model.guildCanApply(state, 1), false);
  assert.equal(model.guildPendingRequest(state, 1).id, "request-1");
  state.requests[0].status = "returned";
  assert.equal(model.guildCanApply(state, 1), true);
  assert.equal(model.guildPendingRequest(state), undefined);
  assert.equal(state.level, 0);
});

const nativeRequire = createRequire(import.meta.url);
function renderGuild(state, view = "hall") {
  const compiledModule = { exports: {} };
  const source = ts.transpileModule(readFileSync(new URL("./GuildGrowthPage.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const dependencies = {
    "./ModuleShell": { ModulePanel: ({ children, className }) => React.createElement("section", { className }, children), ModuleIcon: ({ pack = "academy", file }) => React.createElement("img", { alt: "", "data-module-icon": file, src: load("./sharedAsset").sharedAsset(`/assets/project29/modules/${pack}/${file}.svg`) }) },
    "./JourneyDialogSurface": { JourneyDialogSurface: ({ children }) => React.createElement("div", null, children) },
    "./BadgeArtworkImage": { BadgeArtworkImage: () => null },
    "./BadgeShop": { Medal: () => null },
    "./useGuildGrowth": { useGuildGrowth: () => state },
    "./guildGrowthModel": model,
    "./badgeCatalog": load("./badgeCatalog"),
    "./badgeArtwork": load("./badgeArtwork"),
    "./guildGrowth.css": {},
  };
  vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports, require: name => Object.hasOwn(dependencies, name) ? dependencies[name] : nativeRequire(name) });
  return renderToStaticMarkup(React.createElement(compiledModule.exports.GuildGrowthPage, { view, identity: "当前学员", query: "", onView() {}, onBadges() {}, onTasks() {}, onAcademy() {}, onLab() {} }));
}
test("initial render waits for the account response without a fabricated zero rank", () => {
  const html = renderGuild({ snapshot: null, account: null, error: "", busy: false, refreshing: true, refresh() {} });
  assert.match(html, /正在读取你的公会认证和徽章凭证/);
  assert.doesNotMatch(html, /GUILD LEVEL|<strong>L0<\/strong>|尚未提交工会认证申请/);
  const failed = renderGuild({ snapshot: null, account: null, error: "暂时无法连接", busy: false, refreshing: false, refresh() {} });
  assert.match(failed, /role="alert"/);
  assert.match(failed, /重新读取/);
});
test("server rank and persisted review history display pending and returned reasons", () => {
  const state = snapshot(1);
  state.requests = [
    { id: "older", guildId: "multilingual", level: 2, status: "returned", evidence: [{ id: "id", name: "代码构筑者", grade: 2 }], submittedAt: "2026-11-08T00:00:00Z", reviewedAt: "2026-11-08T01:00:00Z", reviewerName: "审核员", reason: "请补充二级徽章凭证" },
    { id: "newer", guildId: "multilingual", level: 2, status: "pending", evidence: [{ id: "id", name: "代码构筑者", grade: 2 }], submittedAt: "2026-11-09T00:00:00Z", reviewedAt: null, reviewerName: null, reason: "" },
  ];
  const html = renderGuild({ snapshot: state, account: economy.adaptMedals({ medals: [], redemptions: [], wallet: { badgeBalances: {} } }), error: "", busy: false, refreshing: false, refresh() {} });
  assert.match(html, /<strong>规范实践<\/strong>/);
  assert.match(html, /申请待审核/);
  assert.match(html, /退回原因：请补充二级徽章凭证/);
  assert.match(html, /审核员/);
  assert.doesNotMatch(html, /本次会话已认证|会话演示/);
});


test("guild join selection never inherits the old global rank or another guild approval", () => {
  const state = snapshot(0);
  state.joinedGuild = null;
  state.legacyRequests = [{ id: "old-global", guildId: null, level: 3, status: "approved", evidence: [], submittedAt: "2026-11-01T00:00:00Z" }];
  assert.equal(model.guildActiveHall(state), null);
  assert.equal(model.guildCanApply(state, 1), false);
  state.joinedGuild = "functional";
  assert.equal(model.guildActiveHall(state), null);
  state.halls[7].joined = true;
  assert.equal(model.guildActiveHall(state).id, "functional");
  assert.equal(state.level, 0);
  state.requests = [{ id: "other", guildId: "multilingual", level: 1, status: "pending" }];
  assert.equal(model.guildPendingRequest(state), undefined);
  state.requirements[0].taskSubmitted = false;
  assert.equal(model.guildCanApply(state, 1), false);
});

test("task drafts and submissions are keyed by both guild and stage", () => {
  const state = snapshot();
  state.submissions = [
    { guildId: "functional", level: 1, taskId: "same-task", artifact: "职能工会成果", revision: 4 },
    { guildId: "multilingual", level: 2, taskId: "same-task", artifact: "多语种阶段二", revision: 2 },
    { guildId: "multilingual", level: 1, taskId: "same-task", artifact: "多语种阶段一", revision: 1 },
  ];
  assert.equal(model.guildSubmission(state, "multilingual", 1).artifact, "多语种阶段一");
  assert.equal(model.guildSubmission(state, "functional", 1).revision, 4);
  assert.equal(model.guildSubmission(state, "functional", 2), undefined);
  assert.notEqual(model.guildTaskScope("multilingual", 1), model.guildTaskScope("functional", 1));
  assert.notEqual(model.guildTaskScope("multilingual", 1), model.guildTaskScope("multilingual", 2));
});

test("task completion requires 60 to 6000 characters and every server-defined checklist item", () => {
  const task = snapshot().tasks[0];
  assert.ok(model.guildTaskValidation(task, { artifact: "证".repeat(59), checks: task.checks }));
  assert.equal(model.guildTaskValidation(task, { artifact: "证".repeat(60), checks: task.checks }), "");
  assert.equal(model.guildTaskValidation(task, { artifact: "证".repeat(6000), checks: task.checks }), "");
  assert.ok(model.guildTaskValidation(task, { artifact: "证".repeat(6001), checks: task.checks }));
  assert.ok(model.guildTaskValidation(task, { artifact: " ".repeat(60), checks: task.checks }));
  assert.ok(model.guildTaskValidation(task, { artifact: "证".repeat(60), checks: task.checks.slice(1) }));
  task.checks.push("新的服务端要求");
  assert.ok(model.guildTaskValidation(task, { artifact: "证".repeat(60), checks: ["需求", "质量", "验收"] }));
});

const renderState = state => ({ snapshot: state, account: economy.adaptMedals({ medals: [], redemptions: [], wallet: { badgeBalances: {} } }), error: "", busy: false, refreshing: false, refresh() {} });
test("hall renders eight selectable guilds and independent joined progress", () => {
  const state = snapshot();
  state.halls[7].joined = true;
  state.halls[7].level = 2;
  const html = renderGuild(renderState(state));
  assert.equal((html.match(/class="guild-hall-card/g) || []).length, 8);
  hallDefinitions.forEach(([, title]) => assert.ok(html.includes(title)));
  assert.match(html, /已加入 · 协同攻坚/);
  assert.match(html, /切换回该工会/);
  assert.match(html, /当前工会 · 待启用/);
  assert.doesNotMatch(html, /刷新或切换登录会清除/);
});

test("arena uses backend task templates and never claims a fictional mentor publication", () => {
  const html = renderGuild(renderState(snapshot()), "arena");
  taskTitles.forEach(title => assert.ok(html.includes(title)));
  assert.match(html, /认证任务模板/);
  assert.match(html, /管理员审核/);
  assert.doesNotMatch(html, /导师已发布|前端样例|确认进入下一阶段|会话演示/);
});

test("legacy approvals stay in a separate global history and do not certify the selected guild", () => {
  const state = snapshot();
  state.legacyRequests = [{ id: "legacy", guildId: null, level: 3, status: "approved", evidence: [], submittedAt: "2026-11-01T00:00:00Z", reviewedAt: "2026-11-02T00:00:00Z", reviewerName: "原审核员", reason: "旧认证" }];
  const html = renderGuild(renderState(state));
  assert.match(html, /旧版全局认证记录/);
  assert.match(html, /旧版全局认证 · L3/);
  assert.match(html, /尚未提交认证申请/);
  assert.match(html, /<strong>待启用<\/strong>/);
});


function hookHarness(initialSnapshot) {
  const slots = [];
  let cursor = 0;
  let identity = "learner-a";
  let serverSnapshot = initialSnapshot;
  let layoutEffects = [];
  let deferredMutation = null;
  const posts = [];
  const fakeReact = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], value => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useCallback: callback => callback,
    useEffect() {},
    useLayoutEffect(effect) { layoutEffects.push(effect); },
  };
  const compiledModule = { exports: {} };
  const source = ts.transpileModule(readFileSync(new URL("./useGuildGrowth.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(source, {
    module: compiledModule, exports: compiledModule.exports,
    require: name => name === "react" ? fakeReact : name === "./guildGrowthModel" ? model : nativeRequire(name),
    fetch: async (url, options) => {
      if (options?.method === "POST") {
        const command = JSON.parse(options.body);
        posts.push(command);
        if (deferredMutation) await deferredMutation;
        if (command.command === "join") {
          serverSnapshot = { ...serverSnapshot, joinedGuild: command.guildId, level: 0,
            halls: serverSnapshot.halls.map(hall => hall.id === command.guildId ? { ...hall, joined: true } : hall) };
        }
        return { ok: true, json: async () => serverSnapshot };
      }
      return { ok: true, json: async () => url.endsWith("/medals") ? { medals: [], redemptions: [], wallet: { badgeBalances: {} } } : serverSnapshot };
    },
  });
  return {
    posts,
    render(nextIdentity = identity) { identity = nextIdentity; cursor = 0; layoutEffects = []; const result = compiledModule.exports.useGuildGrowth(identity, false); layoutEffects.forEach(effect => effect()); return result; },
    defer() { let release; deferredMutation = new Promise(resolve => { release = resolve; }); return release; },
  };
}

test("a handler captured in guild A cannot save or apply A after switching to B", async () => {
  const harness = hookHarness(snapshot());
  await harness.render().refresh();
  const fromA = harness.render();
  assert.equal(await fromA.join("functional"), true);
  assert.equal(harness.render().snapshot.joinedGuild, "functional");
  assert.equal(await fromA.saveTask("multilingual", 1, { artifact: "证".repeat(60), checks: snapshot().tasks[0].checks, revision: 0 }, true), false);
  assert.equal(await fromA.submit("multilingual", 1, 1), false);
  assert.equal(harness.posts.length, 1);
});

test("a pending save keeps its explicit guild, stage and revision and blocks a competing switch", async () => {
  const harness = hookHarness(snapshot());
  await harness.render().refresh();
  const active = harness.render();
  const release = harness.defer();
  const saved = active.saveTask("multilingual", 1, { artifact: "已写草稿", checks: [], revision: 7 }, false);
  assert.equal(await active.join("functional"), false);
  assert.equal(harness.posts.length, 1);
  assert.deepEqual(harness.posts[0], { command: "task", guildId: "multilingual", level: 1, artifact: "已写草稿", checks: [], expectedRevision: 7, submit: false });
  release();
  assert.equal(await saved, true);
  assert.equal(harness.render().snapshot.joinedGuild, "multilingual");
});

test("an old account mutation response never populates the next account", async () => {
  const harness = hookHarness(snapshot());
  await harness.render().refresh();
  const active = harness.render();
  const release = harness.defer();
  const joining = active.join("functional");
  assert.equal(harness.render("learner-b").snapshot, null);
  release();
  assert.equal(await joining, false);
  assert.equal(harness.render().snapshot, null);
});


test("all eight guild card icons resolve to existing shared SVG resources", () => {
  const html = renderGuild(renderState(snapshot()));
  const icons = [...html.matchAll(/data-module-icon="([^"]+)" src="([^"]+)"/g)];
  for (const file of hallIcons) {
    const icon = icons.find(match => match[1] === file);
    assert.ok(icon, `missing icon ${file}`);
    assert.ok(existsSync(new URL(`../../../public${icon[2]}`, import.meta.url)), `missing file ${icon[2]}`);
  }
  assert.ok(html.includes('/assets/project29/modules/academy/42cb2.svg'));
  assert.ok(html.includes('/assets/project29/modules/academy/d7bdc.svg'));
  assert.ok(html.includes('/assets/project29/eec40.svg'));
  assert.ok(html.includes('/assets/project29/home-4062/8c48a.svg'));
});


test("certification applies with the exact submitted task revision the learner confirmed", async () => {
  const state = snapshot();
  state.submissions = [{ guildId: "multilingual", level: 1, taskId: "task-1", artifact: "证".repeat(60), checks: state.tasks[0].checks, status: "submitted", revision: 4 }];
  const harness = hookHarness(state);
  await harness.render().refresh();
  assert.equal(await harness.render().submit("multilingual", 1, 4), true);
  assert.deepEqual(harness.posts[0], { command: "apply", guildId: "multilingual", level: 1, expectedRevision: 4 });
});

test("a stale confirmation cannot apply a newer task revision or a draft", async () => {
  const state = snapshot();
  state.submissions = [{ guildId: "multilingual", level: 1, taskId: "task-1", artifact: "证".repeat(60), checks: state.tasks[0].checks, status: "submitted", revision: 5 }];
  const harness = hookHarness(state);
  await harness.render().refresh();
  const hook = harness.render();
  assert.equal(await hook.submit("multilingual", 1, 4), false);
  assert.equal(await hook.submit("multilingual", 1, 0), false);
  assert.equal(await hook.submit("multilingual", 1), false);
  state.submissions[0].status = "draft";
  assert.equal(await hook.submit("multilingual", 1, 5), false);
  state.submissions = [];
  assert.equal(await hook.submit("multilingual", 1, 5), false);
  assert.equal(harness.posts.length, 0);
});
