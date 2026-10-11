"""Build a bounded SSH stdin program; execute the guarded operation in live API."""
import json
from pathlib import Path

HOST_PROGRAM = '''
import json, socket, subprocess
from pathlib import Path
if socket.gethostname() != "journey-next-staging":
    raise RuntimeError("HOST_MISMATCH")
root = Path("/srv/journey-next-production/canary")
expected = root / "releases/9e24e64a6b35509da1f28a0dd0e4f8f2131c7399-exploration"
if (root / "current").resolve(strict=True) != expected:
    raise RuntimeError("RELEASE_PATH_MISMATCH")
result = subprocess.run(["docker", "ps", "-q", "--filter",
    "label=com.docker.compose.project=journey-next-greenfield-canary", "--filter",
    "label=com.docker.compose.service=api"], text=True, capture_output=True, check=True)
ids = result.stdout.split()
if len(ids) != 1:
    raise RuntimeError("API_CONTAINER_COUNT_MISMATCH")
result = subprocess.run(["docker", "exec", "-i", ids[0], "python", "-"],
    input=PAYLOAD, text=True, capture_output=True, timeout=120)
if result.returncode:
    # Avoid SQL parameter / identity disclosure in public workflow logs.
    errors = [line for line in result.stderr.splitlines() if line.startswith("RuntimeError:")]
    raise RuntimeError(errors[-1] if errors else "RETEST_TRANSACTION_FAILED")
receipt = json.loads(result.stdout)
if receipt.get("result") not in ("APPLIED", "ALREADY_APPLIED"):
    raise RuntimeError("RETEST_RECEIPT_INVALID")
print(json.dumps(receipt))
'''

if __name__ == "__main__":
    payload = Path(__file__).with_name("owner_retest.py").read_text(encoding="utf-8")
    print("PAYLOAD = " + repr(payload))
    print(HOST_PROGRAM)
