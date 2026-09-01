# Exploration Camp private-invite orientation V2 browser evidence

Status: `MACHINE_PASS / HUMAN_NOT_RUN / RELEASE_NOT_AUTHORIZED`

The controller exercised the existing production build in an isolated local Docker Compose project named
`journey-next-exploration-v2`. All users, invitations, Journey versions, materials, and progress facts were
`SYNTHETIC_NO_REAL_PII`; no production endpoint or real invitation was used.

## Natural path

1. Opened a local private invitation as `/join#token=…`; hydration removed the fragment and left both
   `location.hash` and `location.search` empty.
2. Before the first action, `/join` showed `Muchen Journey · 01 / 05`, five maps, Exploration Camp, and a
   phase-accurate “now / next” explanation.
3. Used the visible controls to verify the invitation, confirm a synthetic display name, and enter `/app`.
4. `/app` displayed the eight-stage Exploration Camp projection and exactly one `打开第一份必读材料` action.
5. The action opened `/app/tasks/:assignmentId#first-learning-input`; the first required material was visible,
   while the learner output remained locked until all required material had been completed.

The local Journey V3 and required materials were created through existing versioned API commands only for this
test. They were never exported as company content or treated as approved human evidence.

## Responsive and interaction results

- 390×844: no horizontal overflow; `/app` CTA bounds remained inside the first viewport; material visible and output locked.
- 768×1024: no horizontal overflow; `/app` CTA bounds remained inside the first viewport; material visible and output locked.
- 1280×900: no horizontal overflow; the natural path reached the required material and retained one primary action.
- Reduced motion: media query active with zero running animations.
- Console: `0` errors, `0` warnings.
- Token safety: token absent from the final URL, page text, screenshots, and stored evidence.

Representative evidence is frozen under `evidence/`. Screenshots prove layout and state only; they do not replace
the four required first-time-human acceptance criteria.
