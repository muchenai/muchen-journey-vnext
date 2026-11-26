export async function experienceRequest(body, url="/api/review-native/experience") {
  const response = await fetch(url, { cache: 'no-store', credentials: 'same-origin',
    ...(body && { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw Object.assign(new Error(result.error || '读取失败，请重试。'), {status:response.status});
  return result.data;
}
