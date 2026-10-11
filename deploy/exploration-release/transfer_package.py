"""Bounded transfers with immediate cancellation and credential-free progress."""
import json
import os
from pathlib import Path
import re
import subprocess
import time

class TransferError(RuntimeError):
    pass

def transfer_files(files, target, remote, options, *, parallel=3, timeout=900):
    if not re.fullmatch(r"/srv/journey-next-production/canary/exploration-runs/[0-9]+-[0-9]+-activate", remote):
        raise TransferError("INVALID_REMOTE_DIRECTORY")
    for path in files:
        if not path.is_file() or path.is_symlink() or not re.fullmatch(r"[A-Za-z0-9_.-]+", path.name):
            raise TransferError("INVALID_PACKAGE_FILE")
    pending = iter(files)
    active = []
    completed = 0
    completed_bytes = 0
    total_bytes = sum(path.stat().st_size for path in files)
    last_report = time.monotonic()
    exhausted = False
    try:
        while active or not exhausted:
            while not exhausted and len(active) < parallel:
                path = next(pending, None)
                if path is None:
                    exhausted = True
                    break
                process = subprocess.Popen(
                    ["scp", *options, str(path), f"root@{target}:{remote}/{path.name}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                active.append((process, path, time.monotonic()))
            for entry in list(active):
                process, path, started = entry
                result = process.poll()
                if result is None:
                    if time.monotonic() - started >= timeout:
                        raise TransferError("PACKAGE_TRANSFER_TIMEOUT:" + path.name)
                elif result != 0:
                    raise TransferError("PACKAGE_TRANSFER_FAILED:" + path.name)
                else:
                    active.remove(entry)
                    completed += 1
                    completed_bytes += path.stat().st_size
                    print("TRANSFERRED " + path.name, flush=True)
            now = time.monotonic()
            if now - last_report >= 30 or (exhausted and not active):
                print(json.dumps({"step": "PACKAGE_TRANSFER", "files_completed": completed,
                                  "files_total": len(files), "bytes_completed": completed_bytes,
                                  "bytes_total": total_bytes}), flush=True)
                last_report = now
            if active:
                time.sleep(1)
    finally:
        # Never wait for queued work or continue uploads after a failure.
        for process, _, _ in active:
            if process.poll() is None:
                process.kill()
            process.wait()

def main():
    package = Path(os.environ["PACKAGE_DIR"])
    options = ["-i", os.environ["SSH_KEY"], "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
               "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
               "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + os.environ["SSH_KNOWN"]]
    transfer_files(sorted(package.iterdir()), os.environ["JOURNEY_HOST"], os.environ["REMOTE_PACKAGE"], options)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"result": "STOP", "category": str(error) if isinstance(error, TransferError)
                          else type(error).__name__, "activation_started": False}), flush=True)
        raise SystemExit(1)
