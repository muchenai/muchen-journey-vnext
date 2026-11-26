import "server-only";
import { apiResponse, ApiRequestError, type Role } from "./api";

const privateHeaders = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };

/** Streams authorized files, including byte-range video requests, through this origin. */
export async function explorationMaterialResponse(request: Request, id: string, role: Role): Promise<Response> {
  if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(id)) return Response.json({ error:"材料标识无效。" }, {status:400, headers:privateHeaders});
  const scope = role === "LEARNER" ? "me" : "review-admin";
  return proxyContentFile(request, `/api/v1/${scope}/exploration/materials/${id}`, role);
}

export async function proxyContentFile(request: Request, path: string, role: Role): Promise<Response> {
  const fail = (error: string, status: number) => Response.json({ error }, { status, headers: privateHeaders });
  const range = request.headers.get("range");
  if (range && !/^bytes=(?:\d+-\d*|-\d+)$/.test(range)) return fail("材料分段参数无效。", 416);
  const headers = new Headers();
  if (range) headers.set("Range", range);
  const query = new URLSearchParams();
  if (new URL(request.url).searchParams.get("inline") === "1") query.set("inline", "1");
  try {
    const response = await apiResponse(`${path}?${query}`, role, {
      method: request.method === "HEAD" ? "HEAD" : "GET", headers, redirect: "error", signal: request.signal,
    });
    const outgoing = new Headers(privateHeaders);
    for (const name of ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Content-Disposition", "ETag", "Last-Modified"]) {
      const value = response.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    return new Response(request.method === "HEAD" ? null : response.body, { status: response.status, headers: outgoing });
  } catch (error) {
    return fail(error instanceof ApiRequestError ? error.message : "材料读取失败，请重试。", error instanceof ApiRequestError ? error.status : 502);
  }
}
