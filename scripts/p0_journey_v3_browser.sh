#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
evidence_dir="$repo_root/output/playwright/p0-journey-v3"
project_name="journey-next-p0-browser-$$"
initial_learner_session="p0-v3-learner-$$"
learner_reentry_session="p0-v3-learner-reentry-$$"
invalid_invite_session="p0-v3-invalid-invite-$$"
learner_session="$initial_learner_session"
reviewer_session="p0-v3-reviewer-$$"
operator_session="p0-v3-operator-$$"
db_port=${MJ_DB_PORT:-35542}
api_port=${MJ_API_PORT:-38110}
web_port=${MJ_WEB_PORT:-33210}
base_url="http://127.0.0.1:$web_port"
api_url="http://127.0.0.1:$api_port"
runtime_config="$evidence_dir/cli.config.json"

cleanup() {
    bash "$PLAYWRIGHT_CLI" -s="$initial_learner_session" close >/dev/null 2>&1 || true
    bash "$PLAYWRIGHT_CLI" -s="$learner_reentry_session" close >/dev/null 2>&1 || true
    bash "$PLAYWRIGHT_CLI" -s="$invalid_invite_session" close >/dev/null 2>&1 || true
    bash "$PLAYWRIGHT_CLI" -s="$reviewer_session" close >/dev/null 2>&1 || true
    bash "$PLAYWRIGHT_CLI" -s="$operator_session" close >/dev/null 2>&1 || true
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

operator_credentials=$(docker compose --project-directory "$repo_root" -p "$project_name" \
    exec -T api python scripts/p0_browser_reviewer_session.py --role OPERATOR)
operator_token=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["session"])' "$operator_credentials")
operator_csrf=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["csrf"])' "$operator_credentials")
unset operator_credentials

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
recovery_log="$evidence_dir/recovery-cli.log"
reviewer_log="$evidence_dir/reviewer-cli.log"
operator_log="$evidence_dir/operator-cli.log"
pw_learner() {
    bash "$PLAYWRIGHT_CLI" -s="$learner_session" "$@" >>"$learner_log" 2>&1
}
pw_reviewer() {
    bash "$PLAYWRIGHT_CLI" -s="$reviewer_session" "$@" >>"$reviewer_log" 2>&1
}
pw_operator() {
    bash "$PLAYWRIGHT_CLI" -s="$operator_session" "$@" >>"$operator_log" 2>&1
}

# Invalid tokens must fail without creating a join fact and without exposing raw API JSON.
bash "$PLAYWRIGHT_CLI" -s="$invalid_invite_session" open \
    "$base_url/join#token=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
    --config "$runtime_config" >/dev/null 2>&1
bash "$PLAYWRIGHT_CLI" -s="$invalid_invite_session" run-code "async (page) => {
  await page.waitForLoadState('networkidle');
  await page.locator('#display-name').fill('Invalid Invite Browser Check');
  await page.getByRole('checkbox').check();
  await page.getByRole('button', {name: '开启旅程'}).click();
  await page.waitForURL('**/join?code=INVITE_EXPIRED_OR_REVOKED**');
  await page.waitForLoadState('networkidle');
  const body = await page.locator('body').innerText();
  if (!body.includes('邀请无效、已过期、已撤销或已经使用')) {
    throw new Error('invalid invite does not provide a safe recovery message');
  }
  if (body.includes('Authentication required.') || body.includes('{\"error\"')) {
    throw new Error('invalid invite exposes a raw API response');
  }
  await page.screenshot({path: '$evidence_dir/00-invalid-invite.png', fullPage: true});
}" >>"$recovery_log" 2>&1

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

bash "$PLAYWRIGHT_CLI" -s="$operator_session" open \
    "about:blank" --config "$runtime_config" >/dev/null 2>&1
bash "$PLAYWRIGHT_CLI" -s="$operator_session" run-code "async (page) => {
  await page.context().addCookies([
    {name: 'journey_next_session', value: '$operator_token', url: '$base_url', httpOnly: true, sameSite: 'Lax'},
    {name: 'journey_next_csrf', value: '$operator_csrf', url: '$base_url', sameSite: 'Lax'},
  ]);
}" >/dev/null 2>&1
unset operator_token operator_csrf

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
  for (const viewport of [
    {name: 'desktop', width: 1280, height: 900},
    {name: 'tablet', width: 768, height: 1024},
    {name: 'mobile', width: 390, height: 844},
  ]) {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    const geometry = await page.evaluate(() => {
      const maps = Array.from(document.querySelectorAll('.journey-route-map'));
      const svg = maps.find((item) => getComputedStyle(item).display !== 'none');
      if (!(svg instanceof SVGSVGElement)) return {error: 'visible_svg_missing'};
      const line = svg.querySelector('polyline');
      const matrix = svg.getScreenCTM();
      if (!(line instanceof SVGPolylineElement) || !matrix) return {error: 'line_missing'};
      const anchors = Array.from(svg.querySelectorAll('.route-node-anchor'));
      const distances = anchors.map((anchor) => {
        const index = Number(anchor.getAttribute('data-route-index'));
        const routePoint = line.points.getItem(index);
        const point = svg.createSVGPoint();
        point.x = routePoint.x;
        point.y = routePoint.y;
        const projected = point.matrixTransform(matrix);
        const orb = anchor.querySelector('.route-node-orb');
        const box = orb?.getBoundingClientRect();
        if (!box) return Number.POSITIVE_INFINITY;
        return Math.hypot(box.left + box.width / 2 - projected.x, box.top + box.height / 2 - projected.y);
      });
      return {maxDistance: Math.max(...distances), nodes: anchors.length};
    });
    if ('error' in geometry || geometry.nodes !== 8 || geometry.maxDistance > 1.5) {
      throw new Error(viewport.name + ': route nodes drifted off shared line geometry: ' + JSON.stringify(geometry));
    }
    if (await page.locator('.button.primary:visible').count() !== 1) {
      throw new Error(viewport.name + ': route does not have one primary next action');
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    if (overflow) throw new Error(viewport.name + ': route has horizontal overflow');
    if (viewport.name === 'mobile') {
      const currentStage = await page.locator('.current-stage-card').boundingBox();
      const routeMap = await page.locator('.journey-map').boundingBox();
      if (!currentStage || !routeMap || currentStage.y >= routeMap.y) {
        throw new Error('mobile route does not put the current action before the map');
      }
    }
    await page.screenshot({
      path: '$evidence_dir/01-first-station-' + viewport.name + '.png',
      fullPage: true,
    });
  }
  await page.setViewportSize({width: 1280, height: 900});
}"
pw_learner screenshot --filename "$evidence_dir/01-first-station.png" --full-page

# A missing assignment exercises the bounded service-failure surface without changing business facts.
pw_learner goto "$base_url/app/tasks/00000000-0000-0000-0000-000000000000"
pw_learner run-code "async (page) => {
  await page.waitForLoadState('networkidle');
  const body = await page.locator('body').innerText();
  if (!body.includes('操作没有完成') || !body.includes('重试') || !body.includes('返回我的旅程')) {
    throw new Error('service failure does not provide retry and return actions');
  }
  if (body.includes('Authentication required.') || body.includes('{\"error\"')) {
    throw new Error('service failure exposes a raw API response');
  }
}"
pw_learner screenshot --filename "$evidence_dir/01-service-failure.png" --full-page
pw_learner goto "$base_url/app"
pw_learner run-code "async (page) => { await page.waitForLoadState('networkidle'); }"

pw_operator goto "$base_url/ops#learner-invites"
pw_operator run-code "async (page) => {
  await page.waitForLoadState('networkidle');
  const expected = [
    ['P0_BROWSER_PRIMARY', '已使用'],
    ['P0_BROWSER_PENDING', '已兑换，待确认身份'],
    ['P0_BROWSER_UNUSED', '待使用'],
  ];
  for (const [purpose, status] of expected) {
    const item = page.locator('.invite-list > li').filter({hasText: purpose});
    if (await item.count() !== 1) throw new Error('invite row missing: ' + purpose);
    if (!(await item.innerText()).includes(status)) {
      throw new Error('invite status mismatch: ' + purpose + ' expected=' + status);
    }
  }
}"
pw_operator screenshot --filename "$evidence_dir/01-invite-statuses.png" --full-page

complete_stage() {
    stage_no=$1
    pw_learner run-code "async (page) => {
      await page.getByRole('link', {name: '开始', exact: true}).click();
      await page.waitForURL('**/app/tasks/**');
      await page.waitForLoadState('networkidle');
      const brief = page.locator('.task-brief');
      if (await brief.count() !== 1) throw new Error('stage $stage_no task brief missing');
      const briefText = await brief.innerText();
      if (!briefText.includes('需要提交') || !briefText.includes('怎么做') || !briefText.includes('完成标准')) {
        throw new Error('stage $stage_no task requirements are not visible on first entry');
      }
      if (await brief.locator('details').count()) {
        throw new Error('stage $stage_no task requirements are hidden in disclosure');
      }
      if (await page.locator('.task-workspace').count() !== 0) {
        throw new Error('stage $stage_no response workspace appeared before learning input');
      }
      if (await page.locator('.button.primary:visible').count() !== 1) {
        throw new Error('stage $stage_no does not have one primary next action');
      }
      if ($stage_no === 1) {
        for (const viewport of [
          {name: 'desktop', width: 1280, height: 900},
          {name: 'tablet', width: 768, height: 1024},
          {name: 'mobile', width: 390, height: 844},
        ]) {
          await page.setViewportSize({width: viewport.width, height: viewport.height});
          if (await page.locator('.learning-material-card[open]').count() !== 1) {
            throw new Error(viewport.name + ': current material is not the only expanded card');
          }
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
          if (overflow) throw new Error(viewport.name + ': task page has horizontal overflow');
          await page.screenshot({
            path: '$evidence_dir/02-first-task-' + viewport.name + '.png',
            fullPage: true,
          });
        }
        await page.setViewportSize({width: 1280, height: 900});
      }
      const links = page.locator('.learning-material-content a');
      if (await links.count() < 1) throw new Error('stage $stage_no has no clickable HTTPS material');
      for (let index = 0; index < await links.count(); index += 1) {
        const href = await links.nth(index).getAttribute('href');
        if (!href || !href.startsWith('https://')) {
          throw new Error('stage $stage_no material is not HTTPS');
        }
      }
      while (await page.getByRole('button', {name: '完成并继续'}).count()) {
        const completed = page.waitForURL('**?material=completed');
        await page.getByRole('button', {name: '完成并继续'}).first().evaluate((element) => element.click());
        await completed;
        await page.waitForLoadState('networkidle');
      }
      if ($stage_no === 1) {
        for (const viewport of [
          {name: 'desktop', width: 1280, height: 900},
          {name: 'tablet', width: 768, height: 1024},
          {name: 'mobile', width: 390, height: 844},
        ]) {
          await page.setViewportSize({width: viewport.width, height: viewport.height});
          const brief = page.locator('.task-brief');
          const workspace = page.locator('.task-workspace');
          if (await brief.count() !== 1 || await workspace.count() !== 1) {
            throw new Error(viewport.name + ': visible task brief or response workspace missing after learning input');
          }
          if (!(await brief.innerText()).includes('需要提交')) {
            throw new Error(viewport.name + ': required deliverables are not visible before response');
          }
          if (!(await brief.innerText()).includes('怎么做') || !(await brief.innerText()).includes('完成标准')) {
            throw new Error(viewport.name + ': complete task requirements are not visible');
          }
          const briefBox = await brief.boundingBox();
          const workspaceBox = await workspace.boundingBox();
          if (!briefBox || !workspaceBox || briefBox.y >= workspaceBox.y) {
            throw new Error(viewport.name + ': task goal and deliverables do not precede the response workspace');
          }
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
          if (overflow) throw new Error(viewport.name + ': visible task brief has horizontal overflow');
          await page.screenshot({
            path: '$evidence_dir/03-visible-task-brief-' + viewport.name + '.png',
            fullPage: true,
          });
        }
        await page.setViewportSize({width: 1280, height: 900});
      }
      if (await page.getByRole('button', {name: '开始小任务'}).count()) {
        await page.getByRole('button', {name: '开始小任务'}).click();
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
      await page.getByRole('link', {name: '继续修订', exact: true}).click();
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

# First assessment proves revision and safe new-browser reentry.
complete_stage 6
complete_review revision

reentry_token=$(python3 "$repo_root/scripts/p0_journey_v3_browser_fixture.py" \
    --base-url "$api_url" --create-reentry --learner-display-name "P0 Browser Learner")
if [ "${#reentry_token}" -lt 32 ]; then
    printf '%s\n' "P0_BROWSER_ERROR=reentry_invite_missing" >&2
    exit 2
fi
bash "$PLAYWRIGHT_CLI" -s="$learner_reentry_session" open \
    "$base_url/join#token=$reentry_token&flow=reentry" --config "$runtime_config" >/dev/null 2>&1
unset reentry_token
bash "$PLAYWRIGHT_CLI" -s="$learner_reentry_session" run-code "async (page) => {
  await page.waitForLoadState('networkidle');
  if (await page.locator('#display-name').count()) throw new Error('reentry asks for a new learner identity');
  if (!(await page.locator('body').innerText()).includes('继续未完成的旅程')) {
    throw new Error('reentry purpose is not visible');
  }
  await page.getByRole('checkbox').check();
  await Promise.all([
    page.waitForURL('**/app'),
    page.getByRole('button', {name: '继续旅程'}).click(),
  ]);
  await page.waitForLoadState('networkidle');
  if (!(await page.locator('body').innerText()).includes('根据反馈修订任务')) {
    throw new Error('reentry did not restore the revision action');
  }
}" >>"$learner_log" 2>&1

pw_learner goto "$base_url/app"
pw_learner run-code "async (page) => {
  await page.waitForLoadState('networkidle');
  if (!page.url().includes('auth_error=LEARNER_SESSION_EXPIRED')) {
    throw new Error('old learner session was not rotated after reentry');
  }
  const body = await page.locator('body').innerText();
  if (!body.includes('新人会话已失效') || !body.includes('一次性重新进入链接')) {
    throw new Error('expired learner session does not provide the safe reentry path');
  }
  if (body.includes('Authentication required.') || body.includes('{\"error\"')) {
    throw new Error('expired learner session exposes a raw API response');
  }
}"
learner_session="$learner_reentry_session"
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
  await page.getByRole('link', {name: '查看结果', exact: true}).evaluate((element) => element.click());
  await resultPage;
  await page.waitForLoadState('networkidle');
  const visibleBody = await page.locator('body').innerText();
  if (!visibleBody.includes('这段旅程，走完了。') || !visibleBody.includes('下一步')) {
    throw new Error('final journey summary or handoff missing');
  }
}"
pw_learner screenshot --filename "$evidence_dir/03-journey-complete.png" --full-page
pw_learner run-code "async (page) => {
  await page.getByText('查看评审与准入详情', {exact: true}).click();
  const expandedBody = await page.locator('body').innerText();
  if (!expandedBody.includes('探索营通过')) {
    throw new Error('final reviewer conclusion missing after disclosure');
  }
}"
pw_learner screenshot --filename "$evidence_dir/03-journey-details.png" --full-page

pw_learner console error
pw_reviewer console error
pw_operator console error
if grep -Eiq '(\[error\]|console\.error|uncaught|pageerror)' "$learner_log" "$recovery_log" "$reviewer_log" "$operator_log"; then
    printf '%s\n' "P0_BROWSER_ERROR=console_error" >&2
    exit 2
fi

printf '%s\n' "P0_JOURNEY_V3_BROWSER=PASS fixture=synthetic invite=one_step invite_statuses=3 recovery=invalid_invite+service_failure+expired_session reentry=new_browser old_session=revoked material_links=8 visible_task_brief=8_stages route_geometry=3_viewports stages=8 revision=resubmitted reviewer=complete external_access=not_proven human_uat=not_run"
