import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const orientation = await readFile(
  new URL("../src/app/join/private-invite-orientation.tsx", import.meta.url),
  "utf8",
);
const joinPage = await readFile(new URL("../src/app/join/page.tsx", import.meta.url), "utf8");
const inviteForm = await readFile(
  new URL("../src/app/join/invite-token-exchange-form.tsx", import.meta.url),
  "utf8",
);
const styles = await readFile(
  new URL("../src/app/join/private-invite-orientation.module.css", import.meta.url),
  "utf8",
);

test("private invitations explain the whole Journey before the first form action", () => {
  assert.match(orientation, /01 \/ 05/);
  assert.match(orientation, /五张地图/);
  assert.match(orientation, /探索营/);
  assert.match(orientation, /第一份必读材料/);
  assert.match(orientation, /VERIFY_INVITE/);
  assert.match(orientation, /CONFIRM_IDENTITY/);
  assert.match(orientation, /REENTRY/);
  assert.match(orientation, /验证专属邀请/);
  assert.match(orientation, /确认这是你的邀请并开启旅程/);
  assert.match(orientation, /确认邀请并恢复原有旅程/);
});

test("the orientation is non-interactive and preserves one primary form action", () => {
  assert.doesNotMatch(orientation, /<(?:a|button|input|form)\b/);
  assert.doesNotMatch(orientation, /tabIndex/);
  assert.ok(joinPage.indexOf("<PrivateInviteOrientation") < joinPage.indexOf("{errorMessage ?"));
  assert.ok(joinPage.indexOf("<PrivateInviteOrientation") < joinPage.indexOf("{summary ?"));
  assert.match(joinPage, /aria-describedby=\{orientationDescriptionId\}/);
  assert.match(joinPage, /orientationDescriptionId=\{orientationDescriptionId\}/);
});

test("both invitation exchange states retain fragment security and share the orientation context", () => {
  assert.equal(inviteForm.match(/aria-describedby=\{orientationDescriptionId\}/g)?.length, 2);
  assert.match(inviteForm, /window\.location\.hash\.slice\(1\)/);
  assert.match(inviteForm, /window\.history\.replaceState\(null, "", "\/join"\)/);
  assert.match(inviteForm, /type="hidden" name="token" value=\{token\}/);
  assert.match(inviteForm, /placeholder="https:\/\/…\/join#token=…"/);
});

test("local styles remain responsive and isolated from shared home selectors", () => {
  assert.match(styles, /@media \(min-width: 768px\)/);
  assert.match(styles, /overflow-wrap: anywhere/);
  assert.doesNotMatch(styles, /animation|transition/);
  assert.doesNotMatch(styles, /\.landing-|\.button\b/);
});
