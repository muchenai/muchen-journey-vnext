"""Read-only space gates before transfer, image import and isolated DB restore."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

ROOT = Path('/srv/journey-next-production/canary')
GIB = 1024**3


class DiskSpaceError(RuntimeError):
    """A safe, actionable stage name for the release progress log."""


def disk_budget(transport_bytes, tar_bytes, largest_gzip):
    assert all(isinstance(n, int) and 0 < n <= 32*GIB for n in (transport_bytes, tar_bytes, largest_gzip))
    # Accommodate image layers and containerd unpacking, one assembled gzip,
    # plus a reserve. Export verification is streamed, never written as a tar.
    importing = 2*tar_bytes + largest_gzip + 2*GIB
    return {'transfer': transport_bytes + importing, 'import': importing}


def check_space(stage, required, *, roots=None):
    assert stage in {'TRANSFER', 'IMPORT', 'RESTORE'}
    assert isinstance(required, int) and 0 < required <= 100*GIB
    if roots is None:
        assert sys.platform == 'linux' and os.geteuid() == 0
        assert socket.gethostname() == 'journey-next-staging' and ROOT.resolve() == ROOT
        result = subprocess.run(['docker', 'info', '--format', '{{.DockerRootDir}}'],
                                capture_output=True, text=True, timeout=30, check=True)
        docker_root = Path(result.stdout.strip())
        assert docker_root.is_absolute() and docker_root.is_dir()
        roots = (ROOT, docker_root)
    facts = []
    for root in {Path(item).resolve() for item in roots}:
        free = shutil.disk_usage(root).free
        facts.append({'path': str(root), 'free_bytes': free})
    print(json.dumps({'step': 'DISK_SPACE_' + stage, 'required_bytes': required, 'filesystems': facts}), flush=True)
    if any(row['free_bytes'] < required for row in facts):
        raise DiskSpaceError('INSUFFICIENT_DISK_SPACE_' + stage)


if __name__ == '__main__':
    assert len(sys.argv) == 3 and sys.argv[1] == 'TRANSFER' and sys.argv[2].isdigit()
    check_space('TRANSFER', int(sys.argv[2]))
