export async function createExcelTemplate() {
  const { utils, write } = await import('../vendor/sheetjs-0.20.3/xlsx.mjs');
  const workbook = utils.book_new();
  const sheet = utils.aoa_to_sheet([['姓名','线下积分']]);
  sheet['!cols'] = [{wch:18},{wch:14}];
  utils.book_append_sheet(workbook, sheet, '培训积分名单');
  return new Uint8Array(write(workbook, {type:'array',bookType:'xlsx',compression:true}));
}

export async function readExcelTable(file) {
  if (!/\.xlsx?$/i.test(file.name)) throw new Error('请选择 .xlsx 或 .xls 工作簿。');
  if (file.size > 2 * 1024 * 1024) throw new Error('名单文件超过 2 MB，请拆分后导入。');
  const buffer = await file.arrayBuffer();
  const legacy = /\.xls$/i.test(file.name);
  if (typeof Worker === 'undefined') {
    const { readWorkbook } = await import('./offline-experience-workbook.js');
    return readWorkbook(buffer, legacy);
  }

  // Decoding the workbook in a short-lived worker keeps the review form responsive.
  const worker = new Worker(new URL('./offline-experience-workbook.js', import.meta.url), { type:'module' });
  try {
    return await new Promise((resolve,reject) => {
      const timeout = setTimeout(() => reject(new Error('Excel 读取超时，请将名单单独另存为工作簿后重试。')), 30000);
      worker.onmessage = ({data}) => {
        clearTimeout(timeout);
        if (data.error) reject(new Error(data.error));
        else resolve(data.rows);
      };
      worker.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('无法加载本地 Excel 读取组件，请刷新页面后重试。'));
      };
      worker.postMessage({buffer,legacy},[buffer]);
    });
  } finally {
    worker.terminate();
  }
}
