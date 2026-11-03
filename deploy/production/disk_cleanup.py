"""Scoped production cleanup: verified transports, retired app images, proven scratch volumes."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import time

from disk_audit import EXPECTED_RELEASE, health

ROOT = Path('/srv/journey-next-production/canary')
IMAGE_ID = re.compile(r'sha256:[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')
APP_REF = re.compile(r'ghcr\.io/(?:muchenai|muchenai2024-creator)/muchen-journey-vnext-(?:api|web|worker)(?::[A-Za-z0-9_.-]+|@sha256:[0-9a-f]{64})')
SOURCES = {'https://github.com/muchenai/muchen-journey-vnext','https://github.com/muchenai2024-creator/muchen-journey-vnext'}


def event(**values):
    print(json.dumps(values,separators=(',',':')),flush=True)


def read_json(path):
    assert path.is_file() and not path.is_symlink() and path.resolve()==path, 'UNSAFE_METADATA_PATH'
    assert path.stat().st_size<=2_000_000, 'METADATA_SIZE'
    return json.loads(path.read_text())


def run(args, timeout=120):
    return subprocess.run(args,capture_output=True,timeout=timeout)


def checked(args, timeout=120):
    result = run(args,timeout)
    assert result.returncode==0, 'DOCKER_METADATA_FAILED'
    return result.stdout


def image_info(reference, *, optional=False):
    assert IMAGE_ID.fullmatch(reference) or re.fullmatch(r'ghcr\.io/[A-Za-z0-9_./:@-]+',reference), 'IMAGE_REFERENCE'
    # New Docker API versions omit empty legacy fields such as Parent. Parse
    # the document locally and retain only the deployment metadata we need.
    # Never log or return Config.Env or other image configuration values.
    result = run(['docker','image','inspect',reference])
    if optional and result.returncode and any(token in result.stderr.lower() for token in (b'no such image',b'not found')):
        return None
    assert result.returncode==0, 'IMAGE_INSPECTION_FAILED'
    rows = json.loads(result.stdout)
    assert len(rows)==1, 'IMAGE_INSPECTION_COUNT'
    row = rows[0]
    labels = (row.get('Config') or {}).get('Labels') or {}
    value = {'id':row['Id'],'tags':row.get('RepoTags') or [],'digests':row.get('RepoDigests') or [],
        'created':row['Created'],'parent':row.get('Parent') or '',
        'revision':labels.get('org.opencontainers.image.revision',''),
        'source':labels.get('org.opencontainers.image.source','').rstrip('/')}
    assert IMAGE_ID.fullmatch(value['id']), 'IMAGE_ID'
    value['refs'] = sorted(set((value['tags'] or [])+(value['digests'] or [])))
    return value


def containers():
    ids = checked(['docker','container','ls','-aq','--no-trunc']).decode().split()
    assert len(ids)<=500 and all(re.fullmatch('[0-9a-f]{64}',value) for value in ids), 'CONTAINER_IDS'
    if not ids:
        return []
    template = '{"id":{{json .Id}},"image":{{json .Image}},"name":{{json .Name}},"state":{{json .State.Status}}}'
    return [json.loads(line) for line in checked(['docker','container','inspect','--format',template,*ids]).splitlines()]


def metadata_inventory(root):
    assert root.is_dir() and not root.is_symlink() and root.resolve()==root
    result = {}
    for path in root.rglob('*'):
        assert not path.is_symlink(), 'PROTECTED_TREE_SYMLINK'
        info = path.lstat()
        if stat.S_ISREG(info.st_mode):
            assert len(result)<50000, 'PROTECTED_FILE_LIMIT'
            result[str(path.relative_to(root))] = (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,stat.S_IMODE(info.st_mode))
    return result


def unchanged(before, root):
    after = metadata_inventory(root)
    assert all(after.get(name)==value for name,value in before.items()), 'PROTECTED_FILES_CHANGED'


def scope_check(scope):
    assert scope['schema']==1 and scope['expected_release']==EXPECTED_RELEASE
    assert scope['keep_release_chain']==[
        EXPECTED_RELEASE,'1b4e1bd6d2aa8f9598490841958bf55b42432e72','69c98991a0dcc9e4929f1eb6d618920909ed72f3'], 'ROLLBACK_CHAIN_CHANGED'
    assert scope['audit_run']=='41636371891' and re.fullmatch('[0-9a-f]{64}',scope['audit_sha256'])
    ids = [row['id'] for row in scope['candidate_images']]
    assert len(ids)==len(set(ids)) and len(ids)<=200 and all(IMAGE_ID.fullmatch(value) for value in ids), 'IMAGE_SCOPE'
    names = [row['name'] for row in scope['candidate_volumes']]
    assert len(names)==len(set(names)) and len(names)<=50 and all(re.fullmatch('[A-Za-z0-9_.-]{1,200}',name) for name in names), 'VOLUME_SCOPE'
    assert scope['maximum_transport_bytes']==8*1024**3, 'TRANSPORT_BOUND'


def successful_releases():
    result = {}
    for path in (ROOT/'releases').iterdir():
        if path.is_symlink() or not path.is_dir() or path.resolve()!=path:
            continue
        receipt = path/'activation-receipt.json'
        if receipt.is_file() and not receipt.is_symlink():
            value = read_json(receipt)
            if value.get('status')=='PASS' and COMMIT.fullmatch(value.get('release','')):
                result[value['release']] = path
    return result


def retained_images(scope, current):
    path = current
    keep = {}
    oldest_created = []
    for index, candidate in enumerate(scope['keep_release_chain']):
        assert path.parent==ROOT/'releases' and path.resolve()==path, 'RELEASE_PATH'
        receipt = read_json(path/'activation-receipt.json')
        prepared = read_json(path/'schema-upgrade-prepared.json')['manifest']
        assert receipt['status']=='PASS' and receipt['release']==candidate and prepared['candidate']==candidate, 'RELEASE_RECEIPT'
        for service, reference in prepared['images'].items():
            image = image_info(reference)
            if service in {'api','web'}:
                assert image['revision']==candidate, 'ROLLBACK_IMAGE_REVISION'
                if index==len(scope['keep_release_chain'])-1:
                    oldest_created.append(dt.datetime.fromisoformat(image['created'].replace('Z','+00:00')).timestamp())
            keep[image['id']] = image
        if index<len(scope['keep_release_chain'])-1:
            path = Path(prepared['base_release'])
    assert len(oldest_created)==2, 'ROLLBACK_BOUNDARY'
    for row in containers():
        keep[row['image']] = image_info(row['image'])
    pending = list(keep.values())
    while pending:
        parent = pending.pop().get('parent')
        if parent and parent not in keep:
            assert IMAGE_ID.fullmatch(parent), 'PARENT_IMAGE_ID'
            value = image_info(parent)
            keep[parent] = value
            pending.append(value)
    return keep,min(oldest_created)


def image_eligible(image, protected, revisions, cutoff, referenced):
    if image['id'] in protected or image['id'] in referenced:
        return False
    if not COMMIT.fullmatch(image['revision']) or image['revision'] in revisions or image['source'] not in SOURCES:
        return False
    if not image['refs'] or not all(APP_REF.fullmatch(ref) for ref in image['refs']):
        return False
    for reference in image['refs']:
        if '@sha256:' not in reference:
            tag = reference.rsplit(':',1)[1]
            if not COMMIT.fullmatch(tag) and not re.fullmatch(r'schema-upgrade-[0-9a-f]{40}-[0-9]+-[0-9]+',tag):
                return False
    if any(candidate in reference for candidate in revisions for reference in image['refs']):
        return False
    created = dt.datetime.fromisoformat(image['created'].replace('Z','+00:00'))
    return created.utcoffset() is not None and created.timestamp()<cutoff


def transport_plan(successful):
    root = ROOT/'exploration-runs'
    assert root.resolve()==root and root.is_dir() and not root.is_symlink()
    plan = []
    preserved = []
    for package in sorted(root.iterdir()):
        if package.is_symlink() or not package.is_dir() or package.resolve()!=package or not re.fullmatch('[0-9]+-[0-9]+-activate',package.name):
            continue
        manifest_path = package/'manifest.json'
        if not manifest_path.is_file() or manifest_path.is_symlink():
            continue
        manifest = read_json(manifest_path)
        if manifest.get('candidate') not in successful or set(manifest.get('archives',{}))!={'api','web'}:
            continue
        package_plan = []
        try:
            for kind in ('api','web'):
                archive = manifest['archives'][kind]
                parts = archive['chunks']
                assert 0<len(parts)<=1000 and len({part['file'] for part in parts})==len(parts)
                assert all(re.fullmatch(kind+r'\.part[0-9]{4}',part['file']) for part in parts)
                rows = [(part['file'],part['sha256'],64*1024**2) for part in parts]
                rows.append((kind+'.tar.gz',archive['gzip_sha256'],2*1024**3))
                for name, expected, limit in rows:
                    assert re.fullmatch('[0-9a-f]{64}',expected)
                    path = package/name
                    assert not path.is_symlink(), 'TRANSPORT_SYMLINK'
                    if not path.exists():
                        continue
                    assert path.is_file() and path.resolve().parent==package and 0<path.stat().st_size<=limit
                    with path.open('rb') as handle:
                        actual = hashlib.file_digest(handle,'sha256').hexdigest()
                    if actual!=expected:
                        preserved.append({'file':str(path.relative_to(ROOT)),'reason':'HASH_MISMATCH'})
                        continue
                    info = path.stat()
                    package_plan.append({'file':str(path.relative_to(ROOT)),'sha256':expected,'size':info.st_size,
                        'inode':info.st_ino,'device':info.st_dev,'mtime_ns':info.st_mtime_ns})
        except (AssertionError,KeyError,TypeError):
            preserved.append({'package':package.name,'reason':'MANIFEST_NOT_ELIGIBLE'})
            continue
        plan.extend(package_plan)
    return plan,preserved


def remove_transport(row):
    relative = Path(row['file'])
    assert not relative.is_absolute() and len(relative.parts)==3 and relative.parts[0]=='exploration-runs'
    assert re.fullmatch('[0-9]+-[0-9]+-activate',relative.parts[1])
    assert re.fullmatch(r'(api|web)(\.part[0-9]{4}|\.tar\.gz)',relative.name), 'TRANSPORT_NAME'
    path = ROOT/relative
    assert path.resolve()==path and path.is_file() and not path.is_symlink(), 'TRANSPORT_PATH_CHANGED'
    info = path.stat()
    assert (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)==(row['device'],row['inode'],row['size'],row['mtime_ns']), 'TRANSPORT_CHANGED'
    with path.open('rb') as handle:
        assert hashlib.file_digest(handle,'sha256').hexdigest()==row['sha256'], 'TRANSPORT_HASH_CHANGED'
    path.unlink()


def volume_info(name):
    assert re.fullmatch('[A-Za-z0-9_.-]{1,200}',name), 'VOLUME_NAME'
    raw = run(['docker','volume','inspect',name])
    return json.loads(raw.stdout)[0] if raw.returncode==0 else None


def volume_eligible(volume, successful, references):
    name = volume['Name']
    labels = volume.get('Labels') or {}
    if references or not re.fullmatch('[0-9a-f]{64}',name) or volume.get('Driver')!='local' or volume.get('Options'):
        return False
    return labels.get('journey.operation') in {'restore-probe','schema-restore','backup-restore'} and labels.get('journey.candidate') in successful


def volume_references(name):
    return checked(['docker','container','ls','-aq','--filter','volume='+name]).decode().split()


def main():
    assert sys.platform=='linux' and os.geteuid()==0 and socket.gethostname()=='journey-next-staging'
    assert ROOT.resolve()==ROOT and Path(__file__).resolve().parent.parent==ROOT/'exploration-runs'
    scope = read_json(Path(__file__).resolve().with_name('disk-cleanup-scope-20261103.json'))
    scope_check(scope)
    import fcntl
    fd = os.open(ROOT/'.schema-upgrade.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before_health = health()
        current = (ROOT/'current').resolve()
        assert (ROOT/'current').is_symlink() and current==ROOT/'releases'/(EXPECTED_RELEASE+'-badges-knowledge'), 'CURRENT_RELEASE_CHANGED'
        services_before = containers()
        assert services_before and all(row['state']=='running' for row in services_before), 'SERVICE_NOT_RUNNING'
        backups_before = metadata_inventory(ROOT/'backups')
        releases_before = metadata_inventory(ROOT/'releases')
        protected,cutoff = retained_images(scope,current)
        successful = successful_releases()
        files,preserved_files = transport_plan(successful)
        assert len(files)<=4000 and sum(row['size'] for row in files)<=scope['maximum_transport_bytes'], 'TRANSPORT_SCOPE_LIMIT'
        image_plan = []
        preserved_images = []
        referenced = {row['image'] for row in services_before}
        for row in scope['candidate_images']:
            image = image_info(row['id'],optional=True)
            if image and image_eligible(image,protected,scope['keep_release_chain'],cutoff,referenced):
                image_plan.append({'id':image['id'],'revision':image['revision'],'refs':image['refs']})
            else:
                preserved_images.append(row['id'])
        volume_plan = []
        preserved_volumes = []
        for row in scope['candidate_volumes']:
            volume = volume_info(row['name'])
            if volume and volume_eligible(volume,successful,volume_references(row['name'])):
                volume_plan.append({'name':row['name'],'labels':{key:volume['Labels'][key]
                    for key in ('journey.operation','journey.candidate')}})
            else:
                preserved_volumes.append({'name':row['name'],'reason':'NO_VERIFIED_SCRATCH_PROVENANCE_OR_REFERENCED'})
        plan = {'kind':'cleanup_plan','source_audit':scope['audit_run'],'protected_releases':scope['keep_release_chain'],
            'protected_image_ids':sorted(protected),'transport_files':files,'preserved_transports':preserved_files,
            'images':image_plan,'preserved_image_ids':preserved_images,'volumes':volume_plan,'preserved_volumes':preserved_volumes}
        plan_raw = json.dumps(plan,sort_keys=True,separators=(',',':')).encode()
        plan_path = Path(__file__).with_name('cleanup-plan.json')
        with plan_path.open('xb') as handle: handle.write(plan_raw)
        free_before = shutil.disk_usage(ROOT).free
        event(step='VERIFIED_CLEANUP_PLAN',transport_files=len(files),transport_bytes=sum(row['size'] for row in files),
            images=len(image_plan),proven_temporary_volumes=len(volume_plan),preserved_volumes=len(preserved_volumes),
            protected_images=len(protected),plan_sha256=hashlib.sha256(plan_raw).hexdigest(),disk_free_bytes=free_before)
        for row in files:
            remove_transport(row)
        event(step='TRANSPORT_CLEANUP_COMPLETE',files=len(files),disk_free_bytes=shutil.disk_usage(ROOT).free)
        removed_images = []
        retained_on_recheck = []
        for index,row in enumerate(image_plan):
            assert (ROOT/'current').resolve()==current, 'CURRENT_CHANGED_DURING_CLEANUP'
            live_ids = {container['image'] for container in containers()}
            image = image_info(row['id'],optional=True)
            if not image:
                removed_images.append(row['id'])
                continue
            if not image_eligible(image,protected,scope['keep_release_chain'],cutoff,live_ids) or image['refs']!=row['refs']:
                retained_on_recheck.append(row['id'])
                continue
            for reference in row['refs']:
                latest = image_info(reference,optional=True)
                if not latest:
                    continue
                assert latest['id']==row['id'], 'IMAGE_REFERENCE_MOVED'
                if row['id'] in {container['image'] for container in containers()}:
                    break
                result = run(['docker','image','rm','--no-prune',reference],timeout=180)
                if result.returncode:
                    event(step='IMAGE_PRESERVED_BY_DOCKER',id=row['id'])
                    break
            latest = image_info(row['id'],optional=True)
            if latest and not latest['refs'] and row['id'] not in {container['image'] for container in containers()}:
                run(['docker','image','rm','--no-prune',row['id']],timeout=180)
            if image_info(row['id'],optional=True) is None:
                removed_images.append(row['id'])
            else:
                retained_on_recheck.append(row['id'])
            if (index+1)%20==0:
                health()
                event(step='IMAGE_CLEANUP_PROGRESS',processed=index+1,removed=len(removed_images),disk_free_bytes=shutil.disk_usage(ROOT).free)
        removed_volumes = []
        for row in volume_plan:
            volume = volume_info(row['name'])
            if volume and all((volume.get('Labels') or {}).get(key)==value for key,value in row['labels'].items()) and volume_eligible(volume,successful,volume_references(row['name'])):
                result = run(['docker','volume','rm',row['name']])
                if result.returncode==0:
                    removed_volumes.append(row['name'])
                else:
                    preserved_volumes.append({'name':row['name'],'reason':'PRESERVED_BY_DOCKER'})
            elif volume:
                preserved_volumes.append({'name':row['name'],'reason':'PROVENANCE_OR_REFERENCE_CHANGED'})
        unchanged(backups_before,ROOT/'backups')
        unchanged(releases_before,ROOT/'releases')
        assert (ROOT/'current').resolve()==current, 'CURRENT_CHANGED'
        after = {row['id']:row for row in containers()}
        assert all(after.get(row['id'])==row for row in services_before), 'SERVICE_CHANGED'
        for image_id in protected:
            assert image_info(image_id)['id']==image_id, 'PROTECTED_IMAGE_MISSING'
        after_health = health()
        time.sleep(3)
        receipt = {'status':'PASS','application_release':EXPECTED_RELEASE,'services_restarted':0,
            'backups_preserved':True,'release_files_preserved':True,'protected_releases':scope['keep_release_chain'],
            'transport_files_removed':len(files),'transport_bytes_removed':sum(row['size'] for row in files),
            'images_removed':len(removed_images),'image_ids_removed':removed_images,'images_preserved_on_recheck':retained_on_recheck,
            'volumes_removed':len(removed_volumes),'volume_names_removed':removed_volumes,'volume_names_preserved':preserved_volumes,
            'preserved_transports':preserved_files,'disk_free_before_bytes':free_before,'disk_free_after_bytes':shutil.disk_usage(ROOT).free,
            'health_before':before_health,'health_after':after_health,'finished_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'plan_sha256':hashlib.sha256(plan_raw).hexdigest()}
        with Path(__file__).with_name('cleanup-receipt.json').open('x') as handle: json.dump(receipt,handle,separators=(',',':'))
        event(**receipt)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        event(status='STOP',error_type=type(error).__name__,
            category=str(error) if re.fullmatch('[A-Z0-9_]+',str(error)) else None,do_not_retry_blindly=True)
        raise SystemExit(1)
