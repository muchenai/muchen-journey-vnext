import { escapeHtml as esc, icon } from './core.js?v=20261030-member-action-spacing';

function learnerOptions(learners) {
  const labels = learners.map(person => [person.name, person.department, person.detail].filter(Boolean).join(' · '));
  const counts = new Map();
  for (const label of labels) counts.set(label,(counts.get(label) || 0) + 1);
  return learners.map((person,index) => {
    const label = labels[index];
    const duplicate = counts.get(label) > 1;
    return `<option value="${esc(person.id)}" ${duplicate ? 'disabled' : ''}>${esc(label)}${duplicate ? '（同名待核对）' : ''}</option>`;
  }).join('');
}

export function grantModes(mode) {
  return `<fieldset class="xp-mode"><legend class="xp-sr">发放方式</legend>
    <label><input type="radio" name="mode" value="single" ${mode === 'single' ? 'checked' : ''}><span>${icon('award',16)}单人发放</span></label>
    <label><input type="radio" name="mode" value="list" ${mode === 'list' ? 'checked' : ''}><span>${icon('upload',16)}批量导表发放</span></label>
  </fieldset>`;
}

export function singleFields(learners) {
  return `<div data-xp-single>
        <div class="xp-fields xp-single-fields">
          <label class="xp-field">学员<select name="learner" required><option value="">选择学员</option>${learnerOptions(learners)}</select></label>
          <label class="xp-field">发放单位<select name="unit"><option value="xp">经验值</option><option value="points">线下积分</option></select></label>
          <label class="xp-field">发放数量<input name="amount" type="number" min="1" step="1" required placeholder="输入正整数"></label>
        </div><p class="xp-single-total" role="status"></p>
      </div>`;
}

export function singleGrant(form) {
  const {learner, unit, amount} = form.elements;
  const quantity = Number(amount.value);
  const xp = unit.value === 'xp' ? quantity : quantity * 10;
  if (!learner.value || !Number.isSafeInteger(quantity) || quantity <= 0 || !Number.isSafeInteger(xp)) return null;
  return {learnerId:learner.value, [unit.value]:quantity};
}

export function showGrantMode(form) {
  const single = form.elements.mode.value === 'single';
  const list = form.querySelector('[data-xp-list]');
  list.hidden = single;
  list.disabled = single;
  const panel = form.querySelector('[data-xp-single]');
  panel.hidden = !single;
  for (const control of panel.querySelectorAll('select,input')) control.disabled = !single;
  const row = singleGrant(form);
  panel.querySelector('[role=status]').textContent = row ? `将发放 ${(row.xp ?? row.points * 10).toLocaleString('zh-CN')} 经验` : '';
}
