import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { apiRequest, ApiRequestError, STAFF_CSRF_COOKIE, STAFF_SESSION_COOKIE, type ReviewDetail } from "@/lib/server/api";
export const dynamic = "force-dynamic";
export async function GET(_request:Request,{params}:{params:Promise<{reviewId:string;attachmentId:string}>}) {
 const {reviewId,attachmentId}=await params;
 if(!/^[0-9a-f-]{36}$/i.test(reviewId)||!/^[0-9a-f-]{36}$/i.test(attachmentId)) return new NextResponse("附件不存在",{status:404});
 try {
  const detail=await apiRequest<ReviewDetail>(`/api/v1/reviews/${reviewId}`,"REVIEWER");
  if(!detail.materials.attachments.some(a=>a.id===attachmentId&&a.status==='READY'&&a.scan_status==='CLEAN'))return new NextResponse("附件不可用",{status:404});
  const headers=new Headers();const store=await cookies();
  const local=process.env.ALLOW_FIXTURE_IDENTITY==='true'&&['local','test'].includes(process.env.APP_ENV??'local');
  if(local)headers.set('X-Fixture-Role','REVIEWER');
  else {const session=store.get(STAFF_SESSION_COOKIE)?.value;if(!session)return new NextResponse("请重新登录",{status:401});headers.set('Cookie',`${STAFF_SESSION_COOKIE}=${session}; ${STAFF_CSRF_COOKIE}=${store.get(STAFF_CSRF_COOKIE)?.value??''}`);}
  headers.set('X-Journey-Session-Scope','staff');
  const response=await fetch(new URL(`/api/v1/attachments/${attachmentId}/download`,process.env.API_INTERNAL_URL??'http://localhost:8000'),{headers,cache:'no-store',redirect:'manual'});
  if(response.status===303){const location=response.headers.get('Location');if(!location||!location.startsWith('https://'))return new NextResponse("附件下载暂不可用",{status:502});return NextResponse.redirect(location,303);}
  if(!response.ok)return new NextResponse("附件下载失败",{status:response.status});
  return new NextResponse(response.body,{headers:{'Content-Type':'application/octet-stream','Content-Disposition':response.headers.get('Content-Disposition')??'attachment','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
 } catch(e){return new NextResponse(e instanceof ApiRequestError?e.message:'附件下载暂不可用',{status:e instanceof ApiRequestError?e.status:503});}
}
