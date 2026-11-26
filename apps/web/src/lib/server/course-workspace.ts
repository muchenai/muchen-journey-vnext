import "server-only";
import { NextRequest, NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

const headers = {"Cache-Control":"private, no-store"};

export async function courseProxy(request: NextRequest, role: "LEARNER" | "REVIEWER", path: string, staff = false) {
  const fail = (message: string, status: number) => NextResponse.json(staff ? {ok:false,error:message} : {error:message}, {status,headers});
  try {
    let init: RequestInit = {};
    if (request.method === "POST") {
      const originText = request.headers.get("origin");
      let trusted = false;
      try {
        const origin = new URL(originText || "");
        trusted = ["https:", "http:"].includes(origin.protocol) && origin.host === request.headers.get("host");
      } catch { /* Reject malformed origins. */ }
      if (!trusted || request.headers.get("sec-fetch-site") === "cross-site") return fail("请求来源不匹配。",403);
      if (!request.headers.get("content-type")?.startsWith("application/json")) return fail("请求格式无效。",415);
      const maxBytes = staff ? 1_000_000 : 40_000;
      if (Number(request.headers.get("content-length")) > maxBytes) return fail("课程请求过长。",413);
      const raw = await request.text();
      if (Buffer.byteLength(raw)>maxBytes) return fail("课程请求过长。",413);
      let body;
      try { body=JSON.parse(raw); } catch { return fail("课程请求格式无效。",400); }
      if (!body || Array.isArray(body) || typeof body!=="object") return fail("课程请求格式无效。",400);
      init={method:"POST",body:raw};
    }
    const data=await apiRequest(path,role,init);
    return NextResponse.json(staff ? {ok:true,data} : data,{headers});
  } catch (error) {
    return fail(error instanceof ApiRequestError ? error.message : "课程服务暂不可用，请重试。",error instanceof ApiRequestError ? error.status : 502);
  }
}
