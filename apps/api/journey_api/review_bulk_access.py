"""Preview-bound, additive-only administrator grants. Never downgrade/reactivate."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from journey_api.auth import Actor, get_actor
from journey_api.config import get_settings
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.department_directory import DepartmentDirectory
from journey_api.models import ExternalIdentity, Organization, Role, RoleAssignment, User, UserStatus
from journey_api.review_admin_access import require_super, access_for, STAFF_ROLES
from journey_api.review_admin_models import ReviewAdminAccess
from journey_api.review_admin_routes import directory_for, directory_subject, envelope, audit, DOMAINS

router = APIRouter(prefix='/api/v1/review-admin/bulk')


class Rule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    department_id: str = Field(min_length=1, max_length=180)
    mode: Literal['all', 'title']
    domain: str = '产品开发'
    level: Literal['初级', '中级', '高级'] = '初级'


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rules: list[Rule] = Field(min_length=1, max_length=100)


class Apply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_token: str = Field(min_length=1, max_length=2000000)
    open_ids: list[str] = Field(min_length=1, max_length=20)
    confirmed: Literal[True]
    choices: dict[str, str] = Field(default_factory=dict, max_length=20)


def fingerprint(profile):
    value = {'departments': sorted(profile['department_ids']), 'title': profile['job_title']}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def sign(payload):
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()
    secret = get_settings().identity_subject_secret.encode()
    return body + '.' + hmac.new(secret, ('review-bulk-v1:' + body).encode(), hashlib.sha256).hexdigest()


def verify(token, actor):
    try:
        body, signature = token.rsplit('.', 1)
        secret = get_settings().identity_subject_secret.encode()
        expected = hmac.new(secret, ('review-bulk-v1:' + body).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(body))
        if payload.get('version') != 2 or payload['actor'] != str(actor.id) or payload['org'] != str(actor.organization_id) or payload['expires'] < time.time():
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError):
        raise ApiError(409, 'PREVIEW_EXPIRED', '名单预览已失效，请重新预览后确认。')


def current_access(session, actor, open_id, *, lock=False):
    identity = session.scalar(select(ExternalIdentity).where(ExternalIdentity.provider == 'FEISHU', ExternalIdentity.subject == directory_subject(open_id)))
    if not identity:
        return None, 'new', '未开通'
    if identity.organization_id != actor.organization_id or identity.revoked_at:
        return None, 'unavailable', '身份绑定不可用'
    user = session.get(User, identity.user_id)
    if user.status != UserStatus.ACTIVE:
        return user, 'unavailable', '账号已停用'
    row = access_for(session, user.id, actor.organization_id)
    if row and row.access_role == 'super_admin':
        return user, 'super', '超级管理员，跳过'
    if row and row.revoked_at:
        return user, 'revoked', '权限已撤销，保持不变'
    if row:
        return user, 'existing', '普通管理员 · ' + row.level + '，保持不变'
    legacy = session.scalar(select(RoleAssignment.id).where(RoleAssignment.user_id == user.id,
        RoleAssignment.organization_id == actor.organization_id, RoleAssignment.role.in_(STAFF_ROLES)).limit(1))
    if legacy:
        return user, 'existing', '已有管理权限，保持不变'
    if lock:
        # Existing staff (including another active operator) are never mutation
        # targets. Lock only an ungranted user after the organization grant lock.
        session.scalar(select(User.id).where(User.id == user.id).with_for_update())
        session.refresh(user)
        if user.status != UserStatus.ACTIVE:
            return user, 'unavailable', '账号已停用'
    return user, 'new', '未开通'


def preview_access(session, actor, open_ids):
    """Two set-based queries instead of several queries for each employee."""
    subjects = {directory_subject(oid): oid for oid in open_ids}
    result = {oid: ('new', '未开通') for oid in open_ids}
    if not subjects:
        return result
    rows = session.execute(select(ExternalIdentity, User, ReviewAdminAccess)
        .outerjoin(User, User.id == ExternalIdentity.user_id)
        .outerjoin(ReviewAdminAccess, (ReviewAdminAccess.user_id == User.id) &
                   (ReviewAdminAccess.organization_id == actor.organization_id))
        .where(ExternalIdentity.provider == 'FEISHU', ExternalIdentity.subject.in_(subjects))).all()
    user_ids = {identity.user_id for identity, _, _ in rows if identity.organization_id == actor.organization_id}
    legacy = set(session.scalars(select(RoleAssignment.user_id).where(
        RoleAssignment.organization_id == actor.organization_id, RoleAssignment.user_id.in_(user_ids),
        RoleAssignment.role.in_(STAFF_ROLES))).all()) if user_ids else set()
    for identity, user, row in rows:
        if identity.organization_id != actor.organization_id or identity.revoked_at:
            status = ('unavailable', '身份绑定不可用')
        elif not user or user.status != UserStatus.ACTIVE:
            status = ('unavailable', '账号已停用')
        elif row and row.access_role == 'super_admin':
            status = ('super', '超级管理员，跳过')
        elif row and row.revoked_at:
            status = ('revoked', '权限已撤销，保持不变')
        elif row:
            status = ('existing', '普通管理员 · ' + row.level + '，保持不变')
        elif user.id in legacy:
            status = ('existing', '已有管理权限，保持不变')
        else:
            status = ('new', '未开通')
        result[subjects[identity.subject]] = status
    return result


@router.get('/departments')
def departments(request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_super(session, actor)
    snapshot = DepartmentDirectory(directory_for(actor)).preview_snapshot(include_people=False)
    return envelope(request, {'items': [d for d in snapshot['tree'] if d['parent_id'] == '0'],
                              'directory': snapshot['directory']})


def options_for(person, tree, rules):
    """Only matching root rules contribute options; equal grants collapse to one."""
    paths = {d['id']: d['path_ids'] for d in tree}
    names = {d['id']: d['name'] for d in tree}
    options = {}
    for rule in rules:
        belongs = any(rule['department_id'] in paths.get(d, []) for d in person['department_ids'])
        title_matches = any(word in person['job_title'] for word in ('经理', '助理'))
        if belongs and (rule['mode'] == 'all' or title_matches):
            key = (rule['domain'], rule['level'])
            if key not in options:
                options[key] = {k: rule[k] for k in ('department_id', 'domain', 'level')}
                options[key]['department_name'] = names[rule['department_id']]
    return list(options.values())


def validate_rules(tree, rules):
    roots = {d['id'] for d in tree if d['parent_id'] == '0'}
    ids = [r['department_id'] for r in rules]
    if len(ids) != len(set(ids)) or any(i not in roots for i in ids):
        raise ApiError(409, 'DEPARTMENT_CHANGED', '请选择不重复的一级部门，并重新预览。')


@router.post('/preview')
def preview(command: Preview, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_super(session, actor)
    if any(rule.domain not in DOMAINS for rule in command.rules):
        raise ApiError(422, 'VALIDATION_FAILED', '请选择有效专业方向。')
    directory = DepartmentDirectory(directory_for(actor))
    snapshot = directory.preview_snapshot()
    tree = snapshot['tree']
    rules = [r.model_dump() for r in command.rules]
    validate_rules(tree, rules)
    expanded = directory.expanded(tree, rules)
    people = [p for p in snapshot['people'] if any(d in expanded for d in p['department_ids'])]
    if len(people) > 5000:
        raise ApiError(503, 'DIRECTORY_INCOMPLETE', '人员过多，请缩小部门范围后预览。')
    access = preview_access(session, actor, [p['open_id'] for p in people])
    items, approved = [], {}
    for person in people:
        status, current = access[person['open_id']]
        options = options_for(person, tree, rules)
        if status == 'new' and not options:
            status = 'missing_title' if not person['job_title'] else 'not_matched'
        if status == 'new':
            approved[person['open_id']] = {'fingerprint': fingerprint(person), 'options': options}
            if len(options) > 1:
                status = 'conflict'
        target = options[0] if status == 'new' else None
        action = ('新增普通管理员 · ' + target['domain'] + ' · ' + target['level']) if target else ('跨部门配置不同，请选择' if status == 'conflict' else current if status not in ('missing_title', 'not_matched') else '职位未填写，跳过' if status == 'missing_title' else '职位不符合，跳过')
        items.append({**person, 'status': status, 'current_access': current, 'action': action,
                      'options': options if status in ('new', 'conflict') else [], 'target': target})
    if len(approved) > 1000:
        raise ApiError(422, 'BULK_LIMIT', '一次最多授权 1000 人，请缩小部门范围。')
    expires = int(time.time()) + 1800
    token = sign({'version': 2, 'actor': str(actor.id), 'org': str(actor.organization_id), 'expires': expires,
                  'rules': rules, 'approved': approved})
    items.sort(key=lambda p: (p['status'] not in ('new', 'conflict'), p['name'], p['open_id']))
    return envelope(request, {'items': items, 'preview_token': token, 'expires_at': expires,
                             'directory': snapshot['directory'],
                             'new_count': sum(p['status'] == 'new' for p in items),
                             'conflict_count': sum(p['status'] == 'conflict' for p in items)})


@router.post('/apply')
def apply(command: Apply, request: Request, actor: Actor = Depends(get_actor), session: Session = Depends(get_db)):
    require_super(session, actor)
    payload = verify(command.preview_token, actor)
    ids = list(dict.fromkeys(command.open_ids))
    if any(open_id not in payload['approved'] for open_id in ids):
        raise ApiError(422, 'INVALID_SELECTION', '只能选择预览中待新增的员工。')
    targets = {}
    for open_id in ids:
        options = payload['approved'][open_id]['options']
        choice = command.choices.get(open_id)
        target = next((o for o in options if o['department_id'] == choice), None) if choice else options[0] if len(options) == 1 else None
        if not target:
            raise ApiError(422, 'CHOICE_REQUIRED', '跨部门员工需选择预览中的方向和等级后再授权。')
        targets[open_id] = target
    directory = DepartmentDirectory(directory_for(actor))
    tree = directory.departments()
    validate_rules(tree, payload['rules'])
    # Recheck employment, job title and current department ancestry.
    fresh, failed = {}, {}
    for open_id in ids:
        try:
            person = directory.fresh(open_id, tree)
            approved = payload['approved'][open_id]
            if fingerprint(person) != approved['fingerprint'] or options_for(person, tree, payload['rules']) != approved['options']:
                failed[open_id] = '部门或职位已变化，请刷新通讯录后重新预览'
            else:
                fresh[open_id] = person
        except ApiError as exc:
            failed[open_id] = exc.message
    session.scalar(select(Organization.id).where(Organization.id == actor.organization_id).with_for_update())
    # Holding the actor lock prevents concurrent revocation while applying this batch.
    require_super(session, actor)
    results = []
    for open_id in ids:
        if open_id in failed:
            results.append({'open_id': open_id, 'status': 'failed', 'reason': failed[open_id]})
            continue
        user, status, reason = current_access(session, actor, open_id, lock=True)
        if status != 'new':
            results.append({'open_id': open_id, 'status': 'skipped', 'reason': reason})
            continue
        if user is None:
            user = User(id=uuid.uuid4(), organization_id=actor.organization_id,
                        display_name=fresh[open_id]['name'], status=UserStatus.ACTIVE)
            session.add(user)
            session.flush()
            session.add(ExternalIdentity(id=uuid.uuid4(), organization_id=actor.organization_id, user_id=user.id,
                provider='FEISHU', subject=directory_subject(open_id), revision=1))
        target = targets[open_id]
        session.add(ReviewAdminAccess(user_id=user.id, organization_id=actor.organization_id,
            access_role='admin', level=target['level'], domain=target['domain'], can_grant_super_admin=False,
            revision=1, granted_by=actor.id))
        session.add(RoleAssignment(id=uuid.uuid4(), organization_id=actor.organization_id, user_id=user.id, role=Role.REVIEWER))
        audit(session, request, actor, 'review_admin.bulk_access_granted', user.id,
              {'level': target['level'], 'domain': target['domain'], 'access_role': 'admin', 'department_id': target['department_id']})
        results.append({'open_id': open_id, 'status': 'created', 'reason': '已开通普通管理员 · ' + target['domain'] + ' · ' + target['level']})
    session.commit()
    return envelope(request, {'items': results})
