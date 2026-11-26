import { escapeHtml as e } from './core.js?v=20261030-member-action-spacing';
import { requestCourseWorkspace } from './academy-workspace.js';

const endpoint = '/api/review-native/course-access';

function scopeLabel(tags) {
  return tags.length ? tags.join('、') : '全部课程';
}

function memberRow(person, assignments, tags) {
  const reviewer = assignments.reviewers.find(row => row.personId === person.id);
  const name = e(person.name);
  return `<tr data-course-member="${e(person.id)}">
    <th scope="row">${name}</th>
    <td><input type="checkbox" name="admin" aria-label="${name} 普通管理员" ${assignments.adminIds.includes(person.id) ? 'checked' : ''}></td>
    <td><input type="checkbox" name="reviewer" aria-label="${name} 课程审核人" ${reviewer ? 'checked' : ''}></td>
    <td><span data-no-scope ${reviewer ? 'hidden' : ''}>—</span>
      <details data-scope-selector ${reviewer ? '' : 'hidden'}><summary aria-label="${name} 可审核范围"><span data-scope-label>${e(scopeLabel(reviewer?.tagNames || []))}</span></summary>
        <div class="aw-scope">${tags.map(tag => `<label><input type="checkbox" name="scope" value="${e(tag)}" ${reviewer?.tagNames.includes(tag) ? 'checked' : ''}>${e(tag)}</label>`).join('') || '暂无课程标签'}</div>
      </details></td></tr>`;
}

function editorMarkup(data, assignments) {
  return `<p class="ac-muted">新手村和 AI 学院共用以下权限。课程负责人可直接发布，普通管理员发布的课程由其他有权限的成员审核。</p>
    <div class="course-permissions-fields">
      <label class="ac-field"><span>课程负责人</span><select name="ownerId">${data.people.map(p =>
        `<option value="${e(p.id)}" ${p.id === assignments.ownerId ? 'selected' : ''}>${e(p.name)}</option>`).join('')}</select></label>
      <form data-add-course-member><label class="ac-field"><span>新增课程管理成员</span><input name="memberName" maxlength="80" required placeholder="输入成员姓名"></label>
        <button type="submit" class="btn btn-secondary">添加成员</button></form>
    </div>
    <form data-course-roles class="course-permissions-roles">
      <h3>成员权限</h3><p class="ac-muted">可限定审核人负责的课程标签。留空时可审核全部课程。</p>
      <div class="ac-table-wrap"><table class="ac-table course-permissions-table"><thead><tr><th scope="col">成员</th><th scope="col">普通管理员</th><th scope="col">审核人</th><th scope="col">可审核范围</th></tr></thead>
      <tbody>${data.people.map(person => memberRow(person, assignments, data.tags)).join('')}</tbody></table></div>
      <div class="ac-form-footer"><button type="submit" class="btn btn-primary">保存课程权限</button></div>
    </form>
    <p data-course-error class="ac-inline-error" role="alert"></p>`;
}

function bindAssignments(section, ui, redraw, revision) {
  const rows = [...section.querySelectorAll('[data-course-member]')];
  const checkedTags = row => [...row.querySelectorAll('[name=scope]:checked')].map(input => input.value);
  function readAssignments() {
    return {
      ownerId: section.querySelector('[name=ownerId]').value,
      adminIds: rows.filter(row => row.querySelector('[name=admin]').checked).map(row => row.dataset.courseMember),
      reviewers: rows.filter(row => row.querySelector('[name=reviewer]').checked).map(row => ({
        personId: row.dataset.courseMember, tagNames: checkedTags(row),
      })),
    };
  }
  rows.forEach(row => {
    const reviewer = row.querySelector('[name=reviewer]');
    reviewer.onchange = () => {
      row.querySelector('[data-no-scope]').hidden = reviewer.checked;
      row.querySelector('[data-scope-selector]').hidden = !reviewer.checked;
    };
    row.querySelector('[data-scope-selector]').onchange = () => {
      row.querySelector('[data-scope-label]').textContent = scopeLabel(checkedTags(row));
    };
  });
  const panel = section.parentElement;
  const notice = section.querySelector('[data-course-error]');
  async function submit(body, draftAssignments) {
    if (panel.dataset.operationPending === 'true') return;
    panel.dataset.operationPending = 'true';
    section.setAttribute('aria-busy','true');
    const fields = section.querySelectorAll('input, select, button');
    fields.forEach(input => { input.disabled = true; });
    notice.textContent = '';
    try {
      const result = await requestCourseWorkspace(endpoint, { ...body, revision });
      redraw(result, draftAssignments);
      ui.toast(body.action === 'saveRoles' ? '课程权限已保存' : '课程管理成员已添加');
      ui.onPermissionsChanged?.();
    } catch (err) {
      notice.textContent = err.message;
    } finally {
      delete panel.dataset.operationPending;
      section.removeAttribute('aria-busy');
      fields.forEach(input => { input.disabled = false; });
    }
  }
  section.querySelector('[data-add-course-member]').onsubmit = event => {
    event.preventDefault();
    const input = event.currentTarget.elements.memberName;
    const name = input.value.trim();
    if (!name) { notice.textContent = '请输入成员姓名。'; input.focus(); return; }
    void submit({action:'addPerson', name}, readAssignments());
  };
  section.querySelector('[data-course-roles]').onsubmit = event => {
    event.preventDefault();
    void submit({action:'saveRoles', assignments:readAssignments()});
  };
}

export async function mountCoursePermissions(root, ui) {
  root.innerHTML = '<section class="course-permissions"><p class="ac-muted" role="status">正在读取课程权限…</p></section>';
  const section = root.firstElementChild;
  function render(data, assignments = data.assignments) {
    if (data.actorId !== data.assignments.ownerId) {
      const owner = data.people.find(person => person.id === data.assignments.ownerId);
      section.innerHTML = `<p class="ac-muted">课程权限由课程负责人${owner ? `「${e(owner.name)}」` : ''}管理。</p>`;
      return;
    }
    section.innerHTML = editorMarkup(data,assignments);
    bindAssignments(section,ui,render,data.revision);
  }
  try {
    render(await requestCourseWorkspace(endpoint));
  } catch (err) {
    section.innerHTML = `<p class="ac-inline-error" role="alert">${e(err.message)}</p><button type="button" class="btn btn-secondary">重新加载</button>`;
    section.querySelector('button').onclick = () => { void mountCoursePermissions(root,ui); };
  }
}
