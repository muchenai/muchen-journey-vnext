import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const compiledModule = { exports: {} };
const source = ts.transpileModule(readFileSync(new URL("../src/app/project29/taskDepartments.ts", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
vm.runInNewContext(source, { module: compiledModule, exports: compiledModule.exports, require: () => ({ pointTypeIds: {}, badgePointTypes: [] }) });
const { taskDepartments, belongsToDepartment, isTaskDepartmentFilter, taskDepartmentName } = compiledModule.exports;

test("guild functional aggregate uses actual publishing departments and excludes all seven delivery lines", () => {
  assert.equal(isTaskDepartmentFilter("functional"), true);
  assert.equal(taskDepartmentName("functional"), "综合职能公会");
  for (const department of taskDepartments) {
    const task = { publishingDepartment: department.name, category: "数据交付", rewardAllocations: [{id: "data", points: 10}] };
    assert.equal(belongsToDepartment(task, "functional"), !department.delivery);
    assert.equal(belongsToDepartment(task, "delivery"), department.delivery);
  }
  assert.equal(belongsToDepartment({ publishingDepartment: "待补充部门" }, "functional"), false);
  assert.equal(belongsToDepartment({}, "functional"), false);
});
