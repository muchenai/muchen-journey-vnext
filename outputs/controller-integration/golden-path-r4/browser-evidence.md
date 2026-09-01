# Browser evidence — controller golden path R4

The candidate was exercised in a production-mode local Docker Compose environment using a fresh `SYNTHETIC_NO_REAL_PII` Journey V3 record.

Natural path:

1. `/` — visitor understands one five-map People AI growth journey and accepts the invitation.
2. `/join` — invitation confirmation preserves the five-map orientation and one primary action.
3. `/app` — the current Exploration Camp station is foregrounded within the whole journey.
4. `/app/tasks/:assignmentId#first-learning-input` — the first required material is open and output remains locked.

Observed browser results:

- 390, 768, and 1280 pixel viewports had document width equal to viewport width.
- The home and `/app` primary CTA remained visible in the first viewport at all three widths.
- Each decision surface had exactly one primary CTA.
- The shared home visibly included all five ordered maps.
- The `/app` hero preserved the whole-journey context and explicitly said the newcomer walks only this station now.
- The invitation token did not remain in the visible body or resulting URL.
- A fresh production-mode browser session recorded 0 console errors and 0 warnings.
- No live environment or real business data was touched.

Evidence files and hashes are frozen in `candidate-manifest.json`.

