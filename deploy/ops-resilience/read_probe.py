"""Exercise the repaired read handler with an existing operator; export counts only."""
import json
import uuid

from sqlalchemy import select, text
from starlette.requests import Request
from journey_api.auth import Actor
from journey_api.db import SessionLocal
from journey_api.models import Role, RoleAssignment, User, UserStatus
from journey_api.ops_routes import list_enrollments

with SessionLocal() as session:
    session.execute(text("SET TRANSACTION READ ONLY"))
    operators = session.scalars(
        select(User).join(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(RoleAssignment.role == Role.OPERATOR,
               RoleAssignment.organization_id == User.organization_id,
               User.status == UserStatus.ACTIVE)
        .order_by(User.organization_id, User.id)
    ).all()
    assert operators, "NO_EXISTING_OPERATOR"
    checked = set()
    count = multiple = 0
    for user in operators:
        if user.organization_id in checked:
            continue
        checked.add(user.organization_id)
        actor = Actor(id=user.id, organization_id=user.organization_id,
                      display_name=user.display_name, roles=frozenset({Role.OPERATOR}))
        request = Request({"type": "http", "state": {"request_id": str(uuid.uuid4())}})
        result = list_enrollments(request, actor=actor, session=session)["data"]
        count += len(result.items)
        multiple += sum(item.open_review_count > 1 for item in result.items)
    print(json.dumps({"ops_enrollment_read": "PASS", "organizations": len(checked),
                      "listed_enrollments": count, "multiple_open_review_enrollments": multiple}))
