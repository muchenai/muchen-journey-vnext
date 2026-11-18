import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";

const nativeRequire = createRequire(import.meta.url);
function compile(file, overrides) {
  const source = ts.transpileModule(readFileSync(new URL(`../src/app/${file}`, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const compiled = { exports: {} };
  vm.runInThisContext(`(function(require,module,exports){${source}\n})`)(
    name => name in overrides ? overrides[name] : nativeRequire(name), compiled, compiled.exports);
  return compiled.exports.default;
}

function taskRoute(destination, { village = true, fail } = {}) {
  let experienceLoads = 0;
  const page = compile("app/tasks/[assignmentId]/page.tsx", {
    "next/navigation": { redirect: path => { throw Error(`REDIRECT ${path}`); } },
    "@/lib/server/local-preview": { localVillagePreviewEnabled: () => village },
    "@/lib/server/api": { learnerPageRequest: async path => {
      assert.equal(path, "/api/v1/me/assignments/assignment-id/destination");
      if (fail) throw fail;
      return destination;
    } },
    "@/app/project-ui/experience-data": { loadProjectExperience: async id => {
      experienceLoads++;
      assert.equal(id, "assignment-id");
      return { learnerName: "学员", experience: { assignmentId: id } };
    } },
    "@/app/project29/App": { default: () => null },
  });
  return {
    open: view => page({ params: Promise.resolve({ assignmentId: "assignment-id" }), searchParams: Promise.resolve({ view }) }),
    loads: () => experienceLoads,
  };
}

test("new exploration review notifications resolve to the new task and its feedback", async () => {
  const route = taskRoute({ module: "exploration", taskId: "new-task" }, { village: false });
  await assert.rejects(route.open("review"), /^Error: REDIRECT \/app\?view=tasks&task=new-task&feedback=1$/);
  assert.equal(route.loads(), 0, "new tasks must never fall through to the old journey loader");
  await assert.rejects(route.open("evidence"), /^Error: REDIRECT \/app\?view=tasks&task=new-task$/);
});

test("novice notifications retain the village task destination", async () => {
  const route = taskRoute({ module: "village", taskId: "novice-task" });
  await assert.rejects(route.open("review"), /^Error: REDIRECT \/app\?view=village&task=novice-task$/);
  assert.equal(route.loads(), 0);
});

test("old exploration links still use the existing journey and review view", async () => {
  const route = taskRoute({ module: "legacy", taskId: null });
  const reviewed = await route.open("review");
  assert.equal(reviewed.props.initialScreen, "view");
  assert.equal(reviewed.props.experience.assignmentId, "assignment-id");
  const detail = await route.open(undefined);
  assert.equal(detail.props.initialScreen, "detail");
  assert.equal(route.loads(), 2);
});

test("an expired or inaccessible destination cannot silently open a different task", async () => {
  for (const reason of ["REDIRECT /?auth_error=LEARNER_SESSION_EXPIRED", "NOT_FOUND"]) {
    const route = taskRoute(null, { fail: Error(reason) });
    await assert.rejects(route.open("review"), error => error.message === reason);
    assert.equal(route.loads(), 0);
  }
});

test("the home route passes the selected task and feedback intent into the new experience", async () => {
  const home = compile("app/page.tsx", {
    "@/lib/server/local-preview": { localVillagePreviewEnabled: () => true },
    "@/app/project-ui/experience-data": { loadProjectExperience: async () => ({ learnerName: "学员", experience: null, needsNickname: false }) },
    "@/app/project29/App": { default: () => null },
  });
  const task = await home({ searchParams: Promise.resolve({ view: "tasks", task: "new-task", feedback: "1" }) });
  assert.equal(task.props.explorationTaskId, "new-task");
  assert.equal(task.props.explorationOpenFeedback, true);
  const village = await home({ searchParams: Promise.resolve({ view: "village", task: "novice-task", feedback: "1" }) });
  assert.equal(village.props.explorationTaskId, undefined);
  assert.equal(village.props.explorationOpenFeedback, false);
});
