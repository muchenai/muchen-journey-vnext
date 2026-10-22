"""Read-only release inventory. No secret values, learner text or DB writes."""
import json
from pathlib import Path
import re
import socket
import subprocess


def safe_application_errors(raw):
    """Return technical identifiers only; never raw messages, SQL or values."""
    if len(raw.encode("utf-8")) > 4 * 1024 * 1024:
        return {"status": "LOG_LIMIT_EXCEEDED"}
    classes = ("TypeError", "ReferenceError", "RangeError", "ApiRequestError",
               "ResponseValidationError", "ValidationError", "ProgrammingError",
               "OperationalError", "InsufficientPrivilege", "UndefinedTable",
               "UndefinedColumn", "InvalidTextRepresentation")
    paths = ("task-definitions", "enrollments", "audit", "runtime-status",
             "identity-access", "invites", "invitation-control", "notification-endpoints",
             "notification-deliveries", "formal-journeys", "content-drafts",
             "reviewer-workload", "invite-targets")
    identifiers = r"[A-Za-z_][A-Za-z0-9_]{0,127}"
    result = {
        "digest_found": "3941254938" in raw,
        "error_codes": [name for name in ("VALIDATION_FAILED", "INVALID_RESPONSE", "UNAUTHENTICATED", "FORBIDDEN", "NOT_FOUND", "INTERNAL_ERROR", "RATE_LIMITED", "SERVICE_UNAVAILABLE")
                        if re.search(r"\bcode:\s*['\"]" + name + r"['\"]", raw)],
        "error_statuses": sorted(set(int(value) for value in re.findall(r"\bstatus:\s*([45][0-9]{2})\b", raw))),
        "exception_classes": [name for name in classes if re.search(r"\b" + name + r"\b", raw)],
        "markers": [label for phrase, label in (
            ("permission denied", "PERMISSION_DENIED"),
            ("Invalid URL", "INVALID_URL"),
            ("Cannot read properties", "MISSING_PROPERTY"),
            ("is not a function", "NOT_CALLABLE"),
            ("fetch failed", "FETCH_FAILED"),
        ) if phrase in raw],
        "denied_tables": sorted(set(re.findall(r"permission denied for table [\"']?(" + identifiers + r")", raw))),
        "missing_relations": sorted(set(re.findall(r'relation "(' + identifiers + r')" does not exist', raw))),
        "api_frames": sorted(set(re.findall(r'File "/app/apps/api/journey_api/([a-zA-Z0-9_./-]+\.py)", line ([0-9]{1,6})', raw))),
        "ops_responses": [],
    }
    for line in raw.splitlines():
        access = re.search(r'GET (/api/v1/ops/(?:' + '|'.join(paths) + r'))(?:\?[^\s"]*)? HTTP/[^\s"]+" ([45][0-9]{2})\b', line)
        if access:
            entry = {"path": access.group(1), "status": int(access.group(2))}
            if entry not in result["ops_responses"]:
                result["ops_responses"].append(entry)
        # Only the logger's JSON request metadata is considered. No headers,
        # query strings, exception input values or arbitrary paths are returned.
        start = line.find('{"')
        if start < 0:
            continue
        try:
            item = json.loads(line[start:])
        except (ValueError, TypeError):
            continue
        if not isinstance(item, dict):
            continue
        path, status = item.get("route", item.get("path")), item.get("status")
        if path in {"/api/v1/ops/" + suffix for suffix in paths} and isinstance(status, int) and status >= 400:
            entry = {"path": path, "status": status}
            if entry not in result["ops_responses"]:
                result["ops_responses"].append(entry)
    return result


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
application_errors = {}
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
    try:
        logs = subprocess.run(["docker", "logs", "--since", "24h", "--tail", "5000", ids[0]],
                              text=True, capture_output=True, timeout=30)
        application_errors[service] = safe_application_errors(logs.stdout + logs.stderr) if logs.returncode == 0 else {"status": "UNAVAILABLE"}
    except subprocess.TimeoutExpired:
        application_errors[service] = {"status": "TIMEOUT"}

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
                  "docker_diagnostics": diagnostics, "application_errors": application_errors}, indent=2))
