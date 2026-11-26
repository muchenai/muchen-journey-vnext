export const explorationOnlyMessage = "请用公司认证的飞书账号进行登录和使用";

export function isCompanyModule(view: unknown): view is "village" | "academy" | "guild" {
  return view === "village" || view === "academy" || view === "guild";
}
