import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const composer = await readFile(new URL("../src/app/app/tasks/[assignmentId]/submission-composer.tsx", import.meta.url), "utf8");
const uploader = await readFile(new URL("../src/app/app/tasks/[assignmentId]/attachment-uploader.tsx", import.meta.url), "utf8");
const globalError = await readFile(new URL("../src/app/error.tsx", import.meta.url), "utf8");
const workbench = await readFile(new URL("../src/app/review/[reviewId]/review-workbench.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../src/app/globals.css", import.meta.url), "utf8");

test("weak-network draft flow retains a local copy and blocks duplicate-risk mutation", () => {
  assert.match(composer, /window\.addEventListener\("offline"/);
  assert.match(composer, /window\.addEventListener\("online"/);
  assert.match(composer, /当前离线/);
  assert.match(composer, /未同步/);
  assert.match(composer, /!isOnline/);
  assert.match(composer, /submissionIdempotencyKey/);
});

test("formal confirmation and errors receive programmatic focus with described fields", () => {
  assert.match(composer, /confirmationHeadingRef/);
  assert.match(composer, /errorRef/);
  assert.match(composer, /aria-describedby="submission-body-help submission-save-status"/);
  assert.match(composer, /tabIndex=\{-1\}/);
  assert.match(globalError, /errorHeadingRef/);
  assert.match(workbench, /errorRef/);
});

test("attachment upload exposes status progress and recoverable error focus", () => {
  assert.match(uploader, /aria-live="polite"/);
  assert.match(uploader, /正在计算文件指纹/);
  assert.match(uploader, /正在上传文件/);
  assert.match(uploader, /正文与服务端草稿不受影响/);
  assert.match(uploader, /errorRef/);
});

test("mobile primary action persists without motion-only or color-only meaning", () => {
  assert.match(styles, /\.submission-composer > \.action-row\s*\{[^}]*position:\s*sticky/s);
  assert.match(styles, /@media \(prefers-reduced-motion: no-preference\)/);
  assert.match(styles, /:focus-visible/);
  assert.match(styles, /min-height:\s*48px/);
  assert.match(composer, /aria-live="polite"/);
});
