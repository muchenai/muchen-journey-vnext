import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

const source = readFileSync(new URL("../public/vendor/feishu/h5-js-sdk-1.5.26.js", import.meta.url));
const digest = createHash("sha256").update(source).digest("hex");
if (digest !== "1080a3f2492ba78e7a86fb3d4f460921f68a20b44d01c80a04f0b32340859ce3") throw new Error("Unexpected Feishu SDK source");
const code = source.toString("utf8");
const getter = 'new Function("return this;")()';
if (code.split(getter).length !== 3) throw new Error("Expected exactly two global object getters");
// Both expressions only return the global object. Use the standard reference
// instead so CSP can keep string-based code execution disabled.
writeFileSync(new URL("../public/vendor/feishu/h5-js-sdk-1.5.26.csp.js", import.meta.url), code.replaceAll(getter, "globalThis"));
