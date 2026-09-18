const PRODUCT_TIME_ZONE = "Asia/Shanghai";

export function formatProductDateTime(
  value: string | Date,
  timeStyle: "short" | "medium" = "short",
): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle,
    timeZone: PRODUCT_TIME_ZONE,
  }).format(typeof value === "string" ? new Date(value) : value);
}
