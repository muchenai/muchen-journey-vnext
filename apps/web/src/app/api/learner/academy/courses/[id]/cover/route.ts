import { NextRequest } from "next/server";
import { proxyAcademyCover } from "@/lib/server/academy-cover";

export const dynamic = "force-dynamic";
export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  return proxyAcademyCover(request, (await context.params).id, "LEARNER");
}
export const HEAD = GET;
