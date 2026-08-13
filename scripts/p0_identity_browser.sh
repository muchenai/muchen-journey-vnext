#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
evidence_dir="$repo_root/output/playwright/p0-identity"
project_name="journey-next-p0-identity-$$"
browser_session="p0-identity-$$"
db_port=${MJ_DB_PORT:-35562}
api_port=${MJ_API_PORT:-38130}
web_port=${MJ_WEB_PORT:-33230}
base_url="http://127.0.0.1:$web_port"
api_url="http://127.0.0.1:$api_port"
runtime_config="$evidence_dir/cli.config.json"

cleanup() {
    bash "$PLAYWRIGHT_CLI" -s="$browser_session" close >/dev/null 2>&1 || true
    docker compose --project-directory "$repo_root" -p "$project_name" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

mkdir -p "$evidence_dir"
chmod 0700 "$evidence_dir"
rm -f "$evidence_dir"/*.log "$evidence_dir"/*.png "$evidence_dir"/*.json

MJ_DB_PORT=$db_port MJ_API_PORT=$api_port MJ_WEB_PORT=$web_port \
    docker compose --project-directory "$repo_root" -p "$project_name" \
    up --build -d --wait db api web >/dev/null

credentials=$(docker compose --project-directory "$repo_root" -p "$project_name" \
    exec -T api python scripts/p0_identity_browser_session.py)
session_token=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["session"])' "$credentials")
csrf_token=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["csrf"])' "$credentials")
unset credentials

python3 - "$runtime_config" "$PLAYWRIGHT_CHROMIUM_EXECUTABLE" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "browser": {
                "launchOptions": {"executablePath": sys.argv[2], "headless": True},
                "contextOptions": {"viewport": {"width": 1280, "height": 900}},
            }
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

bash "$PLAYWRIGHT_CLI" -s="$browser_session" open \
    "about:blank" --config "$runtime_config" >/dev/null 2>&1
bash "$PLAYWRIGHT_CLI" -s="$browser_session" run-code "async (page) => {
  await page.context().addCookies([
    {name: 'journey_next_session', value: '$session_token', url: '$base_url', httpOnly: true, sameSite: 'Lax'},
    {name: 'journey_next_csrf', value: '$csrf_token', url: '$base_url', sameSite: 'Lax'},
  ]);
}" >/dev/null 2>&1
unset session_token csrf_token

browser_log="$evidence_dir/browser.log"
pwcli() {
    bash "$PLAYWRIGHT_CLI" -s="$browser_session" "$@" >>"$browser_log" 2>&1
}

pwcli goto "$base_url/content"
pwcli run-code "async (page) => {
  await page.locator('h1').waitFor({state: 'visible', timeout: 10000});
  if (page.url().endsWith('/content/login')) throw new Error('multi-role session lost content workspace');
  if ((await page.locator('h1').innerText()).trim() !== '准备真实学习内容') {
    throw new Error('content workspace did not render');
  }
}"
pwcli screenshot --filename "$evidence_dir/01-content-workspace.png" --full-page

pwcli goto "$base_url/review"
pwcli run-code "async (page) => {
  await page.locator('h1').waitFor({state: 'visible', timeout: 10000});
  if (page.url().includes('/review/login')) throw new Error('multi-role session entered reviewer login loop');
  if (page.url().includes('auth_error=')) throw new Error('multi-role session returned an auth error');
  if ((await page.locator('h1').innerText()).trim() !== '现在先评谁？') {
    throw new Error('review workspace did not render');
  }
}"
pwcli screenshot --filename "$evidence_dir/02-review-workspace.png" --full-page

bash "$PLAYWRIGHT_CLI" -s="$browser_session" --raw run-code "async (page) => {
  const response = await page.context().request.get('$api_url/api/v1/session', {
    headers: {Cookie: (await page.context().cookies()).map((cookie) => cookie.name + '=' + cookie.value).join('; ')},
  });
  const payload = await response.json();
  return JSON.stringify({status: response.status(), roles: payload.data?.roles, workspaces: payload.data?.allowed_workspaces});
}" >"$evidence_dir/session-readback.json"
python3 - "$evidence_dir/session-readback.json" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8").strip()
result = json.loads(json.loads(raw) if raw.startswith('"') else raw)
expected = {
    "status": 200,
    "roles": ["CONTENT_EDITOR", "REVIEWER"],
    "workspaces": ["content", "review"],
}
if result != expected:
    raise SystemExit(f"multi-role session readback mismatch: {result}")
PY

pwcli console error >"$evidence_dir/console-errors.txt"
if grep -Eiq '(\[error\]|console\.error|uncaught|pageerror)' "$evidence_dir/console-errors.txt"; then
    printf '%s\n' "browser console contains errors" >&2
    exit 2
fi

printf '%s\n' "P0_IDENTITY_BROWSER=PASS content=PASS review=PASS auth_loop=ABSENT"
