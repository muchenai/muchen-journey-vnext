"""Wallet is derived from canonical completed assignments and immutable debits.

No demo balance or browser state is authoritative. Old published snapshots keep
their original reward schedule; updated publications opt into reward rules v2.
"""
from decimal import Decimal, ROUND_FLOOR
from sqlalchemy import BigInteger, select, func, literal, union_all, or_
from journey_api.config import get_settings
from journey_api.models import Assignment, AssignmentStatus, CompletionCode, Enrollment, Evaluation, Decision
from journey_api.management_access_models import MallPointExchange, OfflineExperienceGrant
from journey_api.course_workspace_models import CourseStudyAward
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
XP_PER_MALL_POINT = 10
PRESETS = {"入门": (30, 50, 5), "进阶": (60, 100, 10), "挑战": (90, 150, 15)}

def rewards(content):
    minutes, xp, points = PRESETS.get(content.get("difficulty"), PRESETS["入门"])
    if content.get("rewardRulesVersion", 1) == 1 and content.get("difficulty") == "挑战":
        xp, points = 200, 20
    if content.get('rewardRulesVersion', 1) >= 3:
        points = 0
    if content.get("rewardRulesVersion") == 4:
        xp = content["xp"]
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

def learner_owns(column, actor):
    corporate = select(CompletionCode.migrated_to_user_id).where(
        CompletionCode.organization_id == actor.organization_id, CompletionCode.user_id == actor.id,
        CompletionCode.used_at.is_not(None))
    return or_(column == actor.id, column.in_(corporate))


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
        PublishedTaskContent.organization_id == actor.organization_id, learner_owns(Enrollment.learner_id, actor),
        or_(PublishedTaskContent.content["camp"].as_string() == "novice", PublishedTaskContent.content["camp"].as_string().is_(None)),
        Enrollment.novice_task_id.is_not(None), Assignment.status == AssignmentStatus.COMPLETED)


def medal_redemptions_query(actor):
    return learner_credits(MedalRedemption, actor)


def learner_credits(model, actor):
    # Phone-to-Feishu migration keeps both accounts' immutable credit records.
    return select(model).where(model.organization_id == actor.organization_id, learner_owns(model.user_id, actor))


def mall_exchange_available():
    return get_settings().app_env == "local"


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
    task_points -= session.scalar(learner_credits(NoviceUnlockDebit, actor).with_only_columns(
        func.coalesce(func.sum(NoviceUnlockDebit.amount), 0)))
    redemptions = session.scalars(medal_redemptions_query(actor)).all()
    for redemption in redemptions:
        for item in redemption.content["costs"]: balances[item["badgeId"]] -= item["points"]
    for model in (OfflineExperienceGrant, CourseStudyAward):
        xp += int(session.scalar(learner_credits(model, actor).with_only_columns(func.coalesce(func.sum(model.xp), 0))))
    spent, points = session.execute(learner_credits(MallPointExchange, actor).with_only_columns(
        func.coalesce(func.sum(MallPointExchange.spent_xp), 0), func.coalesce(func.sum(MallPointExchange.points), 0)
    )).one()
    return dict(taskPoints=task_points, xp=xp, badgeBalances=balances,
                availableXp=xp-int(spent), redeemedXp=int(spent), mallPoints=int(points),
                mallExchangeAvailable=mall_exchange_available(),
                ownedMedalCount=len({redemption.medal_id for redemption in redemptions}))


def growth_history(session, actor, *, offset=0, limit=20, kind=None):
    redemptions = medal_redemptions_query(actor).with_only_columns(
        MedalRedemption.id.label("source_id"), literal("medal_redemption").label("kind"),
        MedalRedemption.created_at.label("occurred_at"), MedalRedemption.medal_id.label("subject_id"),
        MedalRedemption.content.label("content"))
    # Keep all types in one ordered result so offset pagination remains consistent.
    empty = (literal(None).label("credit_title"), literal(None).label("credit_xp"), literal(None).label("credit_detail"))
    grants = learner_credits(OfflineExperienceGrant, actor).with_only_columns(
        OfflineExperienceGrant.id, literal("offline_grant"), OfflineExperienceGrant.created_at,
        OfflineExperienceGrant.user_id, OfflineExperienceGrant.content, OfflineExperienceGrant.reason,
        OfflineExperienceGrant.xp, OfflineExperienceGrant.batch)
    study = learner_credits(CourseStudyAward, actor).with_only_columns(
        CourseStudyAward.id, literal("course_reward"), CourseStudyAward.created_at,
        CourseStudyAward.course_id, literal(None), CourseStudyAward.title, CourseStudyAward.xp, CourseStudyAward.scope)
    exchanges = learner_credits(MallPointExchange, actor).with_only_columns(
        MallPointExchange.id, literal("mall_exchange"), MallPointExchange.created_at,
        MallPointExchange.user_id, literal(None), literal(None), -MallPointExchange.spent_xp,
        literal(None), MallPointExchange.points)
    no_points = literal(None, type_=BigInteger).label("mall_points")
    sources = union_all(completed_rewards_query(actor).add_columns(*empty, no_points),
                        grants.add_columns(no_points), study.add_columns(no_points),
                        redemptions.add_columns(*empty, no_points), exchanges).subquery()
    if kind:
        sources = select(sources).where(sources.c.kind == kind).subquery()
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
        elif row.kind == "offline_grant":
            item.update(module="线下培训", title=row.credit_title, xp=row.credit_xp, badgePoints=[],
                        method=" · ".join(filter(None, [row.credit_detail, row.content.get("by")])))
        elif row.kind == "course_reward":
            item.update(module="AI 学院" if row.credit_detail == "academy" else "新手村", title=row.credit_title,
                        xp=row.credit_xp, badgePoints=[], method="课程学习奖励")
        elif row.kind == "mall_exchange":
            item.update(module="沐晨商城", title="经验兑换商城积分", xp=row.credit_xp, badgePoints=[],
                        mallPoints=row.mall_points, xpPerPoint=-row.credit_xp // row.mall_points, method="经验兑换")
        else:
            name = row.content.get("medalName") or "历史徽章"
            item.update(title=name, xp=0, medal=dict(id=str(row.subject_id), name=name),
                        badgePoints=[dict(id=cost["badgeId"], points=-cost["points"])
                                     for cost in row.content["costs"]], method="徽章点兑换")
        items.append(item)
    next_offset = offset + len(items)
    return dict(items=items, total=total, hasMore=next_offset < total,
                nextOffset=next_offset if next_offset < total else None)
