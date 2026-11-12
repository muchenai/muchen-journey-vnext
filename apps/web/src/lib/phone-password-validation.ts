export const PHONE_PASSWORD_MIN_LENGTH = 6;
export const PHONE_PASSWORD_MAX_LENGTH = 11;

export function phonePasswordError(value: string, label = "密码"): string {
  if (!value) return `请输入${label}`;
  if (/\s/.test(value)) return `${label}不能包含空格`;
  if (value.length < PHONE_PASSWORD_MIN_LENGTH) return `${label}至少需要 ${PHONE_PASSWORD_MIN_LENGTH} 个字符`;
  if (value.length > PHONE_PASSWORD_MAX_LENGTH) return `${label}最多支持 ${PHONE_PASSWORD_MAX_LENGTH} 个字符`;
  return "";
}

export function confirmPhonePasswordError(value: string, password: string, label = "密码"): string {
  if (!value) return `请再次输入${label}`;
  const error = phonePasswordError(value, `确认${label}`);
  if (error) return error;
  return value === password ? "" : "两次输入的密码不一致，请重新确认";
}
