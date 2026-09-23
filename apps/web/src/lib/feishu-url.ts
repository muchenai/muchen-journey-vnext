const ALLOWED_FEISHU_HOSTS = ["feishu.cn", "larksuite.com"] as const;

export function validateFeishuDocumentUrl(value: string): string | null {
  const candidate = value.trim();
  if (!candidate) return "请先粘贴飞书文档链接，再提交给 Reviewer。";
  try {
    const parsed = new URL(candidate);
    const hostname = parsed.hostname.toLowerCase();
    const acceptedHost = ALLOWED_FEISHU_HOSTS.some(
      (root) => hostname === root || hostname.endsWith(`.${root}`),
    );
    if (
      parsed.protocol !== "https:"
      || !acceptedHost
      || Boolean(parsed.username)
      || Boolean(parsed.password)
    ) {
      return "请粘贴 HTTPS 飞书文档链接；不接受其他网站、相似域名或包含账号凭据的链接。";
    }
    return null;
  } catch {
    return "飞书文档链接无效；请从浏览器地址栏复制完整链接。";
  }
}
