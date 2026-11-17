import { explorationMaterialResponse } from "@/lib/server/exploration-material-proxy";

export const dynamic = "force-dynamic";
export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  return explorationMaterialResponse(request, (await context.params).id, "REVIEWER");
}
export async function HEAD(request: Request, context: { params: Promise<{ id: string }> }) {
  return explorationMaterialResponse(request, (await context.params).id, "REVIEWER");
}
