export function isMaterialLink(value) {
  const text = String(value ?? '').trim();
  if (text.length > 2000 || !/^https:\/\//i.test(text)) return false;
  try {
    const url = new URL(text);
    return url.protocol === 'https:' && !!url.hostname && !url.username && !url.password;
  } catch { return false; }
}

export function validateMaterialFields({name, url, type = 'link', nameLimit = 160}) {
  const rawName = String(name ?? '');
  const values = {name: rawName.trim(), url: String(url ?? '').trim()};
  const errors = {};
  if (!rawName) errors.name = '请填写材料名称';
  else if (!values.name) errors.name = '材料名称不能只包含空格';
  else if (values.name.length > nameLimit) errors.name = `材料名称不能超过 ${nameLimit} 字`;
  if (type === 'link' && !isMaterialLink(values.url)) errors.url = '请输入有效的 HTTPS 链接（不能包含账号或密码）';
  return {values, errors};
}
