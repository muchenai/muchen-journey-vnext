# Shared home browser evidence

Date: 2026-08-23  
Runtime: Next.js 16.2.11 production build (`next build --webpack`)  
Browser config: `/Users/liumowen/Documents/Muchen Journey2.0/output/playwright/wp25/cli.config.json`  
Browser: configured Playwright Chromium; no browser installation performed  
State source: read-only local HTTP fixture matching `GET /api/v1/session` and `GET /api/v1/me/current-action`; no real identity, invite, or production data used

## Three-viewport visitor checks

| Viewport | Product promise | State | CTA bottom / viewport | Horizontal width | Primary CTA count | Touch target | Result |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 390 × 844 | 五张地图，走成一个人的长期成长 | visitor | 823 / 844 | 390 / 390 | 1 | 52 px | PASS |
| 768 × 1024 | 五张地图，走成一个人的长期成长 | visitor | 961 / 1024 | 768 / 768 | 1 | 52 px | PASS |
| 1280 × 900 | 五张地图，走成一个人的长期成长 | visitor | 642 / 900 | 1280 / 1280 | 1 | 52 px | PASS |

Screenshots:

- `browser-evidence/visitor-390.png`
- `browser-evidence/visitor-768.png`
- `browser-evidence/visitor-1280.png`

## State checks

| State | Evidence | Primary action | Executable result | Result |
| --- | --- | --- | --- | --- |
| visitor-without-session | no learner cookie; direct invitation form on `/` | 我已有专属邀请 | existing `exchangeInvite` server action; no empty `/join` navigation | PASS |
| learner-with-active-session | valid `/api/v1/session`; current action `exploration-camp-journey-v3` | 继续当前旅程 | `/app`, current Journey `探索营` | PASS |
| learner-with-expired-session | `auth_error=LEARNER_SESSION_EXPIRED`; no learner cookie | 使用重新进入链接 | invalid non-real test link reached `/join?code=INVITE_EXPIRED_OR_REVOKED`, displayed recovery action and request id | PASS |
| learner-with-next-map-unlocked | valid session; current action `newcomer-village-journey-v1` | 进入下一张地图 | `/app`, Journey title `新手村`; hard-coded read-only eyebrow recorded in controller proposal | PASS_WITH_INTEGRATION_NOTE |

State screenshots:

- `browser-evidence/active-1280.png`
- `browser-evidence/expired-390.png`
- `browser-evidence/unlocked-1280.png`

## Interaction and recovery

- Keyboard: three Tab presses from page start focused the invitation input; `:focus-visible` was true.
- Touch/pointer: CTA click executed the real server-action route; minimum measured CTA height was 52 px.
- Reduced motion: emulated `prefers-reduced-motion: reduce`; media query matched, document animations = 0, CTA transition duration = 0 s.
- Error and re-entry: a deliberately invalid, non-real 32-character token was rejected with the expected recoverable `/join` error and a still-visible `验证专属邀请` action.
- Prefetch: returning-state links use `prefetch={false}`; no unsolicited `/app` authentication request was observed before activation.
- Console: production-browser shared-home, expired, and invalid-link recovery checks reported 0 errors and 0 warnings.
- No real invite was created or consumed. No production mutation was executed.

## Boundary note

The future unlocked-state destination currently contains a read-only Exploration Camp eyebrow even when its server-owned Journey title is `新手村`. See `controller-proposal.md`. The mismatch is unreachable while Exploration Camp remains the only active authoritative Journey, but it must be repaired before a later map is activated.
