"""Read-only release inventory. No secret values, learner text or DB writes."""
import json
from pathlib import Path
import socket
import subprocess

assert socket.gethostname() == "journey-next-staging", "UNEXPECTED_HOST"
PROJECT = "journey-next-greenfield-canary"
ROOT = Path("/srv/journey-next-production/canary")
current = (ROOT / "current").resolve(strict=True)
assert current.is_relative_to(ROOT / "releases"), "UNEXPECTED_RELEASE_PATH"


def run(args, input=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError("INVENTORY_COMMAND_FAILED")
    return result.stdout


containers = {}
for service in ("api", "web"):
    ids = run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=" + PROJECT,
               "--filter", "label=com.docker.compose.service=" + service]).split()
    assert len(ids) == 1, "UNEXPECTED_CONTAINER_COUNT"
    item = json.loads(run(["docker", "inspect", ids[0]]))[0]
    env = dict(value.split("=", 1) for value in item["Config"]["Env"] if "=" in value)
    allowed = ("APP_ENV", "APP_RELEASE", "RELEASE_MARKER", "FEISHU_APP_ID", "FEISHU_OAUTH_ENABLED",
               "FEISHU_OAUTH_REDIRECT_URI", "FEISHU_LEARNER_REGISTRATION_ENABLED", "ALLOW_FIXTURE_IDENTITY")
    containers[service] = {"image": item["Config"]["Image"], "health": item["State"].get("Health", {}).get("Status"),
                           "config": {key: env.get(key) for key in allowed},
                           "learner_org_configured": bool(env.get("FEISHU_LEARNER_ORGANIZATION_ID")),
                           "learner_reviewer_configured": bool(env.get("FEISHU_LEARNER_REVIEWER_ID"))}
    if service == "api":
        api = ids[0]

probe = '''
import json
from sqlalchemy import text
from journey_api.db import SessionLocal
with SessionLocal() as session:
    session.execute(text("SET TRANSACTION READ ONLY"))
    result={"migration":session.execute(text("select version_num from alembic_version")).scalars().all()}
    for table in ("users","enrollments","assignments","submissions","submission_versions","reviews","evaluations"):
        result[table+"_count"]=session.execute(text("select count(*) from "+table)).scalar_one()
    result["reviewers"]= [dict(row) for row in session.execute(text("select u.id::text, u.organization_id::text, u.display_name, exists(select 1 from external_identities e where e.user_id=u.id and e.provider='FEISHU' and e.revoked_at is null) as feishu_bound, (select count(*) from enrollments n where n.reviewer_id=u.id) as enrollment_count, (select count(*) from reviews v where v.reviewer_id=u.id and v.status in ('ASSIGNED','IN_REVIEW')) as pending_review_count from users u join role_assignments r on r.user_id=u.id and r.organization_id=u.organization_id where r.role='REVIEWER' and u.status='ACTIVE' order by u.id limit 20")).mappings()]
    result["journeys"]=[dict(row) for row in session.execute(text("select j.organization_id::text,j.stable_key,v.id::text,v.version from journey_definitions j join journey_versions v on v.journey_definition_id=j.id where j.status='PUBLISHED' order by v.version desc limit 20")).mappings()]
    result["stages"]=[dict(row) for row in session.execute(text("select s.stable_key,s.position,s.title,s.completion_policy,t.id::text as task_version_id,t.version,t.learning_materials from journey_stage_versions s join task_versions t on t.id=s.task_version_id where s.journey_version_id='889b6c4c-09b9-4415-948b-a028f73087db' order by s.position")).mappings()]
    for stage in result["stages"]:
        stage["learning_materials"]=[{key: material.get(key) for key in ('key','title','kind','url','required')} for material in stage['learning_materials']]
    print(json.dumps(result))
'''
database = json.loads(run(["docker", "exec", "-i", api, "python", "-"], input=probe))
images = [json.loads(line) for line in run(["docker", "image", "ls", "--digests", "--format", "json"]).splitlines() if line.strip()]
images = [{key: item.get(key) for key in ("Repository", "Tag", "Digest", "ID", "Size")}
          for item in images if item.get("Repository", "").startswith("ghcr.io/muchenai/muchen-journey-vnext-")]
paths = {name: (ROOT / relative).exists() for name, relative in {
    "prior_preparation_exists": "releases/05e7e0d2ca488bcdbf0fbf8ab964d98ea3efc292-exploration",
    "prior_backup_exists": "backups/exploration-05e7e0d2ca488bcdbf0fbf8ab964d98ea3efc292",
    "prior_backup_receipt_exists": "backups/exploration-05e7e0d2ca488bcdbf0fbf8ab964d98ea3efc292/backup-receipt.json",
}.items()}
diagnostics = {}
for label, command in {
    "storage_driver": ["docker", "info", "--format", "{{.Driver}}"],
    "docker_disk_percent": ["df", "--output=pcent", "/var/lib/docker"],
}.items():
    try:
        diagnostics[label] = run(command).strip()[:100]
    except (RuntimeError, subprocess.TimeoutExpired):
        diagnostics[label] = "UNAVAILABLE"
try:
    journal = run(["journalctl", "-u", "docker", "--since", "-1 hour", "--no-pager", "-n", "200"]).lower()
    diagnostics["docker_error_counts"] = {word: journal.count(word) for word in
        ("timeout", "deadline exceeded", "failed to resolve", "failed to extract", "no space left", "unauthorized")}
except (RuntimeError, subprocess.TimeoutExpired):
    diagnostics["docker_error_counts"] = "UNAVAILABLE"
print(json.dumps({"current_release": str(current), "containers": containers, "database": database,
                  "cached_journey_images": images, "preparation_paths": paths,
                  "docker_diagnostics": diagnostics}, indent=2))
