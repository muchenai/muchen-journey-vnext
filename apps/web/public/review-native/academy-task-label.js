export const taskAction = kind => ({document:'阅读文档', image:'查看图片', video:'观看视频', link:'学习链接'}[kind] || '学习材料');

export function taskNumber(position) {
  const digits = '零一二三四五六七八九';
  const units = ['', '十', '百', '千'];
  if (position < 1 || position > 9999) return '任务' + position;
  const parts = String(position).split('');
  let label = '', pendingZero = false;
  parts.forEach((digit, index) => {
    const power = parts.length - index - 1;
    if (digit === '0') { pendingZero = true; return; }
    if (pendingZero) label += '零';
    pendingZero = false;
    if (!(index === 0 && power === 1 && digit === '1')) label += digits[Number(digit)];
    label += units[power];
  });
  return '任务' + label;
}

export function taskMaterialType(item) {
  if (item.kind === 'document' && !item.assetId && /^https?:\/\//i.test(item.url || '')) return '文档链接';
  return ({document:'文档', image:'图片', video:'视频', link:'学习链接'})[item.kind] || '材料';
}
