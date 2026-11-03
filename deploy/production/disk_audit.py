"""Read-only disk accounting. Report sizes and deployment metadata, never file contents."""
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import urllib.request

EXPECTED_RELEASE = '2bab0cefe55447c9d64af81dd5c52f5db67db09c'
JOURNEY = Path('/srv/journey-next-production/canary')
LOCAL_FS = {'ext2','ext3','ext4','xfs','btrfs','zfs','vfat','exfat','f2fs'}
WARNINGS = []


def phase(name):
    print(json.dumps({'audit_step':name}), file=sys.stderr, flush=True)


def command(args, timeout=300):
    prefix = (['ionice','-c','3'] if shutil.which('ionice') else []) + ['nice','-n','15']
    try:
        result = subprocess.run(prefix + args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        WARNINGS.append('COMMAND_TIMEOUT:'+Path(args[0]).name)
        return b''
    if result.returncode:
        WARNINGS.append('COMMAND_PARTIAL:'+Path(args[0]).name)
    return result.stdout


def unescape_mount(value):
    return re.sub(r'\\([0-7]{3})',lambda match:chr(int(match[1],8)),value)


def local_mounts(raw):
    by_device = {}
    for line in raw.splitlines():
        left,right = line.split(' - ',1)
        fields,kind = left.split(),right.split()[0]
        target = unescape_mount(fields[4])
        if kind not in LOCAL_FS or (fields[3] != '/' and target != '/'):
            continue
        row = {'mount':target,'filesystem':kind,'device_key':fields[2]}
        prior = by_device.get(fields[2])
        if prior is None or len(target) < len(prior['mount']):
            by_device[fields[2]] = row
    return sorted(by_device.values(),key=lambda row:(row['mount']!='/',len(row['mount']),row['mount']))


def filesystem_usage(path):
    v = os.statvfs(path)
    return {'capacity_bytes':v.f_blocks*v.f_frsize, 'used_bytes':(v.f_blocks-v.f_bfree)*v.f_frsize,
        'available_bytes':max(0,v.f_bavail)*v.f_frsize,
        'reserved_free_bytes':max(0,v.f_bfree-v.f_bavail)*v.f_frsize,
        'inodes_total':v.f_files,'inodes_free':v.f_ffree}


def parse_du(raw):
    result = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        size,path = record.split(b'\t',1)
        result[os.fsdecode(path)] = int(size)
    return result


def disk_tree(path, depth=3):
    if not path.exists() or path.is_symlink():
        return {}
    return parse_du(command(['du','-x','-B1','--max-depth='+str(depth),'--null',str(path)]))


def file_accounting(root, kind):
    """Count allocated blocks once per inode; do not read the files or follow symlinks."""
    groups = {}
    errors = 0
    if not root.is_dir() or root.is_symlink():
        return {'groups':groups,'metadata_errors':errors}
    device = root.stat().st_dev
    seen = set()
    pending = [root]
    while pending:
        path = pending.pop()
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if info.st_dev != device or stat.S_ISLNK(info.st_mode):
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            pending.append(Path(entry.path))
                            continue
                        if not stat.S_ISREG(info.st_mode) or (info.st_dev,info.st_ino) in seen:
                            continue
                        seen.add((info.st_dev,info.st_ino))
                        name = entry.name
                        if kind == 'transport':
                            label = 'image_chunks' if re.fullmatch(r'(api|web)\.part[0-9]{4}',name) else \
                                'compressed_image_archives' if name in {'api.tar.gz','web.tar.gz'} else \
                                'image_tar_exports' if name.endswith('.tar') else 'other_operation_files'
                        else:
                            label = 'encrypted_database_dumps' if name.endswith('.dump.enc') else \
                                'temporary_plain_dumps' if name.endswith('.dump') else \
                                'backup_metadata' if name.endswith('.json') else 'other_backup_files'
                        group = groups.setdefault(label,{'files':0,'allocated_bytes':0,'apparent_bytes':0})
                        group['files'] += 1
                        group['allocated_bytes'] += info.st_blocks*512
                        group['apparent_bytes'] += info.st_size
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return {'groups':groups,'metadata_errors':errors}


def root_file_accounting(root):
    groups = {}
    device = root.stat().st_dev
    with os.scandir(root) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if info.st_dev != device or not stat.S_ISREG(info.st_mode):
                continue
            label = 'swap_files' if entry.name in {'swapfile','swap.img'} else 'other_root_files'
            row = groups.setdefault(label,{'files':0,'allocated_bytes':0,'apparent_bytes':0})
            row['files'] += 1
            row['allocated_bytes'] += info.st_blocks*512
            row['apparent_bytes'] += info.st_size
    return groups


class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/var/run/docker.sock')


def docker_get(path):
    assert path in {'/info','/system/df'}, 'DOCKER_READ_ENDPOINT'
    connection = DockerConnection('localhost',timeout=180)
    try:
        connection.request('GET',path)
        response = connection.getresponse()
        assert response.status == 200, 'DOCKER_READ_FAILED'
        raw = response.read(32*1024**2+1)
        assert len(raw)<=32*1024**2, 'DOCKER_RESPONSE_LIMIT'
        return json.loads(raw)
    finally:
        connection.close()


def integer(value):
    return value if isinstance(value,int) and value>=0 else None


def docker_summary(data):
    containers = data.get('Containers') or []
    used_images = {row['ImageID'] for row in containers}
    images = []
    for row in data.get('Images') or []:
        images.append({'id':row['Id'],'tags':(row.get('RepoTags') or [])[:5],
            'size_bytes':integer(row.get('Size')),'shared_bytes':integer(row.get('SharedSize')),
            'container_references':integer(row.get('Containers')),'referenced_by_container':row['Id'] in used_images,
            'created_unix':row.get('Created')})
    volumes = [{'name':row['Name'],'size_bytes':integer((row.get('UsageData') or {}).get('Size')),
        'references':integer((row.get('UsageData') or {}).get('RefCount'))} for row in data.get('Volumes') or []]
    cache = data.get('BuildCache') or []
    return {'layer_bytes_reported_by_engine':integer(data.get('LayersSize')),
        'images':sorted(images,key=lambda row:row['size_bytes'] or 0,reverse=True),
        'image_count':len(images),'unreferenced_image_count':sum(not row['referenced_by_container'] for row in images),
        'containers':[{'id':row['Id'],'names':row.get('Names',[]),'image_id':row.get('ImageID'),
            'state':row.get('State'),'writable_bytes':integer(row.get('SizeRw'))} for row in containers],
        'volumes':sorted(volumes,key=lambda row:row['size_bytes'] or 0,reverse=True),
        'build_cache_count':len(cache),'build_cache_record_bytes':sum(row.get('Size',0) for row in cache),
        'build_cache_unused_record_bytes':sum(row.get('Size',0) for row in cache if not row.get('InUse')),
        'note':'Docker logical sizes share layers and must not be added to physical directory totals.'}


def container_logs(containers):
    ids = [row['id'] for row in containers]
    assert len(ids)<=500 and all(re.fullmatch('[0-9a-f]{64}',value) for value in ids)
    if not ids:
        return []
    template = '{"id":{{json .Id}},"name":{{json .Name}},"log_path":{{json .LogPath}}}'
    raw = command(['docker','container','inspect','--format',template,*ids],timeout=90)
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        value = {'id':row['id'],'name':row['name'],'allocated_bytes':0,'apparent_bytes':0,'log_files':0}
        if row['log_path']:
            path = Path(row['log_path'])
            # Docker logs can rotate; include only this driver's exact filename and numeric rotations.
            if path.parent.is_dir() and not path.parent.is_symlink():
                for part in path.parent.iterdir():
                    if part.name != path.name and not re.fullmatch(re.escape(path.name)+r'\.[0-9]+(?:\.gz)?',part.name):
                        continue
                    info = part.lstat()
                    if stat.S_ISREG(info.st_mode):
                        value['allocated_bytes'] += info.st_blocks*512
                        value['apparent_bytes'] += info.st_size
                        value['log_files'] += 1
        rows.append(value)
    return sorted(rows,key=lambda row:row['allocated_bytes'],reverse=True)


def deleted_open_files():
    seen = set()
    groups = {}
    errors = 0
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            with os.scandir(process/'fd') as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=True)
                        if not stat.S_ISREG(info.st_mode) or info.st_nlink or (info.st_dev,info.st_ino) in seen:
                            continue
                        seen.add((info.st_dev,info.st_ino))
                        group = groups.setdefault(str(info.st_dev),{'files':0,'allocated_bytes':0,'apparent_bytes':0})
                        group['files'] += 1
                        group['allocated_bytes'] += info.st_blocks*512
                        group['apparent_bytes'] += info.st_size
                    except OSError:
                        errors += 1
        except OSError:
            errors += 1
    return {'by_device':groups,'metadata_errors':errors}


def health():
    with urllib.request.urlopen('https://journey.muchenai.com/health/ready',timeout=20) as response:
        value = json.load(response)
    assert value == {'status':'ready','release':EXPECTED_RELEASE}, 'PRODUCTION_RELEASE_CHANGED'
    return value


def main():
    assert sys.platform=='linux' and os.geteuid()==0 and socket.gethostname()=='journey-next-staging'
    before = health()
    start = dt.datetime.now(dt.timezone.utc).isoformat()
    phase('FILESYSTEM_CAPACITY_AND_DIRECTORY_SCAN')
    mounts = local_mounts(Path('/proc/self/mountinfo').read_text())
    assert any(row['mount']=='/' for row in mounts), 'LOCAL_ROOT_FILESYSTEM_REQUIRED'
    roots = []
    root_tree = {}
    for row in mounts:
        tree = disk_tree(Path(row['mount']),3 if row['mount']=='/' else 1)
        if row['mount']=='/': root_tree=tree
        roots.append({**row,**filesystem_usage(row['mount']),'stat_device':str(os.stat(row['mount']).st_dev),
            'allocated_tree_bytes':tree.get(row['mount']),
            'top_directories':sorted([{'path':path,'allocated_bytes':size} for path,size in tree.items()
                if path!=row['mount'] and Path(path).parent==Path(row['mount'])],key=lambda item:item['allocated_bytes'],reverse=True)})
    known = ['/var/lib','/var/lib/docker','/var/lib/containerd','/var/log','/var/log/journal',
        '/var/cache','/var/tmp','/var/backups','/usr/lib','/usr/local','/usr/share',
        '/srv/journey-next-production','/srv/journey-next-production/canary']
    directory_sizes = {path:root_tree[path] for path in known if path in root_tree}
    phase('DEPLOYMENT_PACKAGES_AND_DATABASE_BACKUPS')
    journey_tree = disk_tree(JOURNEY,2)
    collections = {}
    for name in ('backups','releases','exploration-runs'):
        base = JOURNEY/name
        entries = [{'directory':Path(path).name,'allocated_bytes':size}
            for path,size in journey_tree.items() if Path(path).parent==base]
        collections[name] = {'allocated_bytes':journey_tree.get(str(base)), 'directory_count':len(entries),
            'largest_directories':sorted(entries,key=lambda row:row['allocated_bytes'],reverse=True)[:20]}
    collections['backups']['file_kinds'] = file_accounting(JOURNEY/'backups','backup')
    collections['exploration-runs']['file_kinds'] = file_accounting(JOURNEY/'exploration-runs','transport')
    phase('DOCKER_STORAGE_AND_SHARED_LAYER_ACCOUNTING')
    docker = {}
    try:
        info = docker_get('/info')
        docker = docker_summary(docker_get('/system/df'))
        docker_root = Path(info['DockerRootDir'])
        assert docker_root.is_absolute() and docker_root.resolve()==docker_root, 'DOCKER_ROOT_UNSAFE'
        docker['root_directory'] = str(docker_root)
        docker['storage_driver'] = info.get('Driver')
        docker['physical_directories'] = disk_tree(docker_root,1)
        docker['containerd_physical_directories'] = disk_tree(Path('/var/lib/containerd'),2)
        docker['container_log_files'] = container_logs(docker['containers'])
    except (OSError,ValueError,KeyError,AssertionError,http.client.HTTPException) as error:
        WARNINGS.append('DOCKER_ACCOUNTING:'+type(error).__name__)
    phase('DELETED_OPEN_FILES_AND_FINAL_HEALTH')
    deleted = deleted_open_files()
    after = health()
    report = {'status':'PARTIAL' if WARNINGS else 'PASS','started_at_utc':start,
        'finished_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'measurement':'Allocated disk bytes; changing live filesystem, not a frozen snapshot.',
        'read_only':True,'production_before':before,'production_after':after,
        'filesystems':roots,'selected_directory_bytes':directory_sizes,
        'root_regular_files':root_file_accounting(Path('/')),
        'journey_allocated_bytes':journey_tree.get(str(JOURNEY)), 'journey_collections':collections,
        'docker':docker,'deleted_open_files':deleted,'warnings':WARNINGS,
        'notes':['Filesystem reserved-free bytes are unavailable to normal users, but are not used data.',
            'Directory trees and Docker logical image/cache sizes overlap; do not add them together.',
            'Database backups here are local backup files; this audit does not measure the remote RDS data volume.']}
    print(json.dumps(report,separators=(',',':')),flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status':'STOP','read_only':True,'error_type':type(error).__name__,
            'category':str(error) if re.fullmatch('[A-Z0-9_]+',str(error)) else None}),flush=True)
        raise SystemExit(1)
