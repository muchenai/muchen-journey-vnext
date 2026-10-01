#!/usr/bin/env bash
set -euo pipefail
phase="$1"
base="deploy/talent-demo"
revision=$(python3 -c 'import json; print(json.load(open("deploy/talent-demo/manifest.json"))["revision"])')
[[ "$revision" =~ ^[a-f0-9]{40}$ ]]
stage="/opt/talent-cloud/staging/$revision"
key="$RUNNER_TEMP/talent-deploy-key"
known="$RUNNER_TEMP/talent-known-hosts"
opts=(-i "$key" -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$known")
case "$phase" in
  transfer)
    node "$base/sealed-file.mjs" open "$base/payload.enc" "$RUNNER_TEMP/payload.tar.gz"
    python3 - "$RUNNER_TEMP" <<'PY'
import json, os, pathlib, sys, hashlib
p=pathlib.Path(sys.argv[1]); m=json.load(open('deploy/talent-demo/manifest.json'))
assert hashlib.sha256((p/'payload.tar.gz').read_bytes()).hexdigest()==m['payload_sha256']
users=json.loads(os.environ['TALENT_USERS_JSON']); assert len(users)==5
(p/'users.json').write_text(json.dumps(users)); (p/'users.json').chmod(0o600)
PY
    ssh "${opts[@]}" "root@$TALENT_HOST" "test \"\$(hostname)\" = journey-next-staging && install -d -m 0755 /opt/talent-cloud && install -d -m 0700 /opt/talent-cloud/staging '$stage'"
    scp "${opts[@]}" "$RUNNER_TEMP/payload.tar.gz" "$RUNNER_TEMP/users.json" "$base/manifest.json" "$base/remote.py" "$base/talent-cloud.service" "root@$TALENT_HOST:$stage/"
    rm -f "$RUNNER_TEMP/payload.tar.gz" "$RUNNER_TEMP/users.json"
    ;;
  route)
    python3 - <<'PYDNS'
import os, socket
assert {x[4][0] for x in socket.getaddrinfo('talent.muchenai.com', 443)} == {os.environ['TALENT_HOST']}, 'DNS must point only to the inspected Journey host before routing'
PYDNS
    ssh "${opts[@]}" "root@$TALENT_HOST" "python3 '$stage/remote.py' '$phase' '$stage'"
    ;;
  prepare|migrate|start|verify)
    ssh "${opts[@]}" "root@$TALENT_HOST" "python3 '$stage/remote.py' '$phase' '$stage'"
    ;;
  inspect)
    ssh "${opts[@]}" "root@$TALENT_HOST" 'bash -s' < "$base/inspect.sh"
    ;;
  *) exit 64 ;;
esac
