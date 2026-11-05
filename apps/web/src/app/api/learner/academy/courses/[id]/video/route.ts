import { NextRequest } from "next/server";
import { proxyAcademyVideo } from "@/lib/server/academy-media";

export const dynamic = "force-dynamic";
export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  return proxyAcademyVideo(request, (await context.params).id, "LEARNER");
}
export const HEAD = GET;
