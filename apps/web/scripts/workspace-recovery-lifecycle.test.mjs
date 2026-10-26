import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
import ts from "typescript";

// Run the actual hook with controlled React effects, storage and network responses.
// This simulates page unmount/remount without issuing AI calls or writing real data.
function mount({ storage, records, draft = "" }) {
  const cells = [], effects = [], timers = new Map(), saves = [];
  let cursor = 0, dirty = true, output, timerId = 0;
  const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const react = {
    useState(initial) {
      const i = cursor++;
      if (!(i in cells)) cells[i] = { value: initial };
      return [cells[i].value, value => {
        if (!Object.is(value, cells[i].value)) { cells[i].value = value; dirty = true; }
      }];
    },
    useRef(initial) { const i = cursor++; return cells[i] ??= { current: initial }; },
    useCallback(fn, deps) {
      const i = cursor++;
      if (!same(cells[i]?.deps, deps)) cells[i] = { fn, deps };
      return cells[i].fn;
    },
    useEffect(fn, deps) {
      const i = cursor++;
      if (!same(cells[i]?.deps, deps)) effects.push(() => {
        cells[i]?.cleanup?.();
        cells[i] = { deps, cleanup: fn() };
      });
    },
  };
  const window = {
    setTimeout(fn, delay) { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  };
  const context = vm.createContext({ window, localStorage: storage, FormData, AbortController, Date, JSON,
    crypto: { randomUUID: () => "test-draft-key" },
    fetch: async () => ({ ok: true, json: async () => ({ records: records.value }) }),
  });
  const load = file => {
    const compiled = ts.transpileModule(readFileSync(new URL(file, import.meta.url), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    const compiledModule = { exports: {} };
    vm.runInContext(`(function(require,module,exports){${compiled}\n})`, context)(specifier => {
      if (specifier === "react") return react;
      if (specifier === "../actions") return { saveSubmissionDraft: async (_state, data) => {
        saves.push(data.get("body")); return { savedAt: "now" };
      } };
      if (specifier === "./workspace-recovery") return load("../src/app/project29/workspace-recovery.ts");
      throw new Error(`Unexpected dependency ${specifier}`);
    }, compiledModule, compiledModule.exports);
    return compiledModule.exports;
  };
  const { useWorkspaceRecovery } = load("../src/app/project29/useWorkspaceRecovery.ts");
  const experience = { assignmentId: "task-a", taskVersion: 1, revision: 3, allowedCommands: ["submit"], draftBody: draft, latestSubmissionBody: null };
  function TestComponent() {
    return useWorkspaceRecovery(experience, true);
  }
  return {
    get value() { return output; }, saves,
    async flush() {
      for (let i = 0; i < 20; i++) {
        if (dirty) {
          dirty = false; cursor = 0;
          output = TestComponent();
          effects.splice(0).forEach(fn => fn());
        }
        await new Promise(resolve => setImmediate(resolve));
        if (!dirty) return;
      }
      throw new Error("Hook did not settle");
    },
    async timer(delay) {
      const entry = [...timers].find(([, timer]) => timer.delay === delay);
      assert.ok(entry, `missing ${delay} ms timer`);
      timers.delete(entry[0]);
      await entry[1].fn();
      await this.flush();
    },
    unmount() { cells.forEach(cell => cell?.cleanup?.()); },
  };
}

const storage = () => {
  const entries = new Map();
  return { getItem: key => entries.get(key) ?? null, setItem: (key, value) => entries.set(key, value) };
};
const answer = "https://test.feishu.cn/docx/answerdocument123";
const row = status => ({ id: "check", body: answer, status, createdAt: new Date().toISOString(), result: "evaluation" });

test("leaving during self-check restores the link and busy state; server completion enables submit", async () => {
  const local = storage(), server = { value: [] };
  const first = mount({ storage: local, records: server });
  await first.flush();
  first.value.updateRecord(answer);
  first.value.beginSelfCheck();
  first.unmount();
  server.value = [row("RUNNING")];
  const returned = mount({ storage: local, records: server });
  await returned.flush();
  assert.equal(returned.value.record, answer);
  assert.equal(returned.value.selfCheckBusy, true);
  assert.equal(returned.value.selfCheckInFlight.current, true);
  server.value = [row("COMPLETED")];
  await returned.timer(3000);
  assert.equal(returned.value.selfCheckBusy, false);
  assert.equal(returned.value.selfCheckInFlight.current, false);
  assert.match(returned.value.workspaceMessage, /已完成/);
  assert.equal(returned.value.record, answer);
  returned.unmount();
});

test("server history restores an older lost link and a failed check releases submit", async () => {
  const server = { value: [row("RUNNING")] };
  const page = mount({ storage: storage(), records: server });
  await page.flush();
  assert.equal(page.value.record, answer);
  server.value = [{ ...row("FAILED"), result: "AI 暂时不可用，请重试。" }];
  await page.timer(3000);
  assert.equal(page.value.selfCheckBusy, false);
  assert.match(page.value.workspaceMessage, /请重试/);
  assert.equal(page.value.record, answer);
  page.unmount();
});

test("ordinary edits autosave and an intentionally cleared link does not resurrect from history", async () => {
  const local = storage(), server = { value: [] };
  const page = mount({ storage: local, records: server });
  await page.flush();
  page.value.updateRecord(answer);
  await page.flush();
  await page.timer(1200);
  assert.deepEqual(page.saves, [answer]);
  page.value.updateRecord("");
  page.unmount();
  server.value = [row("COMPLETED")];
  const returned = mount({ storage: local, records: server, draft: answer });
  await returned.flush();
  assert.equal(returned.value.record, "");
  returned.unmount();
});

test("historical evaluations never fill or autosave a fresh empty task", async () => {
  for (const status of ["COMPLETED", "FAILED", "UNCERTAIN"]) {
    const page = mount({ storage: storage(), records: { value: [row(status)] } });
    await page.flush();
    assert.equal(page.value.record, "");
    assert.equal(page.value.selfCheckBusy, false);
    await page.timer(3000);
    assert.equal(page.value.record, "");
    assert.deepEqual(page.saves, []);
    page.unmount();
  }
});

test("a learner's saved draft survives even when history contains a different link", async () => {
  const draft = "https://test.feishu.cn/docx/currentlearnerdraft";
  const page = mount({ storage: storage(), draft, records: { value: [row("COMPLETED")] } });
  await page.flush();
  assert.equal(page.value.record, draft);
  page.unmount();
});
