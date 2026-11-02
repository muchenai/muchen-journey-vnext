import { NextResponse } from "next/server";
import { apiRequest, ApiRequestError } from "@/lib/server/api";

export const dynamic="force-dynamic";
export async function GET(){
  try{
    const wallet=await apiRequest("/api/v1/me/novice/wallet","LEARNER");
    return NextResponse.json(wallet,{headers:{"Cache-Control":"no-store"}});
  }catch(error){
    return NextResponse.json({error:error instanceof ApiRequestError?error.message:"成长数据读取失败，请重试。"},{status:error instanceof ApiRequestError?error.status:500,headers:{"Cache-Control":"no-store"}});
  }
}
