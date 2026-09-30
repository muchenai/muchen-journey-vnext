#!/usr/bin/env bash
set -euo pipefail
# Read-only inventory: do not print container environments or application records.
uname -m
free -m
df -h /
ss -ltn '( sport = :80 or sport = :443 or sport = :3187 )'
python3 - <<'PY'
import json, subprocess, pathlib
ids=subprocess.check_output(['docker','ps','-q'],text=True).split()
for cid in ids:
 d=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
 name=d['Name'].lstrip('/')
 print(json.dumps({'name':name,'image':d['Config']['Image'],'status':d['State']['Status'],
  'networks':list(d['NetworkSettings']['Networks']), 'ports':d['NetworkSettings']['Ports'],
  'mounts':[{'source':m['Source'],'destination':m['Destination'],'type':m['Type']} for m in d['Mounts']]},ensure_ascii=False))
 if 'edge' in name or 'caddy' in name:
  p=subprocess.run(['docker','exec',cid,'caddy','version'],capture_output=True,text=True)
  print('PROXY_VERSION',p.stdout.strip())
  print('PROXY_COMMAND',json.dumps({'entrypoint':d['Config']['Entrypoint'],'cmd':d['Config']['Cmd']}))
  for m in d['Mounts']:
   if m['Type']=='bind' and 'Caddyfile' in m['Destination']:
    p=pathlib.Path(m['Source'])
    if p.is_file():
     import hashlib
     print('PROXY_CONFIG_SHA256',hashlib.sha256(p.read_bytes()).hexdigest())
     for line in p.read_text().splitlines():
      s=line.strip()
      if any(x in s for x in ['reverse_proxy','admin ','import ','muchenai.com']): print('PROXY_ROUTE',s)
print('TALENT_INSTALL_EXISTS',pathlib.Path('/opt/talent-cloud').exists())
PY
curl --fail --silent --show-error --max-time 15 https://journey.muchenai.com/health/ready
