import { NextRequest } from "next/server";
import { courseProxy } from "@/lib/server/course-workspace";

export const dynamic="force-dynamic";
export async function GET(request:NextRequest) {
  return courseProxy(request,"LEARNER","/api/v1/me/course-workspace?camp=village");
}
export const POST=GET;
