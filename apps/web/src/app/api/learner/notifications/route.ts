import { cookies } from "next/headers";
import { apiRequest, ApiRequestError, SESSION_COOKIE } from "@/lib/server/api";
import type { LearnerNotificationPage } from "@/lib/learner-notifications";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = { "Cache-Control": "private, no-store" };
  if (!(await cookies()).get(SESSION_COOKIE)?.value) {
    return Response.json({ error: "登录已失效，请重新登录。" }, { status: 401, headers });
  }
  const cursor = new URL(request.url).searchParams.get("cursor");
  if (cursor && !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(cursor)) {
    return Response.json({ error: "通知分页标识无效。" }, { status: 400, headers });
  }
  try {
    const data = await apiRequest<LearnerNotificationPage>(
      `/api/v1/me/notifications${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`, "LEARNER");
    return Response.json(data, { headers });
  } catch (error) {
    return Response.json({ error: error instanceof ApiRequestError ? error.message : "通知读取失败，请稍后重试。" },
      { status: error instanceof ApiRequestError ? error.status : 502, headers });
  }
}
