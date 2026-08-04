import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const proxySource = readFileSync(new URL("../src/proxy.ts", import.meta.url), "utf8");

test("all staff identity surfaces reject anonymous requests before rendering", () => {
  assert.match(
    proxySource,
    /\["\/ops", "\/review", "\/content"\]\.some\(/,
  );
  assert.match(proxySource, /code: "AUTH_REQUIRED"/);
  assert.match(proxySource, /\{ status: 401 \}/);
});
