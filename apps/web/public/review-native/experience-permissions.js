import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';
import { searchRows } from './member-access.js?v=20261125-certification';
import { experienceRequest } from './experience-request.js';

const endpoint = '/api/review-native/experience/permissions';

export function issuerWarning(person) {
  return person && !person.hasManagementAccess
    ? '「' + person.name + '」尚未开通管理系统访问权限。请先在「成员认证」中为其开通权限' : '';
}

function samePerson(first, second) {
  return Boolean(first && second &&
    ((first.id && first.id === second.id) || (first.openId && first.openId === second.openId)));
}

export function canSaveIssuers(people) {
  return people.length === 2 && people.every(person => person == null || (person.id && person.hasManagementAccess === true)) &&
    !samePerson(people[0], people[1]);
}

export function issuerSearchRows(people) {
  return searchRows(people.map(person => ({
    name: person.name, avatar: person.avatar, employee_no: person.employeeNo, job_title: person.jobTitle,
    department_paths: person.departmentPaths, departments: person.departments,
  })));
}

export function issuerHistory(history) {
  const rows = history.map(item => {
    const time = new Date(item.time);
    const displayTime = Number.isFinite(time.getTime()) ? time.toLocaleString('zh-CN', {hour12:false}) : '—';
    return `<tr><td>${e(displayTime)}</td><td>${e(item.operatorName || '—')}</td><td>发放管理员 ${e(item.slot)}</td><td>${e(item.beforeName || '未指定')}</td><td>${e(item.afterName || '未指定')}</td></tr>`;
  }).join('');
  const content = rows ? `<div class="table-wrap"><table class="data-table"><thead><tr><th scope="col">变更时间</th><th scope="col">操作人</th><th scope="col">发放岗位</th><th scope="col">变更前</th><th scope="col">变更后</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="field-hint">暂无权限变更记录</p>';
  return `<section class="xp-permission-history" aria-label="权限变更记录"><h3>权限变更记录</h3>${content}</section>`;
}

function issuerSlot(index) {
  return `<div data-issuer-slot="${index}" class="xp-issuer-field">
    <label class="form-field"><span class="field-label">发放管理员 ${index+1}</span>
      <input type="search" maxlength="60" autocomplete="off" placeholder="输入成员姓名或工号"
        aria-controls="xp-issuer-results" aria-describedby="xp-issuer-info-${index} xp-issuer-warning-${index}"></label>
    <small data-issuer-info id="xp-issuer-info-${index}" class="field-hint"></small>
    <p data-issuer-warning id="xp-issuer-warning-${index}" class="inline-error" role="status" hidden></p>
  </div>`;
}

export async function bindExperiencePermissions(root, ui, onChange) {
  if (!ui.canConfigureExperience) return;
  root.innerHTML = '<section class="certification-section" aria-label="发放管理员"><p role="status">正在读取经验发放权限…</p></section>';
  const panel = root.firstElementChild;
  async function load() {
    let data;
    try {
      data = await experienceRequest(undefined, endpoint);
    } catch (error) {
      if (!panel.isConnected) return;
      panel.innerHTML = '<p role="alert"></p>';
      panel.querySelector('p').textContent = error.message;
      if (error.status === 403) { onChange?.(); return; }
      const retry = document.createElement('button');
      retry.type = 'button'; retry.className = 'btn btn-secondary'; retry.textContent = '重新读取'; retry.onclick = load;
      panel.append(retry);
      return;
    }
    if (!panel.isConnected) return;
    const original = [data.issuers[0] ?? null, data.issuers[1] ?? null];
    const people = original.map(id => id ? data.selected.find(person => person.id === id) ?? {id, name:'原管理员'} : null);
    panel.innerHTML = '<h3>发放管理员</h3><p class="field-hint">按姓名或工号搜索公司成员，指定两位经验发放管理员。</p>' +
      '<form id="xp-roles"><div class="form-grid">' + issuerSlot(0) + issuerSlot(1) +
      '</div><div id="xp-issuer-results" data-issuer-results class="member-search-results" aria-live="polite" hidden></div>' +
      '<p data-save-error class="inline-error" role="alert" hidden></p>' +
      '<div class="modal-actions"><button type="submit" class="btn btn-primary" disabled>保存发放权限</button></div></form>' + issuerHistory(data.history || []);
    const form = panel.querySelector('form');
    const submit = form.querySelector('[type=submit]');
    const notice = form.querySelector('[data-save-error]');
    const results = form.querySelector('[data-issuer-results]');
    const slots = [...form.querySelectorAll('[data-issuer-slot]')];
    let saving = false;
    let version = 0, timer;

    function clearResults() {
      ++version;
      clearTimeout(timer);
      results.hidden = true;
      results.replaceChildren();
    }
    root.addEventListener('review-close', clearResults, {once:true});

    function readyToSave() {
      const changed = people.some((person, index) => (person?.id ?? null) !== original[index]);
      const resolved = slots.every((slot, index) => people[index] || !slot.querySelector('input').value.trim());
      return changed && resolved && canSaveIssuers(people);
    }

    function update() {
      const duplicate = samePerson(...people);
      slots.forEach((slot, index) => {
        const person = people[index];
        const warning = slot.querySelector('[data-issuer-warning]');
        warning.textContent = issuerWarning(person) || (duplicate ? '请选择两位不同的发放管理员。' : '');
        warning.hidden = !warning.textContent;
        const input = slot.querySelector('input');
        input.disabled = saving;
        input.setAttribute('aria-invalid', String(!warning.hidden));
        slot.querySelector('[data-issuer-info]').textContent = person?.employeeNo ? '工号：' + person.employeeNo : '';
      });
      submit.disabled = saving || !readyToSave();
    }

    slots.forEach((slot, index) => {
      const input = slot.querySelector('input');
      let composing = false;
      input.value = people[index]?.name ?? '';
      function schedule() {
        clearResults();
        const requestVersion = version;
        people[index] = null;
        notice.hidden = true;
        update();
        const query = input.value.trim();
        if (composing || !query) return;
        results.textContent = '正在搜索公司成员…';
        results.hidden = false;
        timer = setTimeout(async () => {
          if (!slot.isConnected || requestVersion !== version) return;
          try {
            const data = await experienceRequest(undefined, endpoint + '/search?' + new URLSearchParams({q:query}));
            if (!slot.isConnected || requestVersion !== version) return;
            if (data.directory?.ready === false) { results.textContent = '公司通讯录正在准备中，请稍候。'; return; }
            results.innerHTML = issuerSearchRows(data.items) + (data.has_more ? '<p class="muted">结果较多，请输入更完整的姓名或工号。</p>' : '');
            results.querySelectorAll('[data-member-choice]').forEach(button => {
              button.onclick = () => {
                if (requestVersion !== version || saving) return;
                people[index] = data.items[Number(button.dataset.memberChoice)];
                input.value = people[index].name;
                clearResults();
                update();
                input.focus();
              };
            });
          } catch (error) {
            if (!slot.isConnected || requestVersion !== version) return;
            results.textContent = error.message;
            if (error.status === 403) onChange?.();
          }
        }, 200);
      }
      input.oninput = schedule;
      input.onfocus = () => {
        if (input.value.trim() && !people[index]) schedule();
        else clearResults();
      };
      input.addEventListener('compositionstart', () => { composing = true; schedule(); });
      input.addEventListener('compositionend', () => { composing = false; schedule(); });
    });
    update();
    form.onsubmit = async event => {
      event.preventDefault();
      if (saving || !readyToSave()) return;
      saving = true;
      root.dataset.operationPending = 'true';
      notice.hidden = true;
      update();
      try {
        await experienceRequest({action:'configure', issuers:people.map(person => person?.id ?? null), revision:data.revision}, endpoint);
        ui.toast('发放权限已保存');
        onChange?.({issuers:people.map(person => person?.id ?? null)});
        if (panel.isConnected) await load();
      } catch (error) {
        if (!panel.isConnected) return;
        if (error.status === 409) { ui.toast(error.message,'error'); await load(); }
        else {
          notice.textContent = error.message;
          notice.hidden = false;
          if (error.status === 403) onChange?.();
        }
      } finally {
        saving = false;
        delete root.dataset.operationPending;
        if (form.isConnected) update();
      }
    };
  }
  await load();
}
