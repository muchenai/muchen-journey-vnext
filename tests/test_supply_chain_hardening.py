from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON_RUNTIME = (
    "python:3.14.6-alpine@sha256:"
    "26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92"
)
RUNTIME_DOCKERFILES = (
    "apps/api/Dockerfile",
    "apps/worker/Dockerfile",
    "apps/web/Dockerfile",
)
OPENSSL_PACKAGE_SHA256 = {
    "amd64": (
        "x86_64",
        "161223a16f042b8e469e9441291e071464fd91d4f4bbe6f496ee8d0abd4e0701",
        "aca521e5ae4a321322a9d47ed64a1775f5ab1ffd215d1e9fc0433c58f7bfd037",
        "e18c561e6a8fb744b42fe000f4a8cdfcc38e7956e62a6ab44b0a0580db948450",
    ),
    "arm64": (
        "aarch64",
        "35b892813c23664a3592e4fc8c12a03538a22c579057655361c7043305272a9a",
        "d6ec970cc10e01539e41626f720c4e0ac69016eaa2079a10ef776ffd3243db5b",
        "0d12f4f145ec045dd19e8465bd3cb07b08197f96a3776641511dc2bec53cc0b7",
    ),
}


def test_runtime_openssl_packages_follow_target_arch_contract() -> None:
    for relative in RUNTIME_DOCKERFILES:
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "ARG TARGETARCH" in content
        assert 'case "${TARGETARCH}" in' in content
        for target_arch, (alpine_arch, *package_hashes) in OPENSSL_PACKAGE_SHA256.items():
            branch = next(
                line for line in content.splitlines() if f"{target_arch})" in line
            )
            assert f"alpine_arch={alpine_arch}" in branch
            for package_hash in package_hashes:
                assert package_hash in branch
        assert 'Unsupported TARGETARCH: ${TARGETARCH}' in content
        assert "main/${alpine_arch}" in content
        assert "sha256sum -c -" in content
        assert "apk add --no-network" in content


def test_python_runtime_images_use_the_reviewed_digest_and_non_root_user() -> None:
    for relative in ("apps/api/Dockerfile", "apps/worker/Dockerfile"):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert content.splitlines()[0] == f"FROM {PYTHON_RUNTIME}"
        assert "adduser -S -D -H -u 10001 -G journey journey" in content
        assert "USER journey" in content
        assert "python:3.14.6-slim" not in content
        assert "sha256sum -c -" in content
        assert "openssl-3.5.8-r0.apk" in content
        assert "apk add --no-network" in content
        assert content.index("RUN python -m pip install --require-hashes") < content.index(
            "ARG VCS_REF=local"
        )

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert f"WP07_PYTHON_IMAGE := {PYTHON_RUNTIME}" in makefile
    assert "pip_audit --progress-spinner=off --no-deps --disable-pip" in makefile


def test_web_runtime_removes_package_manager_toolchain_before_non_root_user() -> None:
    content = (ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
    runtime = content.split(" AS runtime\n", 1)[1]
    assert "sha256sum -c -" in runtime
    assert "openssl-3.5.8-r0.apk" in runtime
    assert "apk add --no-network" in runtime
    removal = runtime.index("RUN rm -rf /usr/local/lib/node_modules/npm")
    user = runtime.index("USER nextjs")
    assert removal < user
    assert "/usr/local/bin/npm" in runtime
    assert "/usr/local/bin/npx" in runtime


def test_python_runtime_dependency_graph_is_hash_locked() -> None:
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    build_lock = (ROOT / "requirements-build.lock").read_text(encoding="utf-8")
    requirement_blocks: list[str] = []
    current: list[str] = []
    for line in lock.splitlines():
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        if not line.startswith((" ", "\t")):
            if current:
                requirement_blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        requirement_blocks.append("\n".join(current))

    assert requirement_blocks
    assert all("==" in block for block in requirement_blocks)
    assert all("--hash=sha256:" in block for block in requirement_blocks)
    assert "file://" not in lock
    assert "-e " not in lock
    assert "setuptools==" in build_lock
    assert "wheel==" in build_lock
    assert "packaging==" in build_lock
    assert build_lock.count("--hash=sha256:") >= 3

    for relative in ("apps/api/Dockerfile", "apps/worker/Dockerfile"):
        content = (ROOT / relative).read_text(encoding="utf-8")
        assert "python -m pip install --require-hashes -r requirements-build.lock" in content
        assert "--require-hashes --no-build-isolation -r requirements.lock" in content
        assert "python -m pip install --upgrade pip" not in content
        assert "python -m pip install --no-deps ." not in content
        assert "PYTHONPATH=/app/apps/api:/app/apps/worker" in content
