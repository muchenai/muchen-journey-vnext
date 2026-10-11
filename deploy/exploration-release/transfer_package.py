"""Bounded concurrent SCP of generated, checksummed files; no credentials in logs."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import subprocess

package = Path(os.environ["PACKAGE_DIR"])
target = os.environ["JOURNEY_HOST"]
remote = os.environ["REMOTE_PACKAGE"]
assert re.fullmatch(r"/srv/journey-next-production/canary/exploration-runs/[0-9]+-[0-9]+-activate", remote)
options = ["-i", os.environ["SSH_KEY"], "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + os.environ["SSH_KNOWN"]]

def transfer(path):
    assert path.is_file() and not path.is_symlink() and re.fullmatch(r"[A-Za-z0-9_.-]+", path.name)
    result = subprocess.run(["scp", *options, str(path), f"root@{target}:{remote}/{path.name}"], capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError("PACKAGE_TRANSFER_FAILED:" + path.name)
    print("TRANSFERRED " + path.name, flush=True)

with ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(transfer, sorted(package.iterdir())))
