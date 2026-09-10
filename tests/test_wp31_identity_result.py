import base64
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts import wp31_identity_bootstrap as bootstrap
from scripts import wp31_identity_result as delivery


ROOT = Path(__file__).resolve().parents[1]
RUN = "34429951107"
CANDIDATE = "a" * 40


@pytest.fixture(scope="module")
def keys():
    # Ephemeral test-only keys. Never load any operator/production private key.
    private = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    return private, public_pem, private_pem


def result():
    # Real UUID/token/timestamp lengths, unlike the historical tiny fixtures.
    return bootstrap.public_result({
        "operator_user_id": str(UUID(int=1)), "learner_user_id": str(UUID(int=2)),
        "owner_user_id": str(UUID(int=3)), "operator_link_id": str(UUID(int=4)),
        "operator_roles": ["OPERATOR", "REVIEWER"], "owner_roles": ["LEARNER", "REVIEWER"],
        "operator_link_start_path": delivery.LINK_PREFIX + "x" * 43,
        "operator_link_expires_at": "2026-09-10T02:38:20.123456+00:00", "expires_in_minutes": 15,
    })


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def test_real_size_result_exceeds_direct_rsa_limit_but_round_trips(keys):
    private, public_pem, private_pem = keys
    raw = encode(result())
    assert len(raw) == 508
    with pytest.raises(ValueError):
        private.public_key().encrypt(raw, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    encrypted = delivery.encrypt(raw, public_pem, RUN, CANDIDATE)
    assert delivery.decrypt(encrypted, private_pem, RUN, CANDIDATE) == raw
    assert raw not in encrypted
    assert b"link_token=" not in encrypted


def test_jwe_parts_use_standard_algorithms_and_protected_header_as_aad(keys):
    private, public_pem, _ = keys
    raw = encode(result())
    encrypted = delivery.encrypt(raw, public_pem, RUN, CANDIDATE)
    parts = encrypted.split(b".")
    # Independent decoding/decryption, not the helper's decrypt implementation.
    decoded = [base64.urlsafe_b64decode(item + b"=" * (-len(item) % 4)) for item in parts]
    header, wrapped, nonce, ciphertext, tag = decoded
    assert json.loads(header)["alg"] == "RSA-OAEP-256"
    assert json.loads(header)["enc"] == "A256GCM"
    assert [len(wrapped), len(nonce), len(tag)] == [512, 12, 16]
    key = private.decrypt(wrapped, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    assert len(key) == 32
    assert AESGCM(key).decrypt(nonce, ciphertext + tag, parts[0]) == raw


def test_fresh_key_and_nonce_for_each_encryption(keys):
    _, pem, _ = keys
    first, second = [delivery.encrypt(encode(result()), pem, RUN, CANDIDATE).split(b".") for _ in range(2)]
    assert all(first[i] != second[i] for i in (1, 2, 3, 4))


@pytest.mark.parametrize("index", range(1, 5))
def test_tampered_key_nonce_ciphertext_or_tag_is_rejected(keys, index):
    _, public_pem, private_pem = keys
    parts = delivery.encrypt(encode(result()), public_pem, RUN, CANDIDATE).split(b".")
    raw = bytearray(delivery._unb64(parts[index]))
    raw[0] ^= 1
    parts[index] = delivery._b64(bytes(raw))
    with pytest.raises((ValueError, InvalidTag)):
        delivery.decrypt(b".".join(parts), private_pem, RUN, CANDIDATE)


def test_tampered_protected_context_fails_even_when_expected_context_matches(keys):
    _, public_pem, private_pem = keys
    parts = delivery.encrypt(encode(result()), public_pem, RUN, CANDIDATE).split(b".")
    header = json.loads(delivery._unb64(parts[0]))
    header["wp31_candidate"] = "b" * 40
    parts[0] = delivery._b64(json.dumps(header, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(InvalidTag):
        delivery.decrypt(b".".join(parts), private_pem, RUN, "b" * 40)


@pytest.mark.parametrize("run,candidate", [("34429951108", CANDIDATE), (RUN, "b" * 40)])
def test_other_run_or_candidate_cannot_reuse_result(keys, run, candidate):
    _, public_pem, private_pem = keys
    encrypted = delivery.encrypt(encode(result()), public_pem, RUN, CANDIDATE)
    with pytest.raises(delivery.IdentityResultError):
        delivery.decrypt(encrypted, private_pem, run, candidate)


def test_wrong_recipient_rejected(keys):
    other = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    pem = other.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with pytest.raises(delivery.IdentityResultError):
        delivery.decrypt(delivery.encrypt(encode(result()), keys[1], RUN, CANDIDATE), pem, RUN, CANDIDATE)


@pytest.mark.parametrize("key", [rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key(), ec.generate_private_key(ec.SECP256R1()).public_key()])
def test_recipient_requires_exact_rsa4096(key):
    pem = key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(delivery.IdentityResultError):
        delivery.public_key(pem)


@pytest.mark.parametrize("field,value", [
    ("owner_roles", ["LEARNER"]), ("operator_roles", ["OPERATOR"]),
    ("operator_user_id", "short"), ("learner_user_id", str(UUID(int=1))),
    ("operator_link_start_path", "https://untrusted.example/"),
    ("operator_link_start_path", delivery.LINK_PREFIX + "short"),
    ("operator_link_expires_at", "2026-09-10T03:00:00"),
    ("expires_in_minutes", True), ("expires_in_minutes", 31),
    ("display_name", "synthetic-private-name"),
])
def test_invalid_result_never_encrypted(keys, field, value):
    payload = result()
    payload[field] = value
    with pytest.raises((ValueError, TypeError)):
        delivery.encrypt(encode(payload), keys[1], RUN, CANDIDATE)


def test_duplicate_fields_and_oversize_input_rejected(keys):
    raw = encode(result())
    for invalid in (b'{"expires_in_minutes":15,' + raw[1:], raw + b" " * 8192):
        with pytest.raises(delivery.IdentityResultError):
            delivery.encrypt(invalid, keys[1], RUN, CANDIDATE)


def test_cli_round_trip_restricted_output_and_no_values_on_stdout(keys, tmp_path, capsys):
    public, private, source, encrypted, restored = [tmp_path / name for name in ("public.pem", "test-private.pem", "source.json", "result.enc", "restored.json")]
    public.write_bytes(keys[1])
    private.write_bytes(keys[2])
    raw = encode(result())
    source.write_bytes(raw)
    common = ["--run-id", RUN, "--candidate", CANDIDATE]
    assert delivery.main(["check-key", "--public-key", str(public)]) == 0
    assert delivery.main(["encrypt", "--public-key", str(public), "--input", str(source), "--output", str(encrypted), *common]) == 0
    assert delivery.main(["decrypt", "--private-key", str(private), "--input", str(encrypted), "--output", str(restored), *common]) == 0
    assert restored.read_bytes() == raw
    if os.name != "nt":
        assert restored.stat().st_mode & 0o777 == 0o600
        assert encrypted.stat().st_mode & 0o777 == 0o600
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == "WP31_IDENTITY_RESULT=PASS operation=check-key\nWP31_IDENTITY_RESULT=PASS operation=encrypt\nWP31_IDENTITY_RESULT=PASS operation=decrypt\n"


def test_cli_failure_is_redacted_and_never_overwrites_output(keys, tmp_path, capsys):
    public, source, output = [tmp_path / name for name in ("public.pem", "source.json", "result.enc")]
    public.write_bytes(keys[1])
    source.write_bytes(encode(result()))
    output.write_bytes(b"preserve-existing-result")
    args = ["encrypt", "--public-key", str(public), "--input", str(source), "--output", str(output), "--run-id", RUN, "--candidate", CANDIDATE]
    assert delivery.main(args) == 2
    assert output.read_bytes() == b"preserve-existing-result"
    source.write_bytes(b'{"sensitive": "never-print-this"}')
    assert delivery.main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "WP31_IDENTITY_RESULT=FAIL category=RESULT_DELIVERY_REJECTED\nWP31_IDENTITY_RESULT=FAIL category=RESULT_CONTRACT_REJECTED\n"


def test_workflow_keeps_restore_validation_before_identity_and_rolls_back_delivery_failure():
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text(encoding="utf-8")
    job = workflow.split("  greenfield_canary:\n", 1)[1].split("  legacy_identity_bootstrap_disabled:\n", 1)[0]
    steps = ["Preflight identity result encryption before infrastructure access", "Initialize frozen infrastructure state read-only", "Create only the exact isolated canary database", "Execute encrypted current-production backup and isolated restore", "Deploy exact zero-worker Canary against isolated restore", "Bootstrap three controlled identities inside isolated Canary database", "Upload encrypted identity bootstrap result", "Inspect exact public and remote Canary state"]
    positions = [job.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "steps.identity_result.outcome == 'failure'" in job
    assert "steps.upload_identity_result.outcome == 'failure'" in job
    assert "cancelled() && steps.deploy.outputs.release != ''" in job
    assert "trap 'rm -f -- \"$RUNNER_TEMP/identity-result.json\"" in job
    assert '"plaintext_cleanup":"ALWAYS_STEP_REQUIRED"' in job
    assert '"plaintext_retained":false' not in job
    assert 'assert len(open(' not in workflow
    assert 'openssl pkeyutl -encrypt' not in workflow
    assert workflow.count("scripts/wp31_identity_result.py encrypt") == 2
    assert "legacy_identity_bootstrap_disabled:" in workflow
    disabled = workflow.split("  legacy_identity_bootstrap_disabled:\n", 1)[1].split("  operate:\n", 1)[0]
    assert "    if: false\n" in disabled
    assert '"$RUNNER_TEMP/wp31-identity-result.json"' in disabled.split("Always remove identity bootstrap credentials", 1)[1]
    deploy = (ROOT / "deploy/production/greenfield_canary_deploy.sh").read_text()
    assert 'cmp -s "$before" "$current_before"' in deploy
    assert 'assert after["counts"].get(table) == count' in deploy


def test_fast_deploy_proof_uses_in_run_backup_not_empty_external_input():
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text(encoding="utf-8")
    inspect = workflow.split("      - name: Inspect exact public and remote Canary state", 1)[1].split("      - name:", 1)[0]
    assert "backup_run_id='${{ inputs.backup_run_id }}'" in inspect
    assert 'if [[ \'${{ inputs.phase }}\' == greenfield-canary-fast ]]; then backup_run_id="$GITHUB_RUN_ID"; fi' in inspect
    assert '--previous-run-id "$backup_run_id"' in inspect


def test_workflow_crypto_install_extracts_complete_existing_locked_hashes():
    bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
    if not bash or not Path(bash).is_file():
        pytest.skip("Bash is required to execute the workflow dependency extraction")
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text(encoding="utf-8")
    lines = [line.strip().split(" >", 1)[0] for line in workflow.splitlines() if line.strip().startswith("awk '/^(cffi|cryptography|pycparser)")]
    assert len(lines) == 2 and lines[0] == lines[1]
    # Feed a script as Actions does; Windows command-line quoting can alter
    # embedded awk quotes when using bash -c through CreateProcess.
    actual = subprocess.run([bash], input=(lines[0] + "\n").encode(), cwd=ROOT, capture_output=True, check=True, timeout=15).stdout.decode()
    lock = (ROOT / "requirements.lock").read_text()
    expected = ""
    copying = False
    for line in lock.splitlines(keepends=True):
        if line.startswith(("cffi==", "cryptography==", "pycparser==")):
            copying = True
        if copying:
            expected += line
            if not line.rstrip().endswith(chr(92)):
                copying = False
    assert actual == expected
    assert "--hash=sha256:" in actual
    assert "--require-hashes --only-binary=:all:" in workflow


def test_partial_write_failure_removes_only_new_output(tmp_path, monkeypatch):
    output = tmp_path / "partial.enc"
    real_fdopen = os.fdopen

    class BrokenWriter:
        def __init__(self, descriptor, mode):
            self.stream = real_fdopen(descriptor, mode)

        def __enter__(self):
            return self

        def write(self, data):
            self.stream.write(data[:2])
            raise OSError("synthetic-write-failure")

        def __exit__(self, *_):
            self.stream.close()

    monkeypatch.setattr(delivery.os, "fdopen", BrokenWriter)
    with pytest.raises(OSError):
        delivery._write_new(output, b"synthetic-ciphertext")
    assert not output.exists()
