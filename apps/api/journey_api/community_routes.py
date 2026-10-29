"""Real knowledge/guild commands. Client snapshots never authorize writes."""
import base64
import copy
import math
import re
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from journey_api.auth import Actor, get_actor
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.models import User, UserStatus, Role, RoleAssignment, TaskVersion, Assignment, Enrollment, Evaluation, Decision
from journey_api.review_admin_models import ReviewAdminTask
from journey_api.review_admin_access import require_publisher
from journey_api.community_models import CommunityState, KnowledgeFile, KnowledgeChunk, GuildContribution

router = APIRouter(prefix='/api/v1/review-admin/community')
CHUNK_SIZE = 512 * 1024
MAX_FILE_SIZE = 100 * 1024 * 1024
ABILITIES = {'data','implementation','quality','communication','collaboration'}


def fail(message, status=422):
    raise ApiError(status, 'COMMUNITY_INVALID' if status == 422 else 'COMMUNITY_CONFLICT', message)


def text(value, label, limit=1000, required=False):
    if not isinstance(value, str): fail(f'{label}格式不正确。')
    value = value.strip()
    if required and not value: fail(f'请填写{label}。')
    if len(value) > limit: fail(f'{label}不能超过 {limit} 个字。')
    return value


def url(value, required=True):
    value = text(value, '链接', 4000, required)
    if not value and not required: return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or re.search(r'[\s\\\x00-\x1f\x7f]', value): raise ValueError()
        parsed.port
    except ValueError: fail('请输入有效的 HTTP 或 HTTPS 链接，不能包含账号或密码。')
    return value


def identifier(value):
    try: return uuid.UUID(str(value))
    except (ValueError, TypeError): fail('记录编号无效。')


def timestamp(): return datetime.now(UTC).isoformat()


def initial(module):
    if module == 'knowledge':
        return dict(categories=[dict(id=k, name=v) for k,v in [('company','公司介绍'),('rules','规章制度'),('product','产品资料'),('training','培训材料'),('uncategorized','未分类')]], items=[])
    return dict(certifications=[], labs=[], rules=[])


def state_row(session, org, module):
    session.execute(insert(CommunityState).values(organization_id=org,module=module,revision=0,content=initial(module)).on_conflict_do_nothing())
    return session.scalar(select(CommunityState).where(CommunityState.organization_id==org, CommunityState.module==module).with_for_update().execution_options(populate_existing=True))


def find(items, record_id):
    row = next((r for r in items if r['id'] == record_id), None)
    if row is None: fail('记录已不存在，请刷新后重试。',404)
    return row


def category(data, value):
    value = value or 'uncategorized'
    find(data['categories'],value)
    return value


def learner(session, org, user_id):
    user = session.scalar(select(User).where(User.id==identifier(user_id), User.organization_id==org,
        User.status==UserStatus.ACTIVE, select(RoleAssignment.id).where(RoleAssignment.user_id==User.id,RoleAssignment.organization_id==org,RoleAssignment.role==Role.LEARNER).exists()))
    if not user: fail('请选择有效的本公司学员。')
    return user


def task_profile(session, org, task_id, published=False):
    row=session.scalar(select(ReviewAdminTask).where(ReviewAdminTask.task_definition_id==identifier(task_id), ReviewAdminTask.organization_id==org))
    if not row or (published and row.status!='published'): fail('请选择本公司已发布的任务。')
    return row


def snapshot(session, row):
    data=copy.deepcopy(row.content)
    data['revision']=row.revision
    if row.module == 'guild':
        org=row.organization_id
        data['learners']=[dict(id=str(u.id),name=u.display_name) for u in session.scalars(select(User).where(User.organization_id==org,User.status==UserStatus.ACTIVE,
            select(RoleAssignment.id).where(RoleAssignment.user_id==User.id,RoleAssignment.organization_id==org,RoleAssignment.role==Role.LEARNER).exists()).order_by(User.display_name))]
        data['tasks']=[dict(id=str(t.task_definition_id),title=t.content.get('title',''),summary=t.content.get('summary',''),status=t.status) for t in session.scalars(select(ReviewAdminTask).where(ReviewAdminTask.organization_id==org))]
        data['contributions']=list(session.scalars(select(GuildContribution.content).where(GuildContribution.organization_id==org)))
        data['contributions'].sort(key=lambda v:v['creditedAt'],reverse=True)
        data['stats']=dict(certifiedLearners=len({r['studentId'] for r in data['certifications'] if r['status']=='active'}),publishedLabs=sum(r['status']=='published' for r in data['labs']),totalPoints=sum(r['points'] for r in data['contributions']))
    return data


def file_type(name):
    ext=name.rsplit('.',1)[-1].lower()
    for kind,extensions in [('pdf',['pdf']),('word',['doc','docx','docm','dot','dotx','odt','rtf']),('ppt',['ppt','pptx','pptm','pps','ppsx','pot','potx','odp','key']),('sheet',['xls','xlsx','xlsm','csv','ods','numbers']),('image',['png','jpg','jpeg','webp','gif','bmp','avif','svg','tif','tiff','heic'])]:
        if ext in extensions:return kind
    return 'other'


def get_file(session, actor, record_id, *, writing=False):
    row=session.scalar(select(KnowledgeFile).where(KnowledgeFile.id==identifier(record_id),KnowledgeFile.organization_id==actor.organization_id).with_for_update())
    if not row: fail('文件不存在。',404)
    if writing and (row.created_by!=actor.id or row.complete):fail('不能修改该上传。',409)
    return row


def file_command(session, actor, action, p):
    if action=='beginUpload':
        name=text(p.get('fileName'), '文件名',255,True)
        size=p.get('size')
        if type(size) is not int or size<0 or size>MAX_FILE_SIZE:fail('单个文件不能超过 100 MB。')
        # Discard abandoned uploads only; published files are never expired.
        session.execute(delete(KnowledgeFile).where(KnowledgeFile.organization_id==actor.organization_id, KnowledgeFile.created_by==actor.id,KnowledgeFile.complete==False,KnowledgeFile.created_at<datetime.now(UTC)-timedelta(days=1)))
        if session.scalar(select(func.count()).select_from(KnowledgeFile).where(KnowledgeFile.created_by==actor.id,KnowledgeFile.complete==False))>=20:fail('未完成的上传过多，请重试或稍后上传。')
        mime={'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','gif':'image/gif','webp':'image/webp','avif':'image/avif','bmp':'image/bmp','pdf':'application/pdf'}.get(name.rsplit('.',1)[-1].lower(),'application/octet-stream')
        row=KnowledgeFile(id=uuid.uuid4(),organization_id=actor.organization_id,created_by=actor.id,size=size,complete=False,metadata_json=dict(fileName=name,size=size,mimeType=mime,fileType=file_type(name)))
        session.add(row);session.flush()
        return dict(id=str(row.id),chunkSize=CHUNK_SIZE)
    row=get_file(session,actor,p.get('id'),writing=action in ('uploadChunk','cancelUpload'))
    if action=='cancelUpload':session.delete(row);return None
    position=p.get('position')
    if type(position) is not int or position<0 or position>=math.ceil(row.size/CHUNK_SIZE):fail('文件分段编号无效。')
    if action=='getChunk':
        if not row.complete:fail('文件尚未上传完成。',409)
        chunk=session.get(KnowledgeChunk,(row.id,position))
        if not chunk:fail('文件分段不存在。',404)
        return dict(data=base64.b64encode(chunk.data).decode())
    try: decoded=base64.b64decode(p.get('data',''),validate=True)
    except (ValueError,TypeError):fail('文件分段格式无效。')
    expected=min(CHUNK_SIZE,row.size-position*CHUNK_SIZE)
    if len(decoded)!=expected:fail('文件分段大小不匹配。')
    previous=session.get(KnowledgeChunk,(row.id,position))
    if previous and previous.data!=decoded:fail('文件分段冲突，请重新上传。',409)
    if not previous:session.add(KnowledgeChunk(file_id=row.id,position=position,data=decoded))
    return None


def knowledge_change(session,actor,data,action,p):
    editor=dict(id=str(actor.id),name=actor.display_name)
    if action=='saveCategory':
        name=text(p.get('name'),'分类名称',30,True)
        if any(r['name'].casefold()==name.casefold() and r['id']!=p.get('id') for r in data['categories']):fail('分类名称已存在。')
        if p.get('id'):
            if p['id']=='uncategorized':fail('未分类不能改名。')
            row=find(data['categories'],p['id']);row['name']=name
        else:row=dict(id=str(uuid.uuid4()),name=name);data['categories'].append(row)
        return row
    if action=='removeCategory':
        if p.get('id')=='uncategorized':fail('未分类不能删除。')
        row=find(data['categories'],p.get('id'));data['categories'].remove(row)
        for item in data['items']:
            if item['categoryId']==row['id']:item['categoryId']='uncategorized'
        return None
    if action=='removeItem':
        row=find(data['items'],p.get('id'));data['items'].remove(row)
        if row['kind']=='file':session.delete(get_file(session,actor,row['id']))
        return None
    if action=='completeUpload':
        file=get_file(session,actor,p.get('id'),writing=True)
        chunks=session.execute(select(KnowledgeChunk.position,func.length(KnowledgeChunk.data)).where(KnowledgeChunk.file_id==file.id).order_by(KnowledgeChunk.position)).all()
        if len(chunks)!=math.ceil(file.size/CHUNK_SIZE) or sum(c[1] for c in chunks)!=file.size:fail('文件未完整上传，请重试。')
        row=dict(id=str(file.id),kind='file',title=file.metadata_json['fileName'][:120],**file.metadata_json,categoryId=category(data,p.get('categoryId')),description=text(p.get('description',''),'资料说明'),createdAt=timestamp(),updatedAt=timestamp(),createdBy=editor)
        file.complete=True;data['items'].insert(0,row);return row
    if action not in ('saveLink','updateItem'):fail('不支持的知识库操作。')
    row=find(data['items'],p['id']) if p.get('id') else None
    if action=='updateItem' and not row:fail('请选择资料。')
    fields=dict(title=text(p.get('title'),'资料名称',120,True),description=text(p.get('description',''),'资料说明'),categoryId=category(data,p.get('categoryId')),updatedAt=timestamp())
    if not row or row['kind']=='link':fields['url']=url(p.get('url',row.get('url') if row else ''))
    if row:row.update(fields)
    else:
        row=dict(id=str(uuid.uuid4()),kind='link',**fields,createdAt=timestamp(),createdBy=editor);data['items'].insert(0,row)
    return row


def guild_change(session,actor,data,action,p):
    editor=dict(id=str(actor.id),name=actor.display_name);now=timestamp()
    if action=='grantCertification':
        user=learner(session,actor.organization_id,p.get('studentId'))
        if not isinstance(p.get('ability'),str) or p.get('ability') not in ABILITIES or p.get('level') not in ('初级','中级','高级'):fail('认证能力或等级无效。')
        evidence=text(p.get('evidence'),'认证依据',1000,True)
        for old in data['certifications']:
            if old['studentId']==str(user.id) and old['ability']==p['ability'] and old['status']=='active':old.update(status='superseded',supersededAt=now)
        row=dict(id=str(uuid.uuid4()),studentId=str(user.id),studentName=user.display_name,ability=p['ability'],level=p['level'],evidence=evidence,status='active',issuedAt=now,issuedBy=editor)
        data['certifications'].insert(0,row);return row
    if action=='revokeCertification':
        row=find(data['certifications'],p.get('id'))
        if row['status']!='active':fail('只能撤销当前生效的认证。',409)
        row.update(status='revoked',revokeReason=text(p.get('reason'),'撤销原因',1000,True),revokedAt=now,revokedBy=editor);return row
    if action in ('saveLab','setLabStatus'):
        row=find(data['labs'],p['id']) if p.get('id') else None
        values={**(row or {}),**p}
        status=values.get('status','draft')
        if status not in ('draft','published','archived') or not isinstance(values.get('ability'),str) or values.get('ability') not in ABILITIES:fail('实验状态或能力无效。')
        task_id=values.get('taskId','')
        if task_id:task_profile(session,actor.organization_id,task_id,status=='published')
        fields=dict(title=text(values.get('title'),'实验名称',100,True),ability=values['ability'],description=text(values.get('description',''),'实验说明',2000,status=='published'),url=url(values.get('url',''),status=='published'),taskId=task_id,status=status,updatedAt=now,updatedBy=editor)
        if row:row.update(fields)
        else:row=dict(id=str(uuid.uuid4()),**fields,createdAt=now,createdBy=editor);data['labs'].insert(0,row)
        return row
    if action in ('saveRule','setRuleEnabled'):
        row=find(data['rules'],p.get('id')) if action=='setRuleEnabled' else next((r for r in data['rules'] if r['taskId']==p.get('taskId')),None)
        values={**(row or {}),**p};enabled=values.get('enabled',True);points=values.get('points')
        if type(enabled) is not bool or type(points) is not int or not 1<=points<=10000:fail('贡献点需为 1～10000 的整数，状态必须有效。')
        task=task_profile(session,actor.organization_id,values.get('taskId'),enabled or row is None)
        fields=dict(taskId=str(task.task_definition_id),taskTitle=task.content.get('title',''),points=points,enabled=enabled,updatedAt=now,updatedBy=editor)
        if row:
            if enabled and not row['enabled']:fields['enabledAt']=now
            row.update(fields)
        else:row=dict(id=str(uuid.uuid4()),**fields,createdAt=now,createdBy=editor,enabledAt=now if enabled else None);data['rules'].insert(0,row)
        return row
    fail('不支持的工会操作。')


class Command(BaseModel):
    action: str = Field(max_length=40)
    expected_revision: int | None = Field(default=None,ge=0)
    payload: dict = Field(default_factory=dict)


@router.post('/{module}')
def command(module: Literal['knowledge','guild'], command: Command, request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    from journey_api.review_admin_routes import envelope,audit
    require_publisher(session,actor)
    action,p=command.action,command.payload
    if module=='knowledge' and action in ('beginUpload','uploadChunk','cancelUpload','getChunk'):
        result=file_command(session,actor,action,p);session.commit()
        return envelope(request,dict(result=result))
    row=state_row(session,actor.organization_id,module)
    result=None
    if action!='snapshot':
        if row.revision!=command.expected_revision:fail('内容已被其他管理员更新，请刷新后重新操作。',409)
        data=copy.deepcopy(row.content)
        result=(knowledge_change if module=='knowledge' else guild_change)(session,actor,data,action,p)
        row.content=data;row.revision+=1
        audit(session,request,actor,f'{module}.{action}',actor.organization_id,{'record_id':result.get('id') if isinstance(result,dict) else p.get('id')})
        session.flush()
    response=dict(snapshot=snapshot(session,row),result=result)
    session.commit()
    return envelope(request,response)


def credit_guild_completion(session, context, evaluation):
    """Called inside the review transaction. No backfill and one credit per learner/task."""
    org=context.assignment.organization_id
    row=session.scalar(select(CommunityState).where(CommunityState.organization_id==org,CommunityState.module=='guild').with_for_update().execution_options(populate_existing=True))
    if not row:return
    task_id=context.task.task_definition_id
    rule=next((r for r in row.content['rules'] if r['taskId']==str(task_id) and r['enabled']),None)
    if not rule:return
    user_id=context.enrollment.learner_id
    prior=session.scalar(select(Evaluation.id).join(Assignment,Assignment.id==Evaluation.assignment_id).join(Enrollment,Enrollment.id==Assignment.enrollment_id).join(TaskVersion,TaskVersion.id==Assignment.task_version_id).where(
        Evaluation.organization_id==org,Evaluation.decision==Decision.PASS,Evaluation.id!=evaluation.id,Enrollment.learner_id==user_id,TaskVersion.task_definition_id==task_id).limit(1))
    if prior:return
    # Review commit-time ordering is serialized with rule edits by the guild row lock.
    now=timestamp();user=session.get(User,user_id)
    record=dict(id=str(uuid.uuid4()),studentId=str(user_id),studentName=user.display_name,taskId=str(task_id),taskTitle=rule['taskTitle'],submissionId=str(context.version.id),ruleId=rule['id'],points=rule['points'],creditedAt=now)
    session.flush()
    session.execute(insert(GuildContribution).values(id=uuid.UUID(record['id']),organization_id=org,user_id=user_id,task_id=task_id,evaluation_id=evaluation.id,content=record).on_conflict_do_nothing(constraint='uq_guild_first_completion'))
