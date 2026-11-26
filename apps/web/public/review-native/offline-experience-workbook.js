// SheetJS CE 0.20.3 from https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz
import { read, set_cptable, utils } from '../vendor/sheetjs-0.20.3/xlsx.mjs';

const badWorkbook = '无法读取工作簿，请使用 Excel 另存为未加密的 .xlsx 或 .xls 文件。';
const maxExpandedBytes = 64 * 1024 * 1024;

// A small .xlsx may expand substantially. Check the ZIP directory before inflating worksheet XML.
function checkArchive(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const uint = offset => view.getUint32(offset, true);
  const ushort = offset => view.getUint16(offset, true);
  let end = bytes.length - 22;
  const start = Math.max(0, end - 65535);
  for (; end >= start; end--) {
    if (uint(end) === 0x06054b50 && end + 22 + ushort(end + 20) === bytes.length) break;
  }
  if (end < start || ushort(end + 4) || ushort(end + 6)) throw new Error(badWorkbook);
  let pos = uint(end + 16);
  if (pos + uint(end + 12) !== end) throw new Error(badWorkbook);
  let total = 0;
  let hasWorkbook = false;
  const decoder = new TextDecoder();
  for (let i = 0; i < ushort(end + 10); i++) {
    if (pos + 46 > end || uint(pos) !== 0x02014b50) throw new Error(badWorkbook);
    const nameLength = ushort(pos + 28);
    const next = pos + 46 + nameLength + ushort(pos + 30) + ushort(pos + 32);
    if (next > end) throw new Error(badWorkbook);
    total += uint(pos + 24);
    if (total > maxExpandedBytes) throw new Error('工作簿展开后过大，请将名单单独另存为工作簿后导入。');
    if (decoder.decode(bytes.subarray(pos + 46, pos + 46 + nameLength)) === 'xl/workbook.xml') hasWorkbook = true;
    pos = next;
  }
  if (pos !== end || !hasWorkbook) throw new Error(badWorkbook);
}

function cellText(cell) {
  if (!cell || cell.v == null || cell.t === 'z') return '';
  if (cell.t === 'd') return cell.v.toISOString().slice(0,10);
  if (cell.t === 'e') return '#ERROR';
  return String(cell.v).trim();
}

function tableRows(sheet) {
  // Use actual cells. Excel sometimes saves a full-page used range just because a column has formatting.
  const positions = new Map();
  for (const [address,cell] of Object.entries(sheet)) {
    if (!/^[A-Z]+[1-9]\d*$/.test(address)) continue;
    const value = cellText(cell);
    if (!value) continue;
    const {r,c} = utils.decode_cell(address);
    if (!positions.has(r)) positions.set(r, new Map());
    if (positions.size > 1001) throw new Error('每批最多导入 1000 人，请拆分名单。');
    positions.get(r).set(c, value);
  }
  const sorted = [...positions.keys()].sort((a,b)=>a-b);
  if (!sorted.length) return [];
  const columns = [...positions.get(sorted[0]).keys()].sort((a,b)=>a-b);
  return sorted.map(index=>columns.map(c=>positions.get(index).get(c) ?? ''));
}

export async function readWorkbook(buffer, legacy) {
  const bytes = new Uint8Array(buffer);
  if (legacy) {
    const cfb = [0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1].every((byte,i)=>bytes[i] === byte);
    const biff = bytes.length >= 4 && bytes[0] === 0x09 && [0x00,0x02,0x04,0x08].includes(bytes[1]);
    if (!cfb && !biff) throw new Error(badWorkbook);
    set_cptable(await import('../vendor/sheetjs-0.20.3/cpexcel.full.mjs'));
  } else {
    if (bytes.length < 22 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) throw new Error(badWorkbook);
    checkArchive(bytes);
  }
  let workbook;
  try {
    workbook = read(bytes,{ type:'array', cellDates:true, cellStyles:false, cellText:false, cellHTML:false, cellFormula:false });
  } catch { throw new Error(badWorkbook); }
  for (const [index,name] of workbook.SheetNames.entries()) {
    if (workbook.Workbook?.Sheets?.[index]?.Hidden || !workbook.Sheets[name]) continue;
    const rows = tableRows(workbook.Sheets[name]);
    if (rows.length) return rows;
  }
  throw new Error('工作簿中没有可读取的名单，请在可见工作表填写姓名和线下积分。');
}

if (typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope) {
  self.onmessage = async ({data}) => {
    try { self.postMessage({rows:await readWorkbook(data.buffer, data.legacy)}); }
    catch (error) { self.postMessage({error:error.message}); }
  };
}
