"""Bounded read-only metadata; no learner text, identity subjects or credentials."""
import json
from sqlalchemy import text
from journey_api.db import SessionLocal

with SessionLocal() as session:
    session.execute(text("SET TRANSACTION READ ONLY"))
    staff = [dict(row) for row in session.execute(text("""
        select u.id::text, u.organization_id::text, u.display_name, r.role,
          exists(select 1 from external_identities e where e.user_id=u.id
            and e.provider='FEISHU' and e.revoked_at is null) as feishu_bound,
          (select count(*) from enrollments n where n.reviewer_id=u.id) as enrollment_count
        from users u join role_assignments r on r.user_id=u.id
          and r.organization_id=u.organization_id
        where r.role in ('REVIEWER','OPERATOR') and u.status='ACTIVE'
        order by u.id,r.role limit 30
    """)).mappings()]
    stages = [dict(row) for row in session.execute(text("""
        select s.stable_key, s.position, s.title, s.completion_policy,
          t.id::text as task_version_id, t.version, t.learning_materials
        from journey_stage_versions s join task_versions t on t.id=s.task_version_id
        where s.journey_version_id='889b6c4c-09b9-4415-948b-a028f73087db'
        order by s.position
    """)).mappings()]
    # TEXT material bodies may contain internal documents; retain only metadata.
    for stage in stages:
        stage['learning_materials'] = [
            {key: material.get(key) for key in ('key','title','kind','url','required')}
            for material in stage['learning_materials']
        ]
    print(json.dumps({'staff': staff, 'stages': stages}, ensure_ascii=False))
