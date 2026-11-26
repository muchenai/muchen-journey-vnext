import {experienceRequest as request} from './experience-request.js';
import { escapeHtml as esc, icon } from './core.js?v=20261030-member-action-spacing';

import { bindGrantRoster } from './offline-experience-roster.js';
import { bindExperienceDemo } from './offline-experience-demo.js?v=20261126-single';
import { grantModes, singleFields, singleGrant, showGrantMode } from './offline-experience-modes.js';

const endpoint = '/api/review-native/experience';
const formatNumber = number => Number(number).toLocaleString('zh-CN');

function grantPanel(data) {
  const heading = `<div class="xp-heading-row"><h2 id="xp-grant-heading">发放经验</h2><button class="btn btn-secondary xp-demo-entry" type="button" data-xp-open-demo>${icon('eye',16)}发放演示</button></div>`;
  return `<section class="xp-panel" aria-labelledby="xp-grant-heading">${heading}
    <form id="xp-grant"><fieldset class="xp-controls">
      ${grantModes('single')}
      <div class="xp-fields xp-batch-fields">
        <label class="xp-field">培训批次<input name="batch" required maxlength="100" placeholder="例如：11 月入职培训第一批"></label>
        <label class="xp-field">发放事由<input name="reason" required maxlength="240" placeholder="例如：完成线下入职培训"></label>
      </div>
      <fieldset class="xp-controls" data-xp-list disabled hidden></fieldset>
      ${singleFields(data.learners)}
      <p class="xp-error" data-xp-error role="alert" hidden></p>
      <div class="xp-footer"><button type="submit" class="btn btn-primary" disabled>${icon('send',16)}<span>确认发放经验</span></button></div>
    </fieldset></form></section>`;
}

function historyPanel({grants},demo=false) {
  const rows = grants.map(grant => {
    const date = new Date(grant.time);
    const time = Number.isNaN(date.valueOf()) ? '—' : date.toLocaleString('zh-CN',{hour12:false});
    return `<tr><td><strong>${esc(grant.name)}</strong>${grant.department ? `<small>${esc(grant.department)}</small>` : ''}</td>
      <td><strong>${esc(grant.batch)}</strong><small>${esc(grant.reason)}</small></td>
      <td class="xp-numeric">${grant.points == null ? '—' : formatNumber(grant.points)}</td>
      <td class="xp-numeric xp-earned">+${formatNumber(grant.xp ?? grant.points * 10)}</td>
      <td>${esc(grant.by)}</td><td class="xp-date">${esc(time)}</td></tr>`;
  }).join('');
  const title = demo ? '模拟发放记录' : '发放记录';
  const headingId = demo ? 'xp-demo-history-heading' : 'xp-history-heading';
  return `<section class="xp-panel" aria-labelledby="${headingId}">
    <div class="xp-heading-row"><h2 id="${headingId}">${title}</h2><span class="xp-count">${formatNumber(grants.length)} 条记录</span></div>
    ${rows ? `<div class="xp-table-scroll" role="region" aria-label="${title}" tabindex="0"><table class="xp-history-table"><thead><tr>
      <th scope="col">学员</th><th scope="col">培训批次 / 事由</th><th scope="col" class="xp-numeric">线下积分</th><th scope="col" class="xp-numeric">发放经验</th><th scope="col">操作人</th><th scope="col">发放时间</th>
      </tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="xp-empty">${icon('clock',22)}<p>暂无${title}</p></div>`}
  </section>`;
}

function bindGrantForm(form, ui, onIssued) {
  const {batch,reason} = form.elements;
  const submit = form.querySelector('[type=submit]');
  const notice = form.querySelector('[data-xp-error]');
  const listPanel = form.querySelector('[data-xp-list]');
  const isList = () => form.elements.mode.value === 'list';
  let busy = false;
  let roster;
  function update() {
    showGrantMode(form);
    submit.disabled = busy || !(isList() ? roster?.isReady() : singleGrant(form));
  }
  roster = bindGrantRoster(listPanel,{
    matchNames:async names=>{
      try { return await request({names},endpoint + '/directory'); }
      catch(error){ if(error.status===403 && form.isConnected) ui.denyExperience(); throw error; }
    },
    onChange:update,
  });
  function setMode() {
    notice.hidden = true;
    update();
  }
  for (const choice of form.querySelectorAll('input[name=mode]')) choice.onchange = setMode;
  form.addEventListener('input',()=>{ notice.hidden = true; update(); });
  setMode();
  form.onsubmit = async event => {
    event.preventDefault();
    if (busy || submit.disabled || !form.reportValidity()) return;
    notice.hidden = true;
    try {
      const list = isList();
      const rows = list ? roster.getRows() : [singleGrant(form)];
      const body = {action:'grant',batch:batch.value.trim(),reason:reason.value.trim(),mode:list?'list':'single',rows};
      if (list) body.snapshotId = roster.getSnapshotId();
      busy = true;
      form.closest('.xp-panel').querySelector('[data-xp-open-demo]').disabled = true;
      form.querySelector('.xp-controls').disabled = true;
      roster.setBusy(true);
      submit.querySelector('span').textContent = '正在发放…';
      update();
      const result = await request(body);
      const message = result.added ? `已向 ${result.added} 位学员发放经验` : '该名单已完成发放';
      ui.toast(message + (result.skipped ? `，${result.skipped} 条已发记录已跳过` : ''));
      if (form.isConnected) await onIssued();
    } catch (error) {
      if(error.status===403 && form.isConnected){ui.denyExperience();return;}
      notice.textContent = error.message;
      notice.hidden = false;
    } finally {
      if (form.isConnected) {
        busy = false;
        form.closest('.xp-panel').querySelector('[data-xp-open-demo]').disabled = false;
        form.querySelector('.xp-controls').disabled = false;
        roster.setBusy(false);
        submit.querySelector('span').textContent = '确认发放经验';
        update();
      }
    }
  };
  return roster;
}

export async function bindOfflineExperience(root, ui) {
  const page = document.createElement('div');
  page.className = 'xp-workspace';
  page.innerHTML = `<header class="xp-page-heading"><div><h1>经验管理</h1><p>每 1 线下积分可发放 10 经验</p></div><span data-xp-identity></span></header>
    <div class="xp-sections" data-xp-live><p role="status">正在读取经验管理数据…</p></div>
    <div class="xp-sections" data-xp-demo hidden></div>`;
  root.replaceChildren(page);
  const live = page.querySelector('[data-xp-live]');
  const demo = page.querySelector('[data-xp-demo]');
  const identity = page.querySelector('[data-xp-identity]');
  let form, roster;
  function toggleDemo(active, mode = 'single') {
    const url = new URL(location.href);
    if (active) url.searchParams.set('demo',mode === 'list' ? 'feishu' : 'single');
    else url.searchParams.delete('demo');
    window.history.replaceState(window.history.state,'',url);
    live.hidden = active;
    demo.hidden = !active;
    identity.hidden = active;
    if (active) {
      bindExperienceDemo(demo,{
        rows:roster?.getDraftRows() ?? [], batch:form?.elements.batch.value, reason:form?.elements.reason.value,
        mode,historyPanel,exit:()=>toggleDemo(false),
      });
    } else {
      demo.replaceChildren();
      const entry = live.querySelector('[data-xp-open-demo]');
      if (entry) entry.focus();
      else void load();
    }
  }
  async function load() {
    try {
      const data = await request();
      if (!page.isConnected) return;
      if(!data.canGrant){ui.denyExperience();return;}
      identity.textContent = '当前身份 · ' + data.current.name;
      live.innerHTML = grantPanel(data) + historyPanel(data);
      form = live.querySelector('#xp-grant');
      roster = form && bindGrantForm(form,ui,load);
      live.querySelector('[data-xp-open-demo]').onclick = ()=>toggleDemo(true,form?.elements.mode.value);
    } catch (error) {
      if (!page.isConnected) return;
      if(error.status===403){ui.denyExperience();return;}
      live.innerHTML = `<div class="xp-panel"><p role="alert">${esc(error.message)}</p><button type="button" class="btn btn-secondary">重新读取</button></div>`;
      live.querySelector('button').onclick = load;
    }
  }
  const initialDemo = new URL(location.href).searchParams.get('demo');
  await load();
  if (page.isConnected && form && (initialDemo === 'feishu' || initialDemo === 'single')) toggleDemo(true,initialDemo === 'feishu' ? 'list' : 'single');
}
