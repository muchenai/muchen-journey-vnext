import type { NextRequest } from "next/server";
import { forwardReviewManagement } from "@/lib/server/review-management-json";

export const dynamic = "force-dynamic";
export function GET(request: NextRequest) {
  const query = new URLSearchParams({ q: request.nextUrl.searchParams.get("q") ?? "" });
  return forwardReviewManagement(request, "/api/v1/ops/experience/permissions/search?" + query);
}
