"""Camp classification shared by queue presentation and review authorization."""
from sqlalchemy import and_, or_, select
from journey_api.models import TaskDefinition
from journey_api.review_admin_models import ReviewAdminTask

EXPLORATION_TASK_KEYS = frozenset({
    "DAY-0", "TRE-001-COMPANY-VALUES", "TRE-002-AI-DATA-BASICS",
    "TRE-003-PROJECT-AWARENESS", "TRE-004-DELIVERY-FIT",
    "ASM-001-RULE-BREAKDOWN", "ASM-002-MODEL-JUDGEMENT", "ASM-003-DATA-CONSTRUCTION",
})


def task_camp(definition, profile):
    default = "exploration" if definition.stable_key in EXPLORATION_TASK_KEYS else "novice"
    return profile.content.get("camp", default) if profile else default


def exploration_task_scope():
    profile = select(ReviewAdminTask.task_definition_id).where(
        ReviewAdminTask.task_definition_id == TaskDefinition.id,
        ReviewAdminTask.organization_id == TaskDefinition.organization_id,
    )
    return or_(
        profile.where(ReviewAdminTask.content["camp"].as_string() == "exploration").exists(),
        and_(TaskDefinition.stable_key.in_(EXPLORATION_TASK_KEYS),
             ~profile.where(ReviewAdminTask.content["camp"].as_string().is_not(None)).exists()),
    )
