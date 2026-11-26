import { NextRequest } from "next/server";
import { courseProxy } from "@/lib/server/course-workspace";

export const dynamic="force-dynamic";
export async function GET(request: NextRequest) {
  const camp = request.nextUrl.searchParams.get("camp")==="village" ? "village" : "academy";
  return courseProxy(request,"REVIEWER","/api/v1/ops/course-workspace?camp="+camp,true);
}
export const POST=GET;
