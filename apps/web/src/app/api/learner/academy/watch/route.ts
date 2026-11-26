import { NextRequest,NextResponse } from "next/server";
import { courseProxy } from "@/lib/server/course-workspace";

export const dynamic="force-dynamic";
export async function GET(request:NextRequest) {
  const query=request.nextUrl.searchParams;
  const id=query.get("courseId") || "", material=query.get("materialId") || "", revision=query.get("revision") || "";
  if (!/^[0-9a-f-]{36}$/i.test(id) || !/^[a-zA-Z0-9_-]{1,100}$/.test(material) || !/^[1-9]\d{0,8}$/.test(revision))
    return NextResponse.json({error:"视频参数无效。"},{status:400});
  const camp=query.get("camp")==="village" ? "village" : "academy";
  return courseProxy(request,"LEARNER",`/api/v1/me/course-workspace/${id}/watch/${material}?revision=${revision}&camp=${camp}`);
}
export const POST=GET;
