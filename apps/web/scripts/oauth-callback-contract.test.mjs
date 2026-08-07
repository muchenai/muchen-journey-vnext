import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const callbackSource = readFileSync(
  new URL("../src/app/auth/feishu/callback/route.ts", import.meta.url),
  "utf8",
);

test("all staff OAuth callbacks allow only the three role entry points", () => {
  assert.match(
    callbackSource,
    /const SAFE_ENTRIES = new Set\(\["\/review", "\/ops", "\/content"\]\);/,
  );
  assert.match(
    callbackSource,
    /if \(!SAFE_ENTRIES\.has\(result\.data\.safe_entry\)\) \{\s*return sameOriginIdentityRedirect\("\/\?auth_error=IDENTITY_PROVIDER_INVALID"\);\s*\}/,
  );
});

test("successful staff OAuth callbacks forward upstream session cookies", () => {
  assert.match(
    callbackSource,
    /return sameOriginIdentityRedirect\(result\.data\.safe_entry, result\.response\);/,
  );
});
