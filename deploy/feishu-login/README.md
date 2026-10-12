# Feishu client login release

This release changes only the production Canary API and Web images. The candidate
and successful mainline package run are pinned in `manifest.json`. The workflow
must run on the exact reviewed `main` commit and retains the existing protected
`production-canary-uat` environment and deployment concurrency group.

Before activation, the script requires the current Web labels release
`50650ae883b14c3ec7485ebb20f518e47e0ac748` and API release
`9e24e64a6b35509da1f28a0dd0e4f8f2131c7399`. It checks archive, image configuration,
revision and platform hashes, and allows only API/Web image and release-label
changes in the existing configuration. Credentials, database and learner settings
are copied unchanged. No migration, seed or account reset is run.

Both containers must become healthy. Public readiness, learner/reviewer/operator
entry pages, the exact SDK asset and a bound native-login start request must pass
before the current release pointer changes. A failure restores both prior images.
All other existing containers must retain their IDs.

The Feishu application's exact production `/join` URL must be allowed alongside
the existing browser callback URL. Native login still requires a real Feishu
client; automated public checks do not claim end-to-end native authorization.
