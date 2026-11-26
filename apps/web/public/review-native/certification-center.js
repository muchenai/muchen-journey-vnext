import { mountMemberCertification } from './member-access.js?v=20261125-certification';
import { mountCoursePermissions } from './academy-course-permissions.js';
import { bindExperiencePermissions } from './experience-permissions.js';

export function openCertificationCenter(store, ui, { preferred = 'members', memberSearch = '', onPermissionsChanged } = {}) {
  const tabs = [
    ...(ui.isSuperAdmin ? [{ id: 'members', label: '成员认证' }] : []),
    { id: 'courses', label: '课程人员与权限' },
    ...(ui.canConfigureExperience === true ? [{ id: 'experience', label: '经验发放权限' }] : []),
  ];
  if (!tabs.length) return;

  const tabButtons = tabs.map(({ id, label }) =>
    `<button type="button" role="tab" id="cert-tab-${id}" aria-controls="cert-panel" data-cert-tab="${id}">${label}</button>`).join('');
  ui.openModal(`<header class="cert-center-heading"><h2 id="cert-center-title">认证与权限</h2></header>
    <div class="cert-center-tabs" role="tablist" aria-label="权限设置">${tabButtons}</div>
    <div class="cert-center-body"></div>`, modal => {
    modal.classList.add('cert-center');
    modal.setAttribute('aria-labelledby', 'cert-center-title');
    modal.removeAttribute('aria-label');
    const buttons = [...modal.querySelectorAll('[data-cert-tab]')];
    const body = modal.querySelector('.cert-center-body');
    let selected, panel;
    const panelUI = Object.create(ui);
    panelUI.onPermissionsChanged = onPermissionsChanged;
    panelUI.showMemberCertification = (search = '') => openCertificationCenter(store, ui, {
      preferred: 'members', memberSearch: search, onPermissionsChanged,
    });
    const dispose = () => panel?.dispatchEvent(new Event('review-close'));
    modal.addEventListener('review-close', dispose, { once: true });

    function select(id) {
      if (selected === id || panel?.dataset.operationPending === 'true' || modal.dataset.operationPending === 'true') return;
      dispose();
      selected = id;
      for (const button of buttons) {
        const active = button.dataset.certTab === id;
        button.setAttribute('aria-selected', String(active));
        button.tabIndex = active ? 0 : -1;
      }
      // Detaching the old panel also prevents late responses from replacing the selected tab.
      panel = document.createElement('section');
      panel.id = 'cert-panel';
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', 'cert-tab-' + id);
      body.replaceChildren(panel);
      if (id === 'members') mountMemberCertification(panel, store, panelUI, memberSearch);
      else if (id === 'courses') void mountCoursePermissions(panel, panelUI);
      else void bindExperiencePermissions(panel, panelUI, onPermissionsChanged);
    }
    for (const [index, button] of buttons.entries()) {
      button.onclick = () => select(button.dataset.certTab);
      button.onkeydown = event => {
        const next = { ArrowRight: (index + 1) % buttons.length, ArrowLeft: (index + buttons.length - 1) % buttons.length,
          Home: 0, End: buttons.length - 1 }[event.key];
        if (next === undefined) return;
        event.preventDefault();
        select(buttons[next].dataset.certTab);
        buttons.find(item => item.dataset.certTab === selected)?.focus();
      };
    }
    select(tabs.some(tab => tab.id === preferred) ? preferred : tabs[0].id);
  });
}
