import type { NextRequest } from "next/server";
import { forwardReviewManagement } from "@/lib/server/review-management-json";

export const dynamic = "force-dynamic";
const handle = (request: NextRequest) => forwardReviewManagement(request, "/api/v1/ops/experience");
export const GET = handle;
export const POST = handle;
