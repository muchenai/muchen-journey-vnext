import { escapeHtml as esc, icon } from './core.js?v=20261030-member-action-spacing';
import { bindGrantRoster } from './offline-experience-roster.js';

import { grantModes, singleFields, singleGrant, showGrantMode } from './offline-experience-modes.js';

const sample = [{name:'张三', points:2}, {name:'李四', points:3}];
const storageKey = 'journey:experience:feishu-demo:last-grant:v1';
const departments = ['产品部','开发部','培训部','运营部'];

export function simulatedDirectory(names, rows) {
  const occurrences = new Map();
  for (const row of rows) {
    const name = row.name.trim();
    occurrences.set(name,(occurrences.get(name) || 0) + 1);
  }
  const matches = names.map((name,index) => {
    const count = Math.max(index === 0 ? 2 : 1, occurrences.get(name) || 1);
    const candidates = Array.from({length:count},(_,i) => ({
      id:`demo:${name}:${i}`, name,
      department:departments[(index+i) % departments.length],
      detail:i >= departments.length ? `演示小组 ${Math.floor(i / departments.length) + 1}` : '',
    }));
    return {name,candidates};
  });
  const count = matches.reduce((sum,group)=>sum+group.candidates.length,0);
  return {source:'demo',sourceLabel:`模拟飞书通讯录 · 找到 ${count} 位候选人`,snapshotId:'demo-only',matches};
}

let latestRecords = [];
function readRecords() {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
    if (Array.isArray(value)) latestRecords = value;
  } catch { /* Keep in-memory history when browser storage is unavailable. */ }
  return latestRecords;
}

function saveRecords(records) {
  latestRecords = [...records, ...readRecords()];
  try { sessionStorage.setItem(storageKey,JSON.stringify(latestRecords)); } catch { /* The result remains visible in this tab. */ }
}

export function bindExperienceDemo(root, {rows, batch, reason, mode, historyPanel, exit}) {
  const people = simulatedDirectory(sample.map(row=>row.name),sample).matches.flatMap(group=>group.candidates);
  root.innerHTML = `<section class="xp-panel xp-demo-panel" aria-labelledby="xp-demo-heading">
    <div class="xp-heading-row"><h2 id="xp-demo-heading">经验发放演示</h2><button class="btn btn-secondary" type="button" data-xp-exit>退出模拟</button></div>
    <p class="xp-demo-note">可选一位模拟学员直接发放，也可导入名单批量发放。演示记录仅保存在当前标签页。</p>
    <form><fieldset class="xp-controls">
      ${grantModes(mode)}
      <div class="xp-fields xp-batch-fields">
        <label class="xp-field">培训批次<input name="batch" required maxlength="100" value="${esc(batch || '入职培训演示')}"></label>
        <label class="xp-field">发放事由<input name="reason" required maxlength="240" value="${esc(reason || '完成线下培训')}"></label>
      </div>
      <fieldset class="xp-controls" data-xp-list></fieldset>
      ${singleFields(people)}
      <div class="xp-footer"><button type="submit" class="btn btn-primary" disabled>${icon('send',16)}确认模拟发放</button></div>
    </fieldset></form></section>
    <div data-xp-demo-result role="status"></div><div data-xp-demo-history></div>`;
  const form = root.querySelector('form');
  const submit = form.querySelector('[type=submit]');
  const result = root.querySelector('[data-xp-demo-result]');
  const history = root.querySelector('[data-xp-demo-history]');
  const exitButton = root.querySelector('[data-xp-exit]');
  exitButton.onclick = exit;
  function renderHistory() {
    history.innerHTML = historyPanel({grants:readRecords(),canGrant:true},true);
  }
  renderHistory();
  let roster;
  let directory = new Map();
  const holder = root.querySelector('[data-xp-list]');
  const isList = () => form.elements.mode.value === 'list';
  function update() {
    showGrantMode(form);
    submit.disabled = !(isList() ? roster?.isReady() : singleGrant(form));
  }
  form.addEventListener('input',update);
  form.addEventListener('change',update);
  roster = bindGrantRoster(holder,{
    isSimulation:()=>true,
    async matchNames(names) {
      // Give the same loading state as an actual lookup without contacting Feishu.
      await new Promise(resolve=>setTimeout(resolve,650));
      const response = simulatedDirectory(names,roster.getDraftRows());
      directory = new Map(response.matches.flatMap(group=>group.candidates.map(person=>[person.id,person])));
      return response;
    },
    onChange:update,
  });
  const custom = rows.length > 0;
  const initialRows = custom ? rows : sample;
  function start() {
    result.replaceChildren();
    form.hidden = false;
    return roster.loadSample(initialRows,custom ? '已导入名单' : '示例名单');
  }
  form.onsubmit = event => {
    event.preventDefault();
    if (form.hidden || submit.disabled || !form.reportValidity()) return;
    const time = new Date().toISOString();
    const selected = isList() ? roster.getRows() : [singleGrant(form)];
    const grants = selected.map(row=>{
      const person = isList() ? directory.get(row.learnerId) : people.find(p=>p.id === row.learnerId);
      return {name:person.name, department:person.department, points:row.points ?? null, xp:row.xp ?? row.points * 10,
        batch:form.elements.batch.value.trim(), reason:form.elements.reason.value.trim(), by:'模拟管理员', time};
    });
    saveRecords(grants);
    form.hidden = true;
    const total = grants.reduce((sum, row)=>sum+row.xp,0);
    result.innerHTML = `<div class="xp-demo-receipt"><div>${icon('checkCircle',20)}<strong>模拟发放完成</strong><span>${grants.length} 人，共 ${total.toLocaleString('zh-CN')} 经验</span></div><button class="btn btn-secondary" type="button">再试一次</button></div>`;
    result.querySelector('button').onclick = start;
    renderHistory();
  };
  void start();
}
