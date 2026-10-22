import "server-only";

import { unstable_rethrow } from "next/navigation";

import { ApiRequestError, identityPageRequest } from "@/lib/server/api";

export async function opsModuleRequest<T>(path: string, role: "OPERATOR"): Promise<T | null> {
  try {
    return await identityPageRequest<T>(path, role);
  } catch (error) {
    // Authentication redirects and framework control flow must still propagate.
    unstable_rethrow(error);
    console.error(JSON.stringify({
      event: "ops.module_unavailable",
      path,
      ...(error instanceof ApiRequestError
        ? { status: error.status, code: error.code, request_id: error.requestId }
        : { code: "READ_FAILED" }),
    }));
    return null;
  }
}
