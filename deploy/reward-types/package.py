"""Bind the successful build, its SBOMs and image archives to one offline release."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.wp07_image_archive import verify_files
from scripts.wp31_candidate_binding import build_binding


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def package(build, output):
    source = ROOT / "deploy/reward-types"
    manifest = json.loads((source / "baseline.json").read_text(encoding="utf-8"))
    manifest["candidate"] = os.environ["CANDIDATE"]
    manifest["package_run_id"] = os.environ["PACKAGE_RUN"]
    for line in (build / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        path = (build / name).resolve()
        assert path.parent == build.resolve() and sha(path) == expected, "HANDOFF_SHA"
    binding = build_binding(build / "release-manifest.json", manifest["package_run_id"])
    assert binding == json.loads((build / "candidate-binding.json").read_text()), "BINDING_CHANGED"
    assert binding["application_candidate_sha"] == manifest["candidate"], "CANDIDATE_CHANGED"
    verify_files(build / "release-manifest.json", build / "image-archives.json", build / "images")
    archive_manifest = json.loads((build / "image-archives.json").read_text())
    output.mkdir(mode=0o700, exist_ok=False)
    manifest["archives"] = {}
    manifest["registry_images"] = binding["images"]
    for name in ("api", "web"):
        entry = archive_manifest["images"][name]
        manifest["images"][name] = entry["local_image_digest"]
        compressed = output / (name + ".tar.gz")
        with (build / "images" / entry["file"]).open("rb") as original, compressed.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=3, mtime=0) as target:
                shutil.copyfileobj(original, target)
        chunks = []
        with compressed.open("rb") as handle:
            index = 0
            # Smaller parts suit the slow cross-region link without changing hashes.
            while data := handle.read(2 * 1024 * 1024):
                path = output / f"{name}.part{index:04}"
                path.write_bytes(data)
                chunks.append({"file": path.name, "sha256": hashlib.sha256(data).hexdigest()})
                index += 1
        manifest["archives"][name] = {"gzip_sha256": sha(compressed), "source_tar_sha256": entry["sha256"], "config_digest": entry["local_image_digest"], "source_reference": entry["runtime_reference"], "chunks": chunks}
        compressed.unlink()
    files = {
        "restore_backup.py": ROOT / "deploy/admin-reviewed/restore_backup.py",
        "diagnose_backup.py": ROOT / "deploy/admin-reviewed/diagnose_backup.py",
        "activate.py": source / "activate.py", "prepare.py": ROOT / "deploy/exploration-release/prepare.py",
        "facts_guard.py": source / "facts_guard.py",
        "canary_schema_upgrade.py": ROOT / "scripts/canary_schema_upgrade.py",
        "wp31_database_snapshot.py": ROOT / "scripts/wp31_database_snapshot.py",
        "db_facts.py": ROOT / "deploy/production/db_facts.py",
        "db_facts_control.py": ROOT / "deploy/production/db_facts.py",
        "grant_runtime.py": source / "grant_runtime.py",
    }
    for name, path in files.items():
        shutil.copyfile(path, output / name)
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    checksums = [sha(path) + "  " + path.name for path in sorted(output.iterdir())]
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
    print(json.dumps({"offline_package": "PASS", "candidate": manifest["candidate"], "files": len(checksums)}))


if __name__ == "__main__":
    package(Path(os.environ["BUILD_DIR"]), Path(os.environ["PACKAGE_DIR"]))
