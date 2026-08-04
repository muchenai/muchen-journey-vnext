#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'WP16_WEB_ONLY_ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "must run as root"
[[ "${WP16_CANDIDATE:-}" =~ ^[0-9a-f]{40}$ ]] || fail "candidate is invalid"
[[ "${WP16_BASELINE:-}" =~ ^[0-9a-f]{40}$ ]] || fail "baseline is invalid"
[[ "${WP16_WEB_IMAGE:-}" =~ ^ghcr\.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:[0-9a-f]{64}$ ]] || fail "Web image is not immutable"
[[ "${WP16_PUBLIC_URL:-}" == "https://staging-vnext.muchenai.com" || "${WP16_PUBLIC_URL:-}" == "https://journey.muchenai.com" ]] || fail "public URL is invalid"
[[ "${WP16_MARKER:-}" == /srv/journey-next-staging/DEPLOYED_WEB_CANDIDATE || "${WP16_MARKER:-}" == /srv/journey-next-production/DEPLOYED_WEB_CANDIDATE ]] || fail "marker path is invalid"
expected_home_marker="${WP16_EXPECTED_HOME_MARKER:-把一个真实问题，变成清晰的下一步。}"
[[ "$expected_home_marker" == "把一个真实问题，变成清晰的下一步。" || "$expected_home_marker" == "这里，没有标准答案。" ]] || fail "home marker is invalid"

for path in compose.yaml .deployment.env secrets/api.env secrets/worker.env secrets/web.env; do
  [[ -f "$path" && ! -L "$path" ]] || fail "$path must be a regular file"
done
[[ "$(stat -c '%a' secrets/web.env)" == "600" ]] || fail "web.env must be 0600"
grep -qx "APP_RELEASE=$WP16_BASELINE" secrets/api.env || fail "API is not at the frozen baseline"
grep -qx "APP_RELEASE=$WP16_BASELINE" secrets/worker.env || fail "Worker is not at the frozen baseline"
grep -qx "APP_RELEASE=$WP16_BASELINE" secrets/web.env || fail "Web is not at the expected baseline"
grep -Eq '^WEB_IMAGE=ghcr\.io/muchenai2024-creator/muchen-journey-vnext-web@sha256:[0-9a-f]{64}$' .deployment.env || fail "current Web image is not immutable"
set -a
. ./.deployment.env
set +a

umask 077
rollback_dir=$(mktemp -d "$PWD/.wp16-web-rollback.XXXXXX")
cp .deployment.env "$rollback_dir/deployment.env"
cp secrets/web.env "$rollback_dir/web.env"
mutated=0

finish() {
  code=$?
  trap - EXIT
  if [[ "$code" -ne 0 && "$mutated" -eq 1 ]]; then
    printf 'WP16_WEB_ONLY_ROLLBACK=START target=%s\n' "$WP16_PUBLIC_URL" >&2
    cp "$rollback_dir/deployment.env" .deployment.env
    cp "$rollback_dir/web.env" secrets/web.env
    chmod 0600 secrets/web.env
    set -a
    . ./.deployment.env
    set +a
    if docker compose up -d --no-deps --force-recreate --wait web && \
       [[ "$(docker compose exec -T web printenv APP_RELEASE)" == "$WP16_BASELINE" ]]; then
      printf 'WP16_WEB_ONLY_ROLLBACK=PASS target=%s\n' "$WP16_PUBLIC_URL" >&2
    else
      printf 'WP16_WEB_ONLY_ROLLBACK=FAILED target=%s\n' "$WP16_PUBLIC_URL" >&2
    fi
  fi
  rm -rf -- "$rollback_dir"
  exit "$code"
}
trap finish EXIT

docker compose config --quiet
timeout 600 docker pull "$WP16_WEB_IMAGE" >/dev/null
docker image inspect "$WP16_WEB_IMAGE" >/dev/null

python3 - .deployment.env WEB_IMAGE "$WP16_WEB_IMAGE" <<'PY'
import os
import stat
import sys
from pathlib import Path

path, key, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = path.read_text().splitlines()
matches = [index for index, line in enumerate(lines) if line.startswith(f"{key}=")]
assert len(matches) == 1
lines[matches[0]] = f"{key}={value}"
temporary = path.with_suffix(path.suffix + ".wp16")
temporary.write_text("\n".join(lines) + "\n")
os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
os.replace(temporary, path)
PY
python3 - secrets/web.env APP_RELEASE "$WP16_CANDIDATE" <<'PY'
import os
import stat
import sys
from pathlib import Path

path, key, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = path.read_text().splitlines()
matches = [index for index, line in enumerate(lines) if line.startswith(f"{key}=")]
assert len(matches) == 1
lines[matches[0]] = f"{key}={value}"
temporary = path.with_suffix(path.suffix + ".wp16")
temporary.write_text("\n".join(lines) + "\n")
os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
os.replace(temporary, path)
PY
mutated=1

set -a
. ./.deployment.env
set +a
docker compose config --quiet
docker compose up -d --no-deps --force-recreate --wait web
[[ "$(docker compose exec -T web printenv APP_RELEASE)" == "$WP16_CANDIDATE" ]] || fail "Web release differs"
[[ "$(docker compose exec -T api printenv APP_RELEASE)" == "$WP16_BASELINE" ]] || fail "API release changed"
[[ "$(docker compose exec -T worker printenv APP_RELEASE)" == "$WP16_BASELINE" ]] || fail "Worker release changed"

ready=$(curl -fsS --max-time 15 "$WP16_PUBLIC_URL/health/ready")
python3 - "$WP16_CANDIDATE" "$ready" <<'PY'
import json
import sys

assert json.loads(sys.argv[2]) == {"status": "ready", "release": sys.argv[1]}
PY
root_html=$(curl -fsS --max-time 15 "$WP16_PUBLIC_URL/")
grep -Fq "$expected_home_marker" <<<"$root_html"
[[ "$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "$WP16_PUBLIC_URL/ops")" == "401" ]] || fail "anonymous ops access is not denied"
[[ "$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' "$WP16_PUBLIC_URL/review")" == "401" ]] || fail "anonymous review access is not denied"

printf '%s\n' "$WP16_CANDIDATE" >"$WP16_MARKER"
chmod 0644 "$WP16_MARKER"
mutated=0
printf 'WP16_WEB_ONLY_DEPLOY=PASS target=%s candidate=%s api_worker=%s\n' "$WP16_PUBLIC_URL" "$WP16_CANDIDATE" "$WP16_BASELINE"
