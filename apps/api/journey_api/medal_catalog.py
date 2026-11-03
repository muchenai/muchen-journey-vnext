"""Only the six priced shop publications supplied in project36.

This is an opt-in import, never startup seed data. The remaining artwork catalog
is preview-only; importing products never grants balances or ownership.
"""
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID, uuid5

# The complete administrator artwork library is selectable; importing the six
# priced products below remains a separate, explicit operation.
BADGE_ARTWORKS = {item['id']: item for item in json.loads(
    Path(__file__).with_name('badge_artworks.json').read_text(encoding='utf-8'))}

PROJECT36_MEDALS = [
    dict(key="product", name="洞察新星", artworkId="product-1", style="blue",
         description="从一个好问题开始，看见真实的用户需求。",
         costs=[dict(badgeId="product", points=20), dict(badgeId="data", points=10)]),
    dict(key="code", name="代码构筑者", artworkId="tech-1", style="purple",
         description="把想法写成代码，把可能变成可运行的作品。",
         costs=[dict(badgeId="tech", points=35)]),
    dict(key="data", name="数据领航员", artworkId="data-3", style="blue",
         description="在复杂信息中找到线索，让数据指引方向。",
         costs=[dict(badgeId="data", points=50), dict(badgeId="product", points=10)]),
    dict(key="pmo", name="协作指挥官", artworkId="pmo-2", style="purple",
         description="连接目标与行动，让每一次协作稳步向前。",
         costs=[dict(badgeId="pmo", points=65), dict(badgeId="project", points=10)]),
    dict(key="ai", name="智能探索家", artworkId="ai-evaluation-2", style="gold",
         description="保持好奇与判断，探索智能的边界与可能。",
         costs=[dict(badgeId="ai-eval", points=90), dict(badgeId="ai", points=20)]),
    dict(key="quality", name="品质守护者", artworkId="quality-1", style="gold",
         description="把认真做到极致，守护每一份交付的质量。",
         costs=[dict(badgeId="quality", points=180)]),
]
SHOP_ARTWORK_IDS = frozenset(m["artworkId"] for m in PROJECT36_MEDALS)


def install_project36_medals(session, organization_id: UUID, created_by: UUID):
    """Idempotently add missing products, preserving subsequent admin edits."""
    from journey_api.medal_routes import MedalContent
    from journey_api.models import User
    from journey_api.review_admin_models import MedalDefinition

    owner = session.get(User, created_by)
    if not owner or owner.organization_id != organization_id:
        raise ValueError("Product owner must belong to the target organization")
    created = []
    for template in PROJECT36_MEDALS:
        content = deepcopy(template)
        key = content.pop("key")
        medal_id = uuid5(organization_id, "project36-shop:" + key)
        if session.get(MedalDefinition, medal_id):
            continue
        content.update(image="", stock=None, status="published", redemptionLimit=1)
        session.add(MedalDefinition(id=medal_id, organization_id=organization_id,
            created_by=created_by, revision=1,
            content=MedalContent.model_validate(content).model_dump(mode="json")))
        created.append(str(medal_id))
    session.flush()
    return created
