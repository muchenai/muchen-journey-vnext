"""Organization-scoped, durable medal administration and atomic redemption."""
import base64
import re
import uuid
import xml.etree.ElementTree as ET
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from journey_api.auth import Actor, get_actor, get_learner_actor, require_role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.models import User, Role
from journey_api.review_admin_models import MedalDefinition, MedalRedemption
from journey_api.review_admin_access import require_publisher
from journey_api.review_admin_routes import envelope, audit
from journey_api.novice_economy import POINT_TYPES, wallet

router = APIRouter(prefix="/api/v1")

def validate_image(value):
    if not value: return value
    match = re.fullmatch(r"data:image/(png|jpeg|webp|svg\+xml);base64,([A-Za-z0-9+/]*={0,2})", value)
    if not match: raise ValueError("请上传有效的 SVG、PNG、JPG 或 WebP 图片")
    data = base64.b64decode(match[2], validate=True)
    if not data or len(data) > 2097152: raise ValueError("图片不能超过 2 MB")
    kind = match[1]
    if kind == "svg+xml":
        source = data.decode("utf-8")
        if re.search(r"<!DOCTYPE|<!ENTITY|<\?", source, re.I): raise ValueError("SVG 仅支持静态图形")
        root = ET.fromstring(source)
        allowed = set("svg g defs path rect circle ellipse line polyline polygon text tspan title desc linearGradient radialGradient stop clipPath mask".split())
        attributes = set("id x y x1 y1 x2 y2 cx cy r rx ry width height viewBox preserveAspectRatio d points transform fill fill-opacity fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset opacity color display visibility vector-effect clip-path clip-rule mask font-family font-size font-weight font-style text-anchor dominant-baseline alignment-baseline letter-spacing word-spacing dx dy rotate textLength lengthAdjust gradientUnits gradientTransform spreadMethod offset stop-color stop-opacity fx fy fr clipPathUnits maskUnits maskContentUnits style href space".split())
        def visit(node, depth=0):
            tag = node.tag.removeprefix("{http://www.w3.org/2000/svg}")
            if depth > 32 or tag not in allowed: raise ValueError("SVG 包含不支持的元素")
            for key, content in node.attrib.items():
                key = key.removeprefix("{http://www.w3.org/1999/xlink}").removeprefix("{http://www.w3.org/XML/1998/namespace}")
                if key not in attributes or re.search(r"\\|/\*|\*/|expression\s*\(|@|(?:javascript|vbscript|data|https?|file|ftp):", content, re.I):
                    raise ValueError("SVG 不能包含脚本或外部资源")
                if key == "href" and (tag not in {"linearGradient", "radialGradient"} or not re.fullmatch(r"#[A-Za-z_][\w.:-]*", content)):
                    raise ValueError("SVG 不支持外部引用")
                safe = re.sub(r"url\(\s*['\"]?#[A-Za-z_][\w.:-]*['\"]?\s*\)", "", content, flags=re.I)
                if re.search(r"url\s*\(", safe, re.I): raise ValueError("SVG 不支持外部引用")
            for child in node: visit(child, depth+1)
        if len(list(root.iter())) > 1500 or root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}: raise ValueError("SVG 过于复杂或格式错误")
        visit(root)
    elif not ((kind == "png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or
              (kind == "jpeg" and data.startswith(b"\xff\xd8\xff")) or
              (kind == "webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise ValueError("图片内容与文件格式不符")
    return value

class Cost(BaseModel):
    badgeId: str
    points: int = Field(strict=True, ge=1, le=1000000)

class MedalContent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    image: str = Field(default="", max_length=2800000)
    style: Literal["blue", "gold", "green"] = "blue"
    costs: list[Cost] = Field(default_factory=list, max_length=8)
    stock: int | None = Field(default=None, strict=True, ge=0, le=1000000)
    status: Literal["draft", "published", "unpublished"] = "draft"
    redemptionLimit: Literal[1] = 1

    @model_validator(mode="after")
    def valid(self):
        self.name = self.name.strip()
        if not self.name: raise ValueError("请填写徽章名称")
        if any(c.badgeId not in POINT_TYPES for c in self.costs) or len({c.badgeId for c in self.costs}) != len(self.costs):
            raise ValueError("兑换点数类型无效或重复")
        if self.status == "published" and not self.costs: raise ValueError("上架前请配置兑换点数")
        try: validate_image(self.image)
        except (ET.ParseError, UnicodeDecodeError, ValueError) as error: raise ValueError("徽章图片无效："+str(error)) from error
        return self

class SaveMedal(BaseModel):
    expected_revision: int = Field(ge=0)
    content: MedalContent

def medal_view(row):
    return dict(**row.content, id=str(row.id), revision=row.revision,
        createdAt=row.created_at.isoformat(), updatedAt=row.updated_at.isoformat())

def redemption_view(row, user):
    return dict(**row.content, id=str(row.id), medalId=str(row.medal_id), studentId=str(row.user_id),
        studentName=user.display_name, redeemedAt=row.created_at.isoformat())

@router.get("/review-admin/medals")
def catalog(request: Request, actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_publisher(session, actor)
    medals = session.scalars(select(MedalDefinition).where(MedalDefinition.organization_id == actor.organization_id)
        .order_by(MedalDefinition.updated_at.desc())).all()
    records = session.execute(select(MedalRedemption, User).join(User, User.id == MedalRedemption.user_id)
        .where(MedalRedemption.organization_id == actor.organization_id, User.organization_id == actor.organization_id)
        .order_by(MedalRedemption.created_at.desc())).all()
    return envelope(request, dict(medals=[medal_view(m) for m in medals], redemptions=[redemption_view(r,u) for r,u in records]))

@router.put("/review-admin/medals/{medal_id}")
def save(medal_id: uuid.UUID, command: SaveMedal, request: Request,
         actor: Actor=Depends(get_actor), session: Session=Depends(get_db)):
    require_publisher(session, actor)
    row = session.scalar(select(MedalDefinition).where(MedalDefinition.id == medal_id).with_for_update())
    if row and row.organization_id != actor.organization_id: raise ApiError(404, "NOT_FOUND", "徽章不存在。")
    if (row.revision if row else 0) != command.expected_revision:
        raise ApiError(409, "VERSION_CONFLICT", "徽章已被其他管理员更新，请返回列表刷新后重试。")
    value = command.content.model_dump(mode="json")
    if row:
        if row.content["status"] != "draft" and value["status"] == "draft":
            raise ApiError(409, "INVALID_STATE", "已上架徽章请使用下架操作。")
        row.content = value
        row.revision += 1
    else:
        row = MedalDefinition(id=medal_id, organization_id=actor.organization_id, created_by=actor.id, revision=1, content=value)
        session.add(row)
    audit(session, request, actor, "medal.save", medal_id, {"status":value["status"], "revision":row.revision})
    session.commit()
    return envelope(request, medal_view(row))

@router.get("/me/novice/wallet")
def read_wallet(request: Request, actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    require_role(actor, Role.LEARNER)
    return envelope(request, wallet(session, actor))

class RedeemMedal(BaseModel):
    expected_revision: int = Field(ge=1)

@router.post("/me/novice/medals/{medal_id}/redeem")
def redeem(medal_id: uuid.UUID, command: RedeemMedal, request: Request,
           actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    require_role(actor, Role.LEARNER)
    session.scalar(select(User.id).where(User.id == actor.id).with_for_update())
    previous = session.scalar(select(MedalRedemption).where(MedalRedemption.user_id == actor.id,
        MedalRedemption.organization_id == actor.organization_id, MedalRedemption.medal_id == medal_id))
    if previous: return envelope(request, dict(alreadyRedeemed=True, id=str(previous.id)))
    medal = session.scalar(select(MedalDefinition).where(MedalDefinition.id == medal_id,
        MedalDefinition.organization_id == actor.organization_id).with_for_update())
    if not medal or medal.content["status"] != "published": raise ApiError(404, "NOT_FOUND", "徽章尚未上架或已下架。")
    if medal.revision != command.expected_revision: raise ApiError(409, "VERSION_CONFLICT", "兑换条件已更新，请刷新后重试。")
    content = dict(medal.content)
    if content["stock"] == 0: raise ApiError(409, "OUT_OF_STOCK", "徽章库存不足。")
    balance = wallet(session, actor)["badgeBalances"]
    if any(balance[c["badgeId"]] < c["points"] for c in content["costs"]): raise ApiError(409, "INSUFFICIENT_POINTS", "徽章点不足，暂不能兑换。")
    result = MedalRedemption(id=uuid.uuid4(), organization_id=actor.organization_id, user_id=actor.id, medal_id=medal_id,
        content=dict(medalName=content["name"], image=content["image"], style=content["style"], costs=content["costs"]))
    session.add(result)
    if content["stock"] is not None:
        content["stock"] -= 1
        medal.content = content
        medal.revision += 1
    audit(session, request, actor, "medal.redeem", result.id, {"medal_id":str(medal_id)})
    session.commit()
    return envelope(request, dict(alreadyRedeemed=False, id=str(result.id)))
