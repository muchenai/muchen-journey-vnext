import { escapeHtml as esc } from './core.js?v=20261030-member-action-spacing';

const maxRows = 1000;
const xpPerPoint = 10;
const nameHeaders = ['姓名', '学员姓名', '员工姓名', '飞书姓名'];
const pointHeaders = ['线下积分', '积分', '培训积分', '线下培训积分', '发放积分'];
const fmt = value => value.toLocaleString('zh-CN');

function cells(text, separator) {
  const rows = [];
  let record = [], value = '', quoted = false;
  function endRecord() {
    record.push(value.trim());
    if (record.some(Boolean)) rows.push(record);
    record = [];
    value = '';
  }
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { value += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && char === separator) {
      record.push(value.trim());
      value = '';
    } else if (!quoted && (char === '\r' || char === '\n')) {
      if (char === '\r' && text[i + 1] === '\n') i++;
      endRecord();
    } else value += char;
  }
  if (quoted) throw new Error('名单中的引号不完整，请检查后重新导入。');
  endRecord();
  return rows;
}

export function parseRoster(text) {
  const clean = text.replace(/^\uFEFF/, '').trim();
  const firstLine = clean.split(/[\r\n]/, 1)[0];
  return parseRosterTable(cells(clean, firstLine.includes('\t') ? '\t' : ','));
}

function grantRow(name, points) {
  return {name,points,candidates:[],selectedId:'',manual:false,needsMatch:true};
}

export function parseRosterTable(table) {
  const [header = [], ...records] = table
    .map(row => row.map(cell => String(cell ?? '').trim()))
    .filter(row => row.some(Boolean));
  const nameCols = header.flatMap((label, i) => nameHeaders.includes(label) ? [i] : []);
  const pointCols = header.flatMap((label, i) => pointHeaders.includes(label) ? [i] : []);
  if (nameCols.length !== 1 || pointCols.length !== 1)
    throw new Error('名单需要一列「姓名」和一列「线下积分」。可下载模板后填写。');
  // Previous templates prefilled all learners and left the amount blank for non-recipients.
  const selected = header.includes('学员ID') ? records.filter(row => row[pointCols[0]]) : records;
  if (!selected.length) throw new Error('没有可导入的名单，请填写姓名和线下积分后重新导入。');
  if (selected.length > maxRows) throw new Error('每批最多导入 1000 人，请拆分名单。');
  return selected.map(row => grantRow(row[nameCols[0]] || '',row[pointCols[0]] || ''));
}

async function readRosterFile(file) {
  if (!/\.(xlsx|xls|csv|tsv|txt)$/i.test(file.name)) throw new Error('请选择 Excel 工作簿（.xlsx、.xls）、CSV 或制表符分隔的文本名单。');
  if (file.size > 2 * 1024 * 1024) throw new Error('名单文件超过 2 MB，请拆分后导入。');
  if (/\.xlsx?$/i.test(file.name)) {
    const {readExcelTable} = await import('./offline-experience-excel.js');
    return parseRosterTable(await readExcelTable(file));
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text;
  if (bytes[0] === 0xff && bytes[1] === 0xfe) text = new TextDecoder('utf-16le').decode(bytes);
  else if (bytes[0] === 0xfe && bytes[1] === 0xff) text = new TextDecoder('utf-16be').decode(bytes);
  else {
    try { text = new TextDecoder('utf-8', { fatal:true }).decode(bytes); }
    catch { text = new TextDecoder('gb18030').decode(bytes); }
  }
  return parseRoster(text);
}

function pointsValue(raw) {
  if (!/^\d+$/.test(raw)) return null;
  const points = Number(raw);
  return points > 0 && Number.isSafeInteger(points * xpPerPoint) ? points : null;
}

export function applyRosterMatches(rows, matches) {
  const byName = new Map(matches.map(group => [group.name, group.candidates]));
  for (const row of rows) {
    const candidates = byName.get(row.name.trim()) || [];
    const retained = row.manual && candidates.some(person => person.id === row.selectedId && !person.indistinguishable);
    const automatic = candidates.length === 1 && !candidates[0].indistinguishable;
    row.selectedId = retained ? row.selectedId : automatic ? candidates[0].id : '';
    row.manual = Boolean(retained);
    row.candidates = candidates;
    row.needsMatch = false;
  }
}

export function reviewRoster(rows) {
  const times = new Map();
  for (const row of rows) if (row.selectedId) times.set(row.selectedId, (times.get(row.selectedId) || 0) + 1);
  let unresolved = 0, totalPoints = 0;
  const reviewed = rows.map(row => {
    const points = pointsValue(row.points);
    const person = row.candidates.find(person => person.id === row.selectedId && !person.indistinguishable);
    let issue = '';
    if (!row.name.trim()) issue = '请填写姓名';
    else if (row.needsMatch) issue = '等待匹配';
    else if (!row.candidates.length) issue = '未找到此人，请核对姓名';
    else if (!person && row.candidates.every(item => item.indistinguishable)) issue = '同名人员资料相同，请完善通讯录后重新匹配';
    else if (!person) issue = '同名待核对';
    else if (times.get(person.id) > 1) issue = '名单中重复选择了此人';
    else if (points === null) issue = '请填写正整数积分';
    if (issue) unresolved++;
    if (points !== null) totalPoints += points;
    return {person, points, issue};
  });
  const totalXp = totalPoints * xpPerPoint;
  const overflow = !Number.isSafeInteger(totalXp);
  return { reviewed, totalPoints, totalXp, unresolved, overflow, ready:rows.length > 0 && !unresolved && !overflow };
}

function personCell(row, i) {
  const name = esc(row.name);
  if (!row.candidates.length || row.needsMatch) {
    return `<input class="xp-roster-name" data-xp-name="${i}" aria-label="第 ${i + 1} 行姓名" value="${name}" placeholder="填写姓名" maxlength="100">`;
  }
  const label = person => [person.name, person.department, person.detail].filter(Boolean).join(' · ');
  if (row.candidates.length === 1 && !row.candidates[0].indistinguishable) {
    const person = row.candidates[0];
    return `<strong>${esc(person.name)}</strong><small>${esc([person.department,person.detail].filter(Boolean).join(' · '))}</small>`;
  }
  return `<strong>${name}</strong><select data-xp-person="${i}" aria-label="第 ${i + 1} 行，核对${name}的身份">
    <option value="">选择同名人员（${row.candidates.length} 人）</option>
    ${row.candidates.map(person => `<option value="${esc(person.id)}" ${row.selectedId === person.id ? 'selected' : ''} ${person.indistinguishable ? 'disabled' : ''}>${esc(label(person))}${person.indistinguishable ? '（资料不足）' : ''}</option>`).join('')}</select>`;
}

export function bindGrantRoster(container, {matchNames, onChange = () => {}, isSimulation = () => false}) {
  container.innerHTML = `<div class="xp-roster">
    <div class="xp-roster-upload"><div class="xp-roster-actions">
      <label class="btn btn-secondary xp-roster-picker">选择名单文件<input type="file" data-xp-file accept=".xlsx,.xls,.csv,.tsv,.txt" aria-label="选择名单文件"></label>
      <button type="button" class="btn btn-ghost" data-xp-template>下载 Excel 模板</button></div>
      <small class="field-hint">支持 Excel（.xlsx、.xls）、CSV 和制表符文本。Excel 读取第一个有内容的可见工作表，表头填写「姓名」和「线下积分」。</small></div>
    <p class="xp-roster-notice" data-xp-notice role="status" hidden></p>
    <section class="xp-roster-review" data-xp-review hidden>
      <div class="xp-roster-heading"><div><h3>核对发放名单</h3><small data-xp-source></small></div>
        <button type="button" class="btn btn-secondary" data-xp-rematch>重新匹配</button></div>
      <div class="xp-roster-table-wrap"><table class="xp-roster-table">
        <thead><tr><th scope="col">学员</th><th scope="col">线下积分</th><th scope="col">发放经验</th><th scope="col">核对状态</th><th scope="col">操作</th></tr></thead>
        <tbody></tbody></table></div>
      <p class="xp-roster-summary" data-xp-summary aria-live="polite"></p></section></div>`;
  const find = selector => container.querySelector(selector);
  const input = find('[data-xp-file]'), notice = find('[data-xp-notice]'), review = find('[data-xp-review]');
  const body = find('tbody'), retry = find('[data-xp-rematch]'), template = find('[data-xp-template]');
  let rows = [], snapshotId = '', sourceLabel = '', filename = '', busy = false, loading = false, version = 0;
  let verdict = reviewRoster(rows);
  const isReady = () => !loading && Boolean(snapshotId) && verdict.ready;
  function announce(message, tone = '') {
    notice.textContent = message;
    notice.hidden = !message;
    notice.dataset.tone = tone;
  }
  function showMatchingWarning() {
    const unresolved = rows.filter(row => row.candidates.length > 1 && !row.manual).length;
    announce(unresolved ? `有 ${unresolved} 行姓名对应多人，请按部门或人员信息逐行核对。` : '', unresolved ? 'warning' : '');
  }
  function toggleControls() {
    input.disabled = busy;
    retry.disabled = loading || busy;
    for (const el of body.querySelectorAll('input, select, button')) el.disabled = loading || busy;
  }
  function summarize() {
    verdict = reviewRoster(rows);
    for (let i = 0; i < rows.length; i++) {
      const line = body.rows[i];
      if (!line) continue;
      const check = verdict.reviewed[i];
      line.dataset.tone = check.issue ? 'warning' : '';
      line.querySelector('[data-xp-converted]').textContent = check.points === null ? '—' : fmt(check.points * xpPerPoint);
      const status = line.querySelector('[data-xp-status]');
      status.textContent = check.issue || (rows[i].manual ? '已人工核对' : '已匹配');
      status.dataset.tone = check.issue ? 'warning' : 'success';
      line.querySelector('[data-xp-points]').setAttribute('aria-invalid', String(check.points === null));
    }
    const count = verdict.unresolved ? ` · ${verdict.unresolved} 行待核对` : '';
    find('[data-xp-summary]').textContent = verdict.overflow ? '总经验超出有效范围，请检查积分。' :
      `名单 ${rows.length} 人${count} · 合计 ${fmt(verdict.totalPoints)} 积分，折合 ${fmt(verdict.totalXp)} 经验`;
    onChange();
  }
  function render() {
    review.hidden = !rows.length;
    find('[data-xp-source]').textContent = [filename,sourceLabel].filter(Boolean).join(' · ');
    body.innerHTML = rows.map((row, i) => `<tr><td class="xp-roster-person">${personCell(row, i)}</td>
      <td><input class="xp-roster-points" type="text" inputmode="numeric" aria-label="第 ${i + 1} 行线下积分" value="${esc(row.points)}" data-xp-points="${i}" autocomplete="off"></td>
      <td data-xp-converted></td><td><span class="xp-roster-status" data-xp-status></span></td>
      <td><button type="button" class="btn btn-ghost xp-roster-remove" data-xp-remove-row="${i}" aria-label="从待发名单移除第 ${i + 1} 行${esc(row.name)}">移除</button></td></tr>`).join('');
    toggleControls();
    summarize();
  }
  async function match(versionAtStart) {
    const names = [...new Set(rows.map(row => row.name.trim()).filter(Boolean))];
    if (!names.length) {
      loading = false;
      announce('请填写名单中的姓名，再点「重新匹配」。','warning');
      render();
      return;
    }
    announce(isSimulation() ? '正在模拟从飞书通讯录匹配人员…' : '正在匹配通讯录人员…');
    render();
    const result = await matchNames(names);
    if (version !== versionAtStart) return;
    if (!result?.snapshotId || !Array.isArray(result.matches)) throw new Error('未能读取完整的人员名单，请重新匹配。');
    sourceLabel = result.sourceLabel;
    snapshotId = result.snapshotId;
    applyRosterMatches(rows, result.matches);
    showMatchingWarning();
    loading = false;
    render();
  }
  async function load(file, sample) {
    if (busy) return;
    const mine = ++version;
    if (file || sample) {
      rows = [];
      filename = file ? file.name : sample.label;
    }
    snapshotId = '';
    sourceLabel = '';
    loading = true;
    announce(file ? '正在读取名单…' : '正在重新匹配…');
    render();
    try {
      if (file || sample) {
        const imported = file ? await readRosterFile(file) :
          parseRosterTable([['姓名','线下积分'], ...sample.rows.map(row => [row.name,row.points])]);
        if (version !== mine) return;
        rows = imported;
      }
      await match(mine);
    } catch (error) {
      if (version !== mine) return;
      loading = false;
      for (const row of rows) row.needsMatch = true;
      announce(error.message || '名单匹配失败，请重新导入或重试。','error');
      render();
    }
  }
  input.onchange = () => {
    const file = input.files?.[0];
    input.value = '';
    if (file) return load(file);
  };
  retry.onclick = () => { if (!loading && !busy) return load(null); };
  template.onclick = async () => {
    if (template.disabled || busy) return;
    template.disabled = true;
    try {
      const {createExcelTemplate} = await import('./offline-experience-excel.js');
      const bytes = await createExcelTemplate();
      const url = URL.createObjectURL(new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = '培训积分名单模板.xlsx';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url),1000);
    } catch {
      announce('Excel 模板暂未生成，请重试下载。','error');
    } finally {
      template.disabled = false;
    }
  };
  body.addEventListener('input', event => {
    if (loading || busy) return;
    const el = event.target;
    if (el.hasAttribute('data-xp-points')) rows[Number(el.dataset.xpPoints)].points = el.value;
    else if (el.hasAttribute('data-xp-name')) {
      const row = rows[Number(el.dataset.xpName)];
      row.name = el.value;
      row.needsMatch = true; row.manual = false; row.selectedId = ''; row.candidates = [];
    } else return;
    summarize();
  });
  body.addEventListener('change', event => {
    const el = event.target;
    if (busy || loading || !el.hasAttribute('data-xp-person')) return;
    const row = rows[Number(el.dataset.xpPerson)];
    row.selectedId = el.value;
    row.manual = Boolean(el.value);
    showMatchingWarning();
    summarize();
  });
  body.addEventListener('click', event => {
    const button = event.target.closest('[data-xp-remove-row]');
    if (!button || loading || busy) return;
    rows.splice(Number(button.dataset.xpRemoveRow), 1);
    if (!rows.length) {
      snapshotId = '';
      announce('待发名单已清空，可以重新选择文件。');
    } else if (snapshotId) showMatchingWarning();
    render();
  });
  body.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.target.tagName !== 'INPUT') return;
    event.preventDefault();
    if (event.target.hasAttribute('data-xp-name') && !busy && !loading) void load(null);
  });
  return {
    isReady,
    getSnapshotId: () => snapshotId,
    getDraftRows: () => rows.map(({name,points}) => ({name,points})),
    loadSample(sampleRows, label='演示名单') {
      return load(null, {rows:sampleRows,label});
    },
    reset() {
      if (busy) return;
      version++;
      rows = [];
      snapshotId = sourceLabel = filename = '';
      loading = false;
      announce('');
      render();
    },
    getRows() {
      if (!isReady()) throw new Error('请先完成名单匹配并核对所有积分，再确认发放。');
      return verdict.reviewed.map(({person,points}) => ({learnerId:person.id, name:person.name, points}));
    },
    setBusy(value) { busy = Boolean(value); toggleControls(); },
  };
}
