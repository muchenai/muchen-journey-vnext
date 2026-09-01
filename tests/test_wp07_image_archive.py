import json
from pathlib import Path

import pytest

import scripts.wp07_image_archive as archive


SHA = "a" * 40


def release_manifest(tmp_path: Path) -> Path:
    images = {}
    for index, component in enumerate(archive.COMPONENTS, start=1):
        images[component] = {
            "registry_reference": (
                "ghcr.io/muchenai/muchen-journey-vnext-"
                f"{component}:{SHA}"
            ),
            "registry_digest": "sha256:" + str(index) * 64,
            "local_image_digest": "sha256:" + str(index + 3) * 64,
        }
    path = tmp_path / "release-manifest.json"
    path.write_text(
        json.dumps(
            {
                "candidate": {"commit_sha": SHA},
                "images": images,
                "external_status": {"registry_push": "VERIFIED"},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_pack_binds_archives_to_candidate_registry_and_local_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = release_manifest(tmp_path)
    output = tmp_path / "images"

    def fake_run(arguments):
        arguments = tuple(arguments)
        if arguments[:3] == ("docker", "image", "inspect"):
            component = next(
                item for item in archive.COMPONENTS if f"-{item}:" in arguments[-1]
            )
            index = archive.COMPONENTS.index(component) + 1
            return json.dumps(
                [
                    {
                        "Id": "sha256:" + str(index + 3) * 64,
                        "Config": {
                            "Labels": {"org.opencontainers.image.revision": SHA}
                        },
                    }
                ]
            )
        assert arguments[:3] == ("docker", "image", "save")
        path = Path(arguments[4])
        path.write_bytes((arguments[-1] + "\n").encode())
        return ""

    monkeypatch.setattr(archive, "run", fake_run)
    result = archive.pack(release, output)

    assert result["candidate_commit"] == SHA
    assert set(result["images"]) == set(archive.COMPONENTS)
    assert archive.verify_files(
        release, tmp_path / "image-archives.json", output
    ) == {"candidate_commit": SHA, "archive_count": 3}


def test_verify_rejects_archive_tampering(tmp_path: Path):
    release = release_manifest(tmp_path)
    output = tmp_path / "images"
    output.mkdir()
    entries = {}
    release_value = json.loads(release.read_text())
    for component in archive.COMPONENTS:
        path = output / f"{component}.tar"
        path.write_bytes(component.encode())
        source = release_value["images"][component]
        entries[component] = {
            "file": path.name,
            "sha256": archive.sha256(path),
            "size_bytes": path.stat().st_size,
            "runtime_reference": source["registry_reference"],
            "local_image_digest": source["local_image_digest"],
            "registry_digest": source["registry_digest"],
        }
    manifest = tmp_path / "image-archives.json"
    manifest.write_text(
        json.dumps(
            {"schema_version": 1, "candidate_commit": SHA, "images": entries}
        ),
        encoding="utf-8",
    )

    (output / "api.tar").write_bytes(b"tampered")
    with pytest.raises(archive.ArchiveError, match="archive size differs|archive hash differs"):
        archive.verify_files(release, manifest, output)


def test_verify_rejects_path_escape(tmp_path: Path):
    release = release_manifest(tmp_path)
    output = tmp_path / "images"
    output.mkdir()
    manifest = tmp_path / "image-archives.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_commit": SHA,
                "images": {
                    component: {
                        "file": "../escape.tar",
                        "sha256": "0" * 64,
                        "size_bytes": 1,
                        "runtime_reference": "unused",
                        "local_image_digest": "unused",
                        "registry_digest": "unused",
                    }
                    for component in archive.COMPONENTS
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(archive.ArchiveError, match="file name is invalid"):
        archive.verify_files(release, manifest, output)
