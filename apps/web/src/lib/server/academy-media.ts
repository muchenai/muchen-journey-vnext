import "server-only";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, STAFF_SESSION_COOKIE } from "@/lib/auth/cookies";

/** Streams private course media without buffering the video or exposing session credentials. */
export async function proxyAcademyVideo(request: NextRequest, courseId: string, role: "LEARNER" | "REVIEWER" | "OPERATOR"): Promise<Response> {
  const responseHeaders = new Headers({ "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" });
  const fail = (message: string, status: number) => NextResponse.json({ error: message }, { status, headers: responseHeaders });
  if (!/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(courseId)) return fail("课程参数无效。", 400);
  const range = request.headers.get("range");
  if (range && !/^bytes=(?:\d+-\d*|-\d+)$/.test(range)) return fail("视频分段参数无效。", 416);
  const ifRange = request.headers.get("if-range");
  const validValidator = !ifRange || (ifRange.length <= 256 && (/^(?:W\/)?"[\x21\x23-\x7e]*"$/.test(ifRange)
    || (/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(ifRange) && Number.isFinite(Date.parse(ifRange)))));
  if (!validValidator) return fail("视频版本参数无效。", 400);
  const learner = role === "LEARNER";
  const cookieName = learner ? SESSION_COOKIE : STAFF_SESSION_COOKIE;
  const token = (await cookies()).get(cookieName)?.value;
  const localFixture = process.env.ALLOW_FIXTURE_IDENTITY === "true" && ["local", "test"].includes(process.env.APP_ENV ?? "local");
  const headers = new Headers({ "X-Journey-Session-Scope": learner ? "learner" : "staff" });
  if (localFixture && role === "REVIEWER") headers.set("X-Fixture-Role", role);
  else if (token) headers.set("Cookie", `${cookieName}=${token}`);
  else if (localFixture) headers.set("X-Fixture-Role", role);
  else return fail("登录已失效，请重新登录。", 401);
  if (range) headers.set("Range", range);
  if (ifRange) headers.set("If-Range", ifRange);
  try {
    const response = await fetch(new URL(`/api/v1/${learner ? "me" : "ops"}/academy/courses/${courseId}/video`, process.env.API_INTERNAL_URL ?? "http://localhost:8000"), {
      method: request.method === "HEAD" ? "HEAD" : "GET", headers, cache: "no-store", redirect: "error", signal: request.signal,
    });
    for (const name of ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Content-Disposition", "ETag", "Last-Modified"]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(request.method === "HEAD" ? null : response.body, { status: response.status, headers: responseHeaders });
  } catch { return fail("视频读取失败，请稍后重试。", 502); }
}
