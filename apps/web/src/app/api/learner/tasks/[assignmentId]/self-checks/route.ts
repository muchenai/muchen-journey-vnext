import { cookies } from "next/headers";
import { apiRequest, ApiRequestError, SESSION_COOKIE } from "@/lib/server/api";
import type { AISelfCheckRecord } from "@/app/actions";

export const dynamic = "force-dynamic";

// A read-only route stays independent of Next's serialized server-action queue.
export async function GET(_request: Request, context: { params: Promise<{ assignmentId: string }> }) {
  if (!(await cookies()).get(SESSION_COOKIE)?.value) {
    return Response.json({ error: "登录已失效，请重新登录。" }, { status: 401 });
  }
  const { assignmentId } = await context.params;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(assignmentId)) {
    return Response.json({ error: "任务标识无效。" }, { status: 400 });
  }
  try {
    const records = await apiRequest<AISelfCheckRecord[]>(`/api/v1/me/assignments/${assignmentId}/ai-self-checks`, "LEARNER");
    return Response.json({ records }, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof ApiRequestError ? error.message : "暂时无法查询自查状态，请稍候。" },
      { status: error instanceof ApiRequestError ? error.status : 502 });
  }
}
