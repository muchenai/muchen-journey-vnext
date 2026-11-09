"""Wallet is derived from canonical completed assignments and immutable debits.

No demo balance or browser state is authoritative. Old published snapshots keep
their original reward schedule; updated publications opt into reward rules v2.
"""
from decimal import Decimal, ROUND_FLOOR
from sqlalchemy import select, func, literal, union_all
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

def completed_rewards_query(actor):
    # One immutable approval time per assignment. A repeated PASS must neither
    # duplicate a reward nor move its original earned time in the history.
    approvals = select(Evaluation.assignment_id,
        func.min(Evaluation.created_at).label("occurred_at")).where(
        Evaluation.organization_id == actor.organization_id,
        Evaluation.decision == Decision.PASS).group_by(Evaluation.assignment_id).subquery()
    return select(Assignment.id.label("source_id"), literal("task_reward").label("kind"),
        approvals.c.occurred_at, Assignment.task_definition_id.label("subject_id"),
        PublishedTaskContent.content.label("content")).select_from(Assignment).join(PublishedTaskContent,
        Assignment.task_version_id == PublishedTaskContent.task_version_id).join(Enrollment,
        Enrollment.id == Assignment.enrollment_id).join(approvals,
        approvals.c.assignment_id == Assignment.id).where(
        Assignment.organization_id == actor.organization_id, Enrollment.organization_id == actor.organization_id,
        PublishedTaskContent.organization_id == actor.organization_id, Enrollment.learner_id == actor.id,
        Enrollment.novice_task_id.is_not(None), Assignment.status == AssignmentStatus.COMPLETED)


def medal_redemptions_query(actor):
    return select(MedalRedemption).where(MedalRedemption.user_id == actor.id,
        MedalRedemption.organization_id == actor.organization_id)


def wallet(session, actor):
    contents = session.execute(completed_rewards_query(actor)).all()
    balances = dict.fromkeys(POINT_TYPES, 0)
    task_points = xp = 0
    for row in contents:
        reward = rewards(row.content)
        task_points += reward["taskPoints"]
        xp += reward["xp"]
        for item in reward["allocations"]:
            if item["id"] in balances: balances[item["id"]] += item["points"]
    task_points -= session.scalar(select(func.coalesce(func.sum(NoviceUnlockDebit.amount), 0)).where(
        NoviceUnlockDebit.user_id == actor.id, NoviceUnlockDebit.organization_id == actor.organization_id))
    redemptions = session.scalars(medal_redemptions_query(actor)).all()
    for redemption in redemptions:
        for item in redemption.content["costs"]: balances[item["badgeId"]] -= item["points"]
    # XP exchange remains closed: the only existing debits spend task points or
    # badge points. Never subtract either currency from a learner's earned XP.
    return dict(taskPoints=task_points, xp=xp, badgeBalances=balances,
                availableXp=xp, redeemedXp=0,
                ownedMedalCount=len({redemption.medal_id for redemption in redemptions}))


def growth_history(session, actor, *, offset=0, limit=20):
    redemptions = medal_redemptions_query(actor).with_only_columns(
        MedalRedemption.id.label("source_id"), literal("medal_redemption").label("kind"),
        MedalRedemption.created_at.label("occurred_at"), MedalRedemption.medal_id.label("subject_id"),
        MedalRedemption.content.label("content"))
    sources = union_all(completed_rewards_query(actor), redemptions).subquery()
    total = session.scalar(select(func.count()).select_from(sources))
    rows = session.execute(select(sources).order_by(sources.c.occurred_at.desc(),
        sources.c.kind, sources.c.source_id.desc()).offset(offset).limit(limit)).all()
    items = []
    for row in rows:
        item = dict(id=f"{row.kind}:{row.source_id}", kind=row.kind,
                    occurredAt=row.occurred_at.isoformat(), module="新手村")
        if row.kind == "task_reward":
            reward = rewards(row.content)
            item.update(title=row.content.get("title") or "历史新手村任务", taskId=str(row.subject_id),
                        xp=reward["xp"], badgePoints=reward["allocations"], method="任务审核通过")
        else:
            name = row.content.get("medalName") or "历史徽章"
            item.update(title=name, xp=0, medal=dict(id=str(row.subject_id), name=name),
                        badgePoints=[dict(id=cost["badgeId"], points=-cost["points"])
                                     for cost in row.content["costs"]], method="徽章点兑换")
        items.append(item)
    next_offset = offset + len(items)
    return dict(items=items, total=total, hasMore=next_offset < total,
                nextOffset=next_offset if next_offset < total else None)
