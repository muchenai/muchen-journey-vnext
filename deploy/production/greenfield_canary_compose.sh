#!/usr/bin/env bash
set -euo pipefail

# Every independent SSH/recovery entrypoint uses the literal release environment.
# Do not source this file: its values may contain shell metacharacters.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec python3 ./wp31_exec_env.py --env-file ./.deployment.env -- docker compose "$@"
