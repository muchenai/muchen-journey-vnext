import { NextRequest } from "next/server";
import { courseProxy } from "@/lib/server/course-workspace";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const query = new URLSearchParams();
  for (const key of ["courseId", "learnerId", "courseRevision"]) {
    const value = request.nextUrl.searchParams.get(key);
    if (value !== null) query.set(key, value);
  }
  return courseProxy(request, "REVIEWER", `/api/v1/ops/course-workspace/village-reflections?${query}`, true);
}
