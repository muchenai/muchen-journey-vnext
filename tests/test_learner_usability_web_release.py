"""Learner usability must replace only Web on the proven learner refinements release."""
import ast
import copy
from contextlib import redirect_stdout
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
_original_path = list(sys.path)
try:
    sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "deploy/academy-release")]
    spec = importlib.util.spec_from_file_location(
        "learner_usability_web_release", ROOT / "deploy/learner-usability-web/activate.py")
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
finally:
    sys.path[:] = _original_path


@pytest.fixture
def web_environment(tmp_path, monkeypatch):
    candidate = "1" * 40
    loaded_id = "sha256:" + "2" * 64
    old_web, old_api = "sha256:" + "3" * 64, "sha256:" + "4" * 64
    config = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
    config_digest = "sha256:" + hashlib.sha256(config).hexdigest()
    config_name = config_digest[7:] + ".json"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for name, data in [("manifest.json", json.dumps([{"Config": config_name, "Layers": []}]).encode()),
                           (config_name, config)]:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
    tar_bytes = archive.getvalue()
    zipped = gzip.compress(tar_bytes)
    base = tmp_path / "releases" / release.BASE_RELEASE
    (base / "secrets").mkdir(parents=True)
    for name in release.COPY_FILES:
        (base / name).write_bytes(b"preserve configuration")
    (base / ".deployment.env").write_text(
        f"WEB_IMAGE={old_web}\nAPI_IMAGE={old_api}\nCANDIDATE_COMMIT={release.BASE}\n")
    (base / "secrets/web.env").write_text(f"APP_RELEASE={release.BASE}\n")
    (base / "secrets/api.env").write_text(f"APP_RELEASE={release.BASE}\nDATABASE_URL=private\n")
    for name in (*release.AI_SECRETS, "secrets/migration.env", "secrets/future-secret"):
        (base / name).write_bytes(b"preserve private settings")
        (base / name).chmod(0o600)
    # Learner refinements retains 0056 and writes these exact successful receipt shapes.
    (base / "activation-receipt.json").write_text(json.dumps({
        "status": "PASS", "release": release.BASE, "schema": release.SCHEMA,
        "database_schema_changed": False, "old_assignments_unchanged": True}))
    (base / "schema-upgrade-prepared.json").write_text(json.dumps({"manifest": {
        "candidate": release.BASE, "images": {"api": old_api, "web": old_web},
        "migrations": {"from": release.SCHEMA, "to": release.SCHEMA}}}))
    (tmp_path / "current").symlink_to(base, target_is_directory=True)
    package = tmp_path / "exploration-runs/1-1-activate"
    package.mkdir(parents=True)
    (package / "web.part0000").write_bytes(zipped)
    (package / "unrelated.keep").write_bytes(b"retain")
    pin = {"release_kind": "learner-usability-web", "candidate": candidate, "package_run_id": "12345678",
           "base_candidate": release.BASE, "base_release": release.BASE_RELEASE,
           "schema": release.SCHEMA, "disk_budget": {"import": 1024}, "archive": {
               "chunks": [{"file": "web.part0000", "sha256": hashlib.sha256(zipped).hexdigest()}],
               "gzip_sha256": hashlib.sha256(zipped).hexdigest(), "gzip_bytes": len(zipped),
               "tar_sha256": hashlib.sha256(tar_bytes).hexdigest(), "tar_bytes": len(tar_bytes),
               "config_digest": config_digest,
               "reference": "ghcr.io/muchenai/muchen-journey-vnext-web:" + candidate}}
    (package / "manifest.json").write_text(json.dumps(pin))
    before = {"services": {"api": {"image": old_api, "environment": {"APP_RELEASE": release.BASE}},
                           "web": {"image": old_web, "environment": {"APP_RELEASE": release.BASE}}}}
    state = {"release": release.BASE, "failure": None, "operations": [], "commands": [], "loaded": []}

    def compose(path, *args, **kwargs):
        if args[0] == "config":
            result = copy.deepcopy(before)
            if path != base:
                result["services"]["web"] = {"image": loaded_id, "environment": {"APP_RELEASE": candidate}}
            return json.dumps(result).encode()
        if args[0] == "exec":
            assert args[1:5] == ("-T", "api", "python", "-c")
            assert "SET TRANSACTION READ ONLY" in args[5]
            return json.dumps(["wrong" if state["failure"] == "schema" else release.SCHEMA]).encode()
        state["operations"].append((path, args))
        state["release"] = release.BASE if path == base else candidate
        if state["failure"] == "up" and path != base:
            raise release.UpgradeError("SIMULATED_UNHEALTHY_WEB")
        return b""

    def run(args, **kwargs):
        state["commands"].append(args)
        if args[1:3] == ["image", "inspect"]:
            return json.dumps([{"Id": loaded_id, "Os": "linux", "Architecture": "amd64",
                "Config": {"Labels": {"org.opencontainers.image.revision": candidate}}}]).encode()
        return b""

    def container(service):
        current = release.BASE if service == "api" else state["release"]
        requested = old_api if service == "api" else old_web if current == release.BASE else loaded_id
        if state["failure"] == "drift" and service == "api":
            requested = "sha256:" + "f" * 64
        return {"Id": service + "-stable", "Image": requested if current == release.BASE else config_digest,
                "State": {"Running": True, "Health": {"Status": "healthy"}},
                "Config": {"Image": requested, "Env": ["APP_RELEASE=" + current],
                           "Labels": {"org.opencontainers.image.revision": current}}}

    def urlopen(*args, **kwargs):
        stream = io.BytesIO(json.dumps({"status": "ready", "release": state["release"]}).encode())
        stream.status = 200
        return stream

    original_replace, original_write = os.replace, release.write_new
    def replace(src, dest):
        original_replace(src, dest)
        if state["failure"] == "pointer" and src.name == "current-" + candidate:
            raise KeyboardInterrupt()

    def write_new(path, data, *args):
        original_write(path, data, *args)
        if state["failure"] == "receipt" and path.name == "web-release-receipt.json":
            raise OSError("simulated receipt interruption")

    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release.socket, "gethostname", lambda: "journey-next-staging")
    monkeypatch.setattr(release, "compose", compose)
    monkeypatch.setattr(release, "run", run)
    monkeypatch.setattr(release, "container", container)
    monkeypatch.setattr(release, "protected_containers", lambda: {"api": "stable", "worker": "stable", "db": "stable"})
    monkeypatch.setattr(release, "check_space", lambda *_args: None)
    monkeypatch.setattr(release, "verify_loaded_image", lambda *args: state["loaded"].append(args))
    monkeypatch.setattr(release.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(release.os, "replace", replace)
    monkeypatch.setattr(release, "write_new", write_new)
    return {**locals(), "root": tmp_path}


def test_switches_only_web_on_refinements_baseline_and_binds_loaded_config(web_environment):
    env = web_environment
    release.activate(env["package"])
    new = (env["root"] / "current").resolve()
    assert new.name == env["candidate"] + "-learner-usability"
    receipt = json.loads((new / "web-release-receipt.json").read_text())
    assert receipt["release_kind"] == "learner-usability-web"
    assert receipt["web_candidate"] == env["candidate"]
    assert receipt["api_candidate"] == release.BASE
    assert receipt["schema"] == "0056_guild_halls" and receipt["database_writes"] == 0
    assert receipt["api_container_unchanged"] and receipt["other_containers_unchanged"]
    assert env["loaded_id"] != env["config_digest"]
    assert env["state"]["loaded"] == [(env["loaded_id"], env["config_digest"])]
    for original in (env["base"] / "secrets").iterdir():
        if original.name != "web.env":
            copied = new / "secrets" / original.name
            assert copied.read_bytes() == original.read_bytes()
            assert (copied.stat().st_uid, copied.stat().st_gid, copied.stat().st_mode) == (
                original.stat().st_uid, original.stat().st_gid, original.stat().st_mode)
    assert not (env["package"] / "web.part0000").exists()
    assert (env["package"] / "unrelated.keep").read_bytes() == b"retain"
    for _, args in env["state"]["operations"]:
        assert args[-1] == "web" and "--no-deps" in args and "--no-build" in args


@pytest.mark.parametrize("field,value", [
    ("base_candidate", "f" * 40), ("base_release", "b" * 40 + "-academy"),
    ("schema", "0054_academy_covers"),
])
def test_unapproved_baseline_stops_before_import(web_environment, field, value):
    env = web_environment
    pin = dict(env["pin"])
    pin[field] = value
    (env["package"] / "manifest.json").write_text(json.dumps(pin))
    with pytest.raises(release.UpgradeError, match="BASE_PIN"):
        release.activate(env["package"])
    assert not env["state"]["operations"] and not env["state"]["commands"]


def test_other_release_package_stops_before_import(web_environment):
    env = web_environment
    pin = copy.deepcopy(env["pin"])
    pin.pop("release_kind")
    (env["package"] / "manifest.json").write_text(json.dumps(pin))
    with pytest.raises(release.UpgradeError, match="LEARNER_USABILITY_RELEASE_KIND"):
        release.activate(env["package"])
    assert not env["state"]["operations"] and not env["state"]["commands"]


@pytest.mark.parametrize("failure", ["schema", "drift"])
def test_live_schema_or_api_drift_stops_before_import(web_environment, failure):
    env = web_environment
    env["state"]["failure"] = failure
    with pytest.raises(release.UpgradeError):
        release.activate(env["package"])
    assert not env["state"]["operations"] and not env["state"]["commands"]


@pytest.mark.parametrize("field,value", [
    ("status", "ROLLED_BACK"), ("release", "f" * 40), ("schema", "0054_academy_covers"),
])
def test_baseline_receipt_drift_stops_before_import(web_environment, field, value):
    env = web_environment
    path = env["base"] / "activation-receipt.json"
    receipt = json.loads(path.read_text())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(release.UpgradeError, match="BASE_RECEIPT"):
        release.activate(env["package"])
    assert not env["state"]["operations"] and not env["state"]["commands"]
    assert (env["root"] / "current").resolve() == env["base"]


@pytest.mark.parametrize("change,category", [
    ("candidate", "BASE_PREPARED_CANDIDATE"), ("api", "BASE_IMAGE_DRIFT"), ("web", "BASE_IMAGE_DRIFT"),
])
def test_baseline_prepared_evidence_must_match_live_images(web_environment, change, category):
    env = web_environment
    path = env["base"] / "schema-upgrade-prepared.json"
    prepared = json.loads(path.read_text())
    if change == "candidate":
        prepared["manifest"]["candidate"] = "f" * 40
    else:
        prepared["manifest"]["images"][change] = "sha256:" + "f" * 64
    path.write_text(json.dumps(prepared))
    with pytest.raises(release.UpgradeError, match=category):
        release.activate(env["package"])
    assert not env["state"]["operations"] and not env["state"]["commands"]


@pytest.mark.parametrize("change,category", [("chunk", "CHUNK_SHA"), ("reference", "WEB_SOURCE_REFERENCE")])
def test_unbound_transport_stops_before_loading_or_switching(web_environment, change, category):
    env = web_environment
    if change == "chunk":
        (env["package"] / "web.part0000").write_bytes(b"unverified archive")
    else:
        pin = copy.deepcopy(env["pin"])
        pin["archive"]["reference"] = pin["archive"]["reference"].replace("-web:", "-api:")
        (env["package"] / "manifest.json").write_text(json.dumps(pin))
    with pytest.raises(release.UpgradeError, match=category):
        release.activate(env["package"])
    assert not env["state"]["operations"] and not env["state"]["commands"]
    assert (env["root"] / "current").resolve() == env["base"]


def test_non_web_compose_change_is_rejected_before_switch(web_environment, monkeypatch):
    env = web_environment
    original = release.compose

    def changed_compose(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if args[0] == "config" and path != env["base"]:
            parsed = json.loads(result)
            parsed["services"]["api"]["environment"]["APP_RELEASE"] = env["candidate"]
            return json.dumps(parsed).encode()
        return result

    monkeypatch.setattr(release, "compose", changed_compose)
    with pytest.raises(release.UpgradeError, match="COMPOSE_EXTRA_CHANGE"):
        release.activate(env["package"])
    assert not env["state"]["operations"]
    assert (env["root"] / "current").resolve() == env["base"]


def test_non_web_runtime_change_detected_after_switch_rolls_back_only_web(web_environment, monkeypatch):
    env = web_environment

    def protected():
        image = env["old_api"] if env["state"]["release"] == release.BASE else "sha256:" + "f" * 64
        return {"/api": {"Id": "api-stable", "Image": image, "Config": {}, "HostConfig": {}, "Mounts": []}}

    monkeypatch.setattr(release, "protected_containers", protected)
    with pytest.raises(release.UpgradeError, match="PROTECTED_CONTAINER_CHANGED"):
        release.activate(env["package"])
    assert (env["root"] / "current").resolve() == env["base"]
    assert len(env["state"]["operations"]) == 2
    assert env["state"]["operations"][-1][0] == env["base"]
    assert all(args[-1] == "web" and "--no-deps" in args for _, args in env["state"]["operations"])


@pytest.mark.parametrize("failure,error", [("up", release.UpgradeError), ("pointer", KeyboardInterrupt), ("receipt", OSError)])
def test_failed_switch_rolls_back_web_only_and_removes_success_receipt(web_environment, failure, error):
    env = web_environment
    env["state"]["failure"] = failure
    with pytest.raises(error):
        release.activate(env["package"])
    assert (env["root"] / "current").resolve() == env["base"]
    new = env["root"] / "releases" / (env["candidate"] + "-learner-usability")
    assert not (new / "web-release-receipt.json").exists()
    assert json.loads((new / "web-rollback-receipt.json").read_text())["result"] == "ROLLED_BACK"
    assert env["state"]["operations"][-1][0] == env["base"]
    for _, args in env["state"]["operations"]:
        assert args[-1] == "web" and "--no-deps" in args


def test_mount_reordering_is_stable_but_changes_stop_without_exposing_secrets(monkeypatch):
    item = {"Name": "/api", "Id": "api-stable", "Image": "image-stable",
            "Config": {"Labels": {}, "Env": ["SECRET=private"]}, "HostConfig": {},
            "Mounts": [{"Destination": "/a", "Source": "/private-a", "RW": False},
                       {"Destination": "/b", "Source": "/private-b", "RW": True}]}
    reordered = copy.deepcopy(item)
    reordered["Mounts"].reverse()
    outputs = iter([b"api-stable", json.dumps([item]).encode(), b"api-stable", json.dumps([reordered]).encode()])
    monkeypatch.setattr(release, "run", lambda *_args: next(outputs))
    before, after = release.protected_containers(), release.protected_containers()
    assert before == after
    after["/api"]["Mounts"][0]["RW"] = True
    monkeypatch.setattr(release, "protected_containers", lambda: after)
    output = io.StringIO()
    with redirect_stdout(output), pytest.raises(release.UpgradeError, match="PROTECTED_CHANGED"):
        release.verify_protected_containers(before, "PROTECTED_CHANGED")
    assert "Mounts" in output.getvalue()
    assert "private" not in output.getvalue() and "SECRET" not in output.getvalue()


def test_release_pins_successful_mainline_and_protects_api_database_and_ingress():
    package_source = (ROOT / "deploy/learner-usability-web/package.py").read_text()
    pin = next(ast.literal_eval(node.value) for node in ast.parse(package_source).body
               if isinstance(node, ast.Assign) and any(
                   isinstance(target, ast.Name) and target.id == "BASE_PIN" for target in node.targets))
    assert pin == {"release_kind": "learner-usability-web",
                   "base_candidate": "ef06970c1658f8d583bdaf9bd3a4fd90c13fdc49",
                   "base_release": "ef06970c1658f8d583bdaf9bd3a4fd90c13fdc49-learner-refinements",
                   "schema": "0056_guild_halls"}
    assert (release.BASE, release.BASE_RELEASE, release.SCHEMA) == (
        pin["base_candidate"], pin["base_release"], pin["schema"])
    workflow = (ROOT / ".github/workflows/learner-usability-web-release.yml").read_text()
    package = (ROOT / "deploy/learner-usability-web/package.py").read_text()
    source = (ROOT / "deploy/learner-usability-web/activate.py").read_text()
    for required in ("inputs.expected_commit == github.sha", "PACKAGE_RUN: ${{ inputs.package_run }}",
                     "run['status']=='completed' and run['conclusion']=='success'",
                     "run['head_sha']==p['candidate']", "run['name']=='Mainline Candidate Gate'",
                     "environment: production-canary-uat", "group: wp08-volcengine-staging",
                     "cancel-in-progress: false", "if: always() && steps.runner.outputs.cidr != ''",
                     'wp08_security_group close --security-group-id "$SECURITY_GROUP" --cidr "$RUNNER_CIDR"'):
        assert required in workflow
    assert "binding == json.loads((build / 'candidate-binding.json').read_text())" in package
    assert "['images']['web']" in package and "['images']['api']" not in package
    assert "source_config_digest(src" in source and "verify_loaded_image(image" in source
    assert "fcntl.LOCK_EX | fcntl.LOCK_NB" in source
    assert "alembic upgrade" not in source and "docker build" not in workflow
    assert "run: python3 deploy/learner-usability-web/package.py" in workflow
    assert "deploy/learner-usability-web/activate.py" in package
    assert "deploy/exploration-release/transfer_package.py" in workflow
    assert "deploy/academy-release/disk_space.py" in workflow
    assert "'LEARNER_USABILITY_WEB_RELEASE_FAILED'" in source
    for text in (workflow, package, source):
        assert "profile-growth" not in text and "journey-profile-web" not in text
        assert "b1be86fb9dfb81e67fc58965417a0d86061a61d4" not in text
