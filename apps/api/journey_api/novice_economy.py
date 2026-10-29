"""Wallet is derived from canonical completed assignments and immutable debits.

No demo balance or browser state is authoritative. Old published snapshots keep
their original reward schedule; updated publications opt into reward rules v2.
"""
from decimal import Decimal, ROUND_FLOOR
from sqlalchemy import select, func
from journey_api.models import Assignment, AssignmentStatus, Enrollment, Evaluation, Decision
from journey_api.review_admin_models import PublishedTaskContent, MedalRedemption, NoviceUnlockDebit

POINT_NAMES = {
    "product": "产品开发", "data": "数据交付", "tech": "技术开发", "pmo": "PMO",
    "ai-eval": "AI评测", "quality": "质量检测", "project": "项目管理", "ai": "AI 能力",
    "it-service": "IT服务", "talent-acquisition": "人才开发", "talent-development": "人才发展",
    "customer-growth": "客户增长", "hr-compensation": "人事薪酬", "finance-compliance": "财法合规",
    "organization-development": "组织发展", "intelligent-solutions": "智能产品方案",
    "workplace": "行政职场", "business-operations": "综合经营",
}
POINT_TYPES = frozenset(POINT_NAMES)
PRESETS = {"入门": (30, 50, 5), "进阶": (60, 100, 10), "挑战": (90, 150, 15)}

def rewards(content):
    minutes, xp, points = PRESETS.get(content.get("difficulty"), PRESETS["入门"])
    if content.get("rewardRulesVersion", 1) == 1 and content.get("difficulty") == "挑战":
        xp, points = 200, 20
    if content.get('rewardRulesVersion', 1) >= 3:
        points = 0
    total = xp // 10
    weights = content.get("badges", [])
    raw = [Decimal(total) * Decimal(str(b["weight"])) / 100 for b in weights]
    allocation = [int(n.to_integral_value(rounding=ROUND_FLOOR)) for n in raw]
    if weights and sum(Decimal(str(b["weight"])) for b in weights) == 100:
        order = sorted(range(len(weights)), key=lambda i: (-(raw[i]-allocation[i]), i))
        for i in order[:total-sum(allocation)]:
            allocation[i] += 1
    return dict(minutes=minutes, xp=xp, taskPoints=points, totalPoints=total,
                allocations=[dict(id=b["id"], points=allocation[i]) for i,b in enumerate(weights)])

def unlock_cost(content):
    # All currently available novice tasks can be claimed directly. Historical
    # immutable debit records stay available for audit and are never rewritten.
    return 0

def wallet(session, actor):
    # Evaluation existence prevents completion-like status alone minting rewards.
    passed = select(Evaluation.id).where(Evaluation.assignment_id == Assignment.id,
        Evaluation.organization_id == actor.organization_id, Evaluation.decision == Decision.PASS).exists()
    contents = session.scalars(select(PublishedTaskContent.content).join(Assignment,
        Assignment.task_version_id == PublishedTaskContent.task_version_id).join(Enrollment,
        Enrollment.id == Assignment.enrollment_id).where(
        Assignment.organization_id == actor.organization_id, Enrollment.organization_id == actor.organization_id,
        PublishedTaskContent.organization_id == actor.organization_id, Enrollment.learner_id == actor.id,
        Enrollment.novice_task_id.is_not(None), Assignment.status == AssignmentStatus.COMPLETED, passed)).all()
    balances = dict.fromkeys(POINT_TYPES, 0)
    task_points = xp = 0
    for content in contents:
        reward = rewards(content)
        task_points += reward["taskPoints"]
        xp += reward["xp"]
        for item in reward["allocations"]:
            if item["id"] in balances: balances[item["id"]] += item["points"]
    task_points -= session.scalar(select(func.coalesce(func.sum(NoviceUnlockDebit.amount), 0)).where(
        NoviceUnlockDebit.user_id == actor.id, NoviceUnlockDebit.organization_id == actor.organization_id))
    for content in session.scalars(select(MedalRedemption.content).where(
        MedalRedemption.user_id == actor.id, MedalRedemption.organization_id == actor.organization_id)):
        for item in content["costs"]: balances[item["badgeId"]] -= item["points"]
    return dict(taskPoints=task_points, xp=xp, badgeBalances=balances)
