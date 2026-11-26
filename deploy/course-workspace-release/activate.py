"""Roll the live exploration release forward to the learner/administrator course workspace."""
import json
import re

from dynamic_release import Activation, BASE as PRIOR_API, WEB_BASE as PRIOR_WEB, SECRET_FILES, PACKAGE_FILES
from dynamic_release import execute
from canary_schema_upgrade import COPY_FILES, ENV_FILES, ROOT, Upgrade, read_file, require
from grant_runtime import TABLES


class CourseWorkspaceActivation(Activation):
    base_api = base_web = "cf5615788d5d44608c9b9e317ee2b0761a8075b0"
    source_schema = "0060_migrated_ai_ownership"
    target_schema = "0063_admin_video_storage"
    new_tables = TABLES
    seeds_curriculum = False
    in_flight_sql = (
        "select (" + Activation.in_flight_sql + ") + (select count(*) from exploration_self_checks "
        "where status = 'RUNNING' and created_at >= current_timestamp - interval '10 minutes')"
    )
    protected_endpoints = (*Activation.protected_endpoints, "/api/review-native/course-workspace",
                           "/api/review-native/experience/permissions")

    def __init__(self, manifest, package):
        Upgrade.__init__(self, manifest, package)
        self.base = ROOT / "releases" / (self.base_api + "-dynamic-exploration")
        require(manifest["base_release"] == self.base.as_posix()
                and manifest["base_candidate"] == manifest["base_web_candidate"] == self.base_api, "BASE_PATH")
        require(manifest.get("schema_version") == 4
                and manifest["migrations"] == {"from": self.source_schema, "to": self.target_schema}, "SCHEMA_PIN")
        require(manifest["database"] == "journey_next_canary_20260901_c72fea5", "DATABASE_PIN")
        require(re.fullmatch(r"[0-9a-f]{40}", manifest["candidate"]) and manifest["candidate"] != self.base_api, "CANDIDATE")
        require(re.fullmatch(r"[0-9]+", manifest["package_run_id"]), "PACKAGE_RUN")
        self.new = ROOT / "releases" / (manifest["candidate"] + "-course-workspace")
        self.backup = ROOT / "backups" / ("course-workspace-" + manifest["candidate"])

        receipt = json.loads(read_file(self.base / "activation-receipt.json"))
        prepared = json.loads(read_file(self.base / "schema-upgrade-prepared.json"))
        previous = prepared["manifest"]
        require(receipt.get("status") == "PASS" and receipt.get("release") == self.base_api
                and receipt.get("schema") == self.source_schema and receipt.get("package_run_id") == "44357590475"
                and receipt.get("previous_api_release") == PRIOR_API and receipt.get("previous_web_release") == PRIOR_WEB
                and receipt.get("existing_business_rows_preserved") is True and receipt.get("curriculum_initialized") is True
                and receipt.get("other_containers_unchanged") is True, "BASE_ACTIVATION_RECEIPT")
        require(previous["candidate"] == self.base_api and previous["package_run_id"] == receipt["package_run_id"]
                and previous["base_candidate"] == PRIOR_API and previous["base_web_candidate"] == PRIOR_WEB
                and previous["database"] == manifest["database"] and previous["migrations"]["to"] == self.source_schema
                and previous["images"]["dbrestore"] == manifest["images"]["dbrestore"], "BASE_PREPARED_MANIFEST")
        require(manifest["old_images"] == {}, "OLD_IMAGE_OVERRIDE")
        manifest["old_images"] = {name: previous["images"][name] for name in ("api", "web")}
        require(all(re.fullmatch(r"sha256:[0-9a-f]{64}", image) for image in self.old_images.values()), "OLD_IMAGE_ID")
        self.base_hashes = prepared["hashes"]
        required = set(COPY_FILES + ENV_FILES + PACKAGE_FILES) | set(SECRET_FILES.values()) | {"secrets/migration.env"}
        require(required <= self.base_hashes.keys(), "BASE_CONFIGURATION_PROOF")
        require(all((name in required or re.fullmatch(r"secrets/[A-Za-z0-9_.-]+", name))
                    and re.fullmatch(r"[0-9a-f]{64}", value)
                    for name, value in self.base_hashes.items()), "BASE_CONFIGURATION_PATH")
        self.verify_base_configuration()

    def verify_login_configuration(self):
        super().verify_login_configuration()
        probe = """
from journey_api.main import app
from journey_api.content_assets import CHUNK_SIZE
from journey_api.video_limits import MAX_VIDEO_SIZE
assert CHUNK_SIZE == 2 * 1024**2 and MAX_VIDEO_SIZE == 2 * 1024**3
paths = app.openapi()["paths"]
for path in ("/api/v1/ops/course-workspace", "/api/v1/me/course-workspace",
             "/api/v1/review-admin/content-assets", "/api/v1/ops/experience/permissions"):
    assert path in paths
print("COURSE_RUNTIME_READY")
"""
        require(self.docker_api("secrets/api.env", "python", "-c", probe, read_only=True).strip()
                == b"COURSE_RUNTIME_READY", "COURSE_RUNTIME_CONFIG")


if __name__ == "__main__":
    execute(CourseWorkspaceActivation)
