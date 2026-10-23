"""Claim checks shared by the native UI and original review endpoints."""
from datetime import UTC, datetime
from sqlalchemy import select
from journey_api.errors import ApiError
from journey_api.models import ReviewStatus, User
from journey_api.review_admin_models import ReviewClaim

LEASE_SECONDS = 120


def live_claim(session, review):
    claim = session.get(ReviewClaim, review.id, populate_existing=True)
    if (claim and claim.organization_id == review.organization_id
        and review.status in {ReviewStatus.ASSIGNED, ReviewStatus.IN_REVIEW}
        and claim.expires_at > datetime.now(UTC)):
        return claim
    return None


def busy(session, claim):
    owner = session.get(User, claim.owner_id)
    name = owner.display_name if owner and owner.organization_id == claim.organization_id else "其他审核员"
    raise ApiError(409, "REVIEW_CLAIMED", f"该文档正在被{name}审核，请稍后再试。")


def check_read(session, review, actor):
    claim = live_claim(session, review)
    if claim and claim.owner_id != actor.id:
        busy(session, claim)


def check_write(session, review, actor, *, token=None, required=False):
    claim = live_claim(session, review)
    if claim and claim.owner_id != actor.id:
        busy(session, claim)
    recorded = session.get(ReviewClaim, review.id)
    if required or recorded:
        if not claim or str(claim.token) != str(token):
            raise ApiError(409, "REVIEW_CLAIM_EXPIRED", "审核占用已释放或过期，请返回列表重新领取。")
    return claim


def claim_views(session, reviews, actor):
    ids = [review.id for review in reviews if review.status in {ReviewStatus.ASSIGNED, ReviewStatus.IN_REVIEW}]
    rows = session.execute(select(ReviewClaim, User).join(User, User.id == ReviewClaim.owner_id)
        .where(ReviewClaim.review_id.in_(ids), ReviewClaim.organization_id == actor.organization_id,
               User.organization_id == actor.organization_id, ReviewClaim.expires_at > datetime.now(UTC))).all() if ids else []
    return {str(claim.review_id): {"owner_id": str(claim.owner_id), "owner_name": owner.display_name,
        "started_at": claim.started_at.isoformat(), "expires_at": claim.expires_at.isoformat(),
        "mine": claim.owner_id == actor.id, "version": claim.version} for claim, owner in rows}
