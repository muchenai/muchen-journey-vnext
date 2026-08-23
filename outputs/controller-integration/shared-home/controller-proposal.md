# Shared home controller proposal: map-aware learner hub labels

## Learner need

When the authoritative `GET /api/v1/me/current-action` response moves a learner from Exploration Camp to a later Journey, the shared home correctly identifies the new map from `journey.stable_key` and sends the learner to `/app`. The destination must name the same current map throughout so that “进入下一张地图” does not open a visually contradictory context.

## Observed compatibility gap

Read-only browser evidence with an authoritative `newcomer-village-journey-v1` projection showed:

- shared home: `探索营` = completed, `新手村` = current;
- shared home CTA: `进入下一张地图` → `/app`;
- `/app` Journey title: `新手村`;
- `/app` current-stage eyebrow: `探索营 · 当前进度 · 第 1 站`.

The hard-coded label is in the read-only dependency `apps/web/src/app/app/page.tsx`. Related Exploration Camp aria text also exists in `apps/web/src/app/app/journey-map.tsx`. This shared-home candidate does not modify either file.

## Proposed controller change

Before any non-Exploration Journey can become the authoritative current action:

1. derive the visible current-map name from the same server-owned Journey projection already used by `/app`;
2. replace hard-coded Exploration Camp labels and aria text with that derived name;
3. retain `/app` as the single learner growth-hub route and avoid query-string or browser-storage map state;
4. regression-test Exploration Camp plus the first cross-map transition.

## Compatibility and migration

- API/schema change: none required for the observed label gap.
- data migration: none.
- current Exploration Camp candidate: unaffected and remains frozen.
- activation constraint: must land before program control activates a non-Exploration `journey.stable_key` for learners.
- release authority: unchanged; this proposal does not authorize implementation, merge, or release.

## Evidence

The Playwright state stub returned the same `CurrentAction` shape as the checked-in API contract and varied only the server-owned `journey.stable_key`. Browser result: `/app` pathname, Journey title `新手村`, eyebrow `探索营 · 当前进度 · 第 1 站`, one primary action, zero browser console errors on the shared-home surfaces.
