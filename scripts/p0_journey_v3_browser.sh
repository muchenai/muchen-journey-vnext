#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
evidence_dir="$repo_root/output/playwright/p0-journey-v3"
project_name="journey-next-p0-browser-$$"
learner_session="p0-v3-learner-$$"
reviewer_session="p0-v3-reviewer-$$"
db_port=${MJ_DB_PORT:-35542}
api_port=${MJ_API_PORT:-38110}
web_port=${MJ_WEB_PORT:-33210}
base_url="http://127.0.0.1:$web_port"
api_url="http://127.0.0.1:$api_port"
runtime_config="$evidence_dir/cli.config.json"

cleanup() {
    bash "$PLAYWRIGHT_CLI" -s="$learner_session" close >/dev/null 2>&1 || true
    bash "$PLAYWRIGHT_CLI" -s="$reviewer_session" close >/dev/null 2>&1 || true
    docker compose --project-directory "$repo_root" -p "$project_name" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

mkdir -p "$evidence_dir"
chmod 0700 "$evidence_dir"
rm -f "$evidence_dir"/*.log "$evidence_dir"/*.png

MJ_DB_PORT=$db_port MJ_API_PORT=$api_port MJ_WEB_PORT=$web_port \
    docker compose --project-directory "$repo_root" -p "$project_name" \
    up --build -d --wait db api web >/dev/null

invite_token=$(python3 "$repo_root/scripts/p0_journey_v3_browser_fixture.py" --base-url "$api_url")
if [ "${#invite_token}" -lt 32 ]; then
    printf '%s\n' "P0_BROWSER_ERROR=fixture_invite_missing" >&2
    exit 2
fi

reviewer_credentials=$(docker compose --project-directory "$repo_root" -p "$project_name" \
    exec -T api python scripts/p0_browser_reviewer_session.py)
reviewer_token=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["session"])' "$reviewer_credentials")
reviewer_csrf=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["csrf"])' "$reviewer_credentials")
unset reviewer_credentials

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

learner_log="$evidence_dir/learner-cli.log"
reviewer_log="$evidence_dir/reviewer-cli.log"
pw_learner() {
    bash "$PLAYWRIGHT_CLI" -s="$learner_session" "$@" >>"$learner_log" 2>&1
}
pw_reviewer() {
    bash "$PLAYWRIGHT_CLI" -s="$reviewer_session" "$@" >>"$reviewer_log" 2>&1
}

# The credential is intentionally neither printed nor retained in evidence.
bash "$PLAYWRIGHT_CLI" -s="$learner_session" open \
    "$base_url/join#token=$invite_token" --config "$runtime_config" >/dev/null 2>&1
unset invite_token

bash "$PLAYWRIGHT_CLI" -s="$reviewer_session" open \
    "about:blank" --config "$runtime_config" >/dev/null 2>&1
bash "$PLAYWRIGHT_CLI" -s="$reviewer_session" run-code "async (page) => {
  await page.context().addCookies([
    {name: 'journey_next_session', value: '$reviewer_token', url: '$base_url', httpOnly: true, sameSite: 'Lax'},
    {name: 'journey_next_csrf', value: '$reviewer_csrf', url: '$base_url', sameSite: 'Lax'},
  ]);
}" >/dev/null 2>&1
unset reviewer_token reviewer_csrf

pw_learner run-code "async (page) => {
  await page.waitForLoadState('networkidle');
  if (await page.getByRole('button', {name: '打开通行证'}).count()) throw new Error('two-step invite still visible');
  await page.locator('#display-name').fill('P0 Browser Learner');
  await page.getByRole('checkbox').check();
  await Promise.all([
    page.waitForURL('**/app'),
    page.getByRole('button', {name: '开启旅程'}).click(),
  ]);
  await page.waitForLoadState('networkidle');
  const progress = (await page.locator('[aria-label^="已完成"]').getAttribute('aria-label')) ?? '';
  if (!/已完成\s+0\s*\/\s*8\s+站/.test(progress)) throw new Error('Journey V3 progress missing');
}"
pw_learner screenshot --filename "$evidence_dir/01-first-station.png" --full-page

complete_stage() {
    stage_no=$1
    pw_learner run-code "async (page) => {
      await page.getByRole('link', {name: '进入这一站'}).click();
      await page.waitForURL('**/app/tasks/**');
      await page.waitForLoadState('networkidle');
      if ($stage_no === 1) {
        const link = page.getByRole('link', {name: '打开学习材料'});
        if (await link.count() !== 1) throw new Error('frozen text URL is not clickable');
        const href = await link.getAttribute('href');
        if (!href || !href.startsWith('https://')) throw new Error('learning link is not HTTPS');
      }
      while (await page.getByRole('button', {name: '完成本材料'}).count()) {
        const completed = page.waitForURL('**?material=completed');
        await page.getByRole('button', {name: '完成本材料'}).first().evaluate((element) => element.click());
        await completed;
        await page.waitForLoadState('networkidle');
      }
      if (await page.getByRole('button', {name: '开始这一站'}).count()) {
        await page.getByRole('button', {name: '开始这一站'}).click();
        await page.waitForLoadState('networkidle');
      }
      await page.locator('#submission-body').fill('第 ${stage_no} 站浏览器验证：我完成了固定输入，记录当前判断、可定位依据、风险边界以及下一步行动。');
      const submit = page.getByRole('button', {name: /完成这一站|交给 Reviewer/});
      await Promise.all([page.waitForURL('**/app'), submit.click()]);
      await page.waitForLoadState('networkidle');
    }"
}

complete_revision() {
    pw_learner run-code "async (page) => {
      const body = await page.locator('body').innerText();
      if (!body.includes('根据反馈修订任务')) throw new Error('revision state missing');
      await page.getByRole('link', {name: '进入这一站'}).click();
      await page.waitForLoadState('networkidle');
      const input = page.locator('#submission-body');
      await input.fill((await input.inputValue()) + ' 修订补充：新增一条可复核证据，并明确判断失效时的停止条件。');
      await Promise.all([
        page.waitForURL('**/app'),
        page.getByRole('button', {name: '提交修订版本'}).click(),
      ]);
      await page.waitForLoadState('networkidle');
    }"
}

complete_review() {
    decision=$1
    pw_reviewer goto "$base_url/review"
    pw_reviewer run-code "async (page) => {
      await page.waitForLoadState('networkidle');
      const detail = page.waitForURL(/\/review\/[^/?]+$/);
      await page.locator('.queue-item').first().evaluate((element) => element.click());
      await detail;
      await page.waitForLoadState('networkidle');
      if (await page.getByRole('button', {name: '开始评审'}).count()) {
        const started = page.waitForURL('**?started=yes');
        await page.getByRole('button', {name: '开始评审'}).evaluate((element) => element.click());
        await started;
        await page.waitForLoadState('networkidle');
      }
      if (!(await page.locator('input[value=\"MEETS\"]').count())) throw new Error('review rubric missing');
      const needsRevision = '$decision' === 'revision';
      await page.locator('input[value=' + (needsRevision ? '\"NEEDS_WORK\"' : '\"MEETS\"') + ']').first().check();
      await page.locator('.rubric-feedback').first().fill(needsRevision ? '请补充可定位证据和停止条件。' : '证据与判断对应，下一步清晰。');
      await page.locator('#overall-feedback').fill(needsRevision ? '请按维度反馈补充证据后再次提交。' : '本阶段证据完整，可以继续下一站。');
      await page.locator('input[value=' + (needsRevision ? '\"REQUEST_REVISION\"' : '\"APPROVE\"') + ']').check();
      await page.getByRole('button', {name: '提交不可变最终结论'}).click();
      await page.waitForLoadState('networkidle');
    }"
}

# Day 0 and four treasures progress on learner evidence.
complete_stage 1
complete_stage 2
complete_stage 3
complete_stage 4
complete_stage 5

# First assessment proves revision and safe same-session resubmission.
complete_stage 6
complete_review revision
pw_learner reload
pw_learner screenshot --filename "$evidence_dir/02-revision-required.png" --full-page
complete_revision
complete_review approve

# Remaining assessments prove repeated reviewer progression.
pw_learner reload
complete_stage 7
complete_review approve
pw_learner reload
complete_stage 8
complete_review approve

pw_learner reload
pw_learner run-code "async (page) => {
  const resultPage = page.waitForURL('**/app/result');
  await page.getByRole('link', {name: '打开旅程结果'}).evaluate((element) => element.click());
  await resultPage;
  await page.waitForLoadState('networkidle');
  const body = await page.locator('body').innerText();
  if (!body.includes('这段旅程，走完了。') || !body.includes('探索营通过')) {
    throw new Error('final journey result missing');
  }
}"
pw_learner screenshot --filename "$evidence_dir/03-journey-complete.png" --full-page

pw_learner console error
pw_reviewer console error
if grep -Eiq '(\[error\]|console\.error|uncaught|pageerror)' "$learner_log" "$reviewer_log"; then
    printf '%s\n' "P0_BROWSER_ERROR=console_error" >&2
    exit 2
fi

printf '%s\n' "P0_JOURNEY_V3_BROWSER=PASS invite=one_step stages=8 revision=resubmitted reviewer=complete"
