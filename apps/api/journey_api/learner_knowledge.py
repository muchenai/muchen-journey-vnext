"""Learner reads are scoped by organization, published state and destination module."""
import base64
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from journey_api.auth import Actor, get_learner_actor, require_role
from journey_api.models import Role
from journey_api.db import get_db
from journey_api.errors import ApiError
from journey_api.community_models import CommunityState, KnowledgeFile, KnowledgeChunk, KnowledgeFavorite
from journey_api.community_routes import initial, CHUNK_SIZE
from journey_api.review_admin_routes import envelope

router = APIRouter(prefix='/api/v1/me/knowledge')
Module = Literal['dashboard', 'village', 'academy', 'guild']


def visible_items(session, actor, module):
    require_role(actor, Role.LEARNER)
    row = session.get(CommunityState, (actor.organization_id, 'knowledge'))
    data = row.content if row else initial('knowledge')
    items = [item for item in data.get('items', []) if item.get('status') == 'published'
             and module in item.get('modules', [])]
    return data, items


def visible_item(session, actor, module, item_id):
    _, items = visible_items(session, actor, module)
    item = next((r for r in items if r['id'] == str(item_id)), None)
    if not item:
        raise ApiError(404, 'KNOWLEDGE_NOT_FOUND', '资料已下架、删除或未在当前模块发布。')
    return item


@router.get('/{module}')
def listing(module: Module, request: Request, actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    data, items = visible_items(session, actor, module)
    favorites = set(str(i) for i in session.scalars(select(KnowledgeFavorite.item_id).where(
        KnowledgeFavorite.organization_id==actor.organization_id, KnowledgeFavorite.user_id==actor.id)))
    public = []
    for item in items:
        row = {key:item[key] for key in ('id','kind','title','description','categoryId','fileName','fileType','mimeType','size','url','createdAt','updatedAt') if key in item}
        row.update(publisher=item.get('createdBy', {}).get('name', '管理员'), saved=item['id'] in favorites)
        public.append(row)
    return envelope(request, dict(categories=data['categories'], items=public))


class FavoriteCommand(BaseModel):
    saved: bool = Field(strict=True)


@router.post('/{module}/favorites/{item_id}')
def favorite(module: Module, item_id: uuid.UUID, command: FavoriteCommand, request: Request,
             actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    visible_item(session, actor, module, item_id)
    values = dict(organization_id=actor.organization_id, user_id=actor.id, item_id=item_id)
    if command.saved:
        session.execute(insert(KnowledgeFavorite).values(**values).on_conflict_do_nothing())
    else:
        session.execute(delete(KnowledgeFavorite).where(KnowledgeFavorite.organization_id==actor.organization_id,
            KnowledgeFavorite.user_id==actor.id, KnowledgeFavorite.item_id==item_id))
    session.commit()
    return envelope(request, dict(id=str(item_id), saved=command.saved))


@router.get('/{module}/files/{item_id}/chunks/{position}')
def chunk(module: Module, item_id: uuid.UUID, position: int, request: Request,
          actor: Actor=Depends(get_learner_actor), session: Session=Depends(get_db)):
    item = visible_item(session, actor, module, item_id)
    file = session.scalar(select(KnowledgeFile).where(KnowledgeFile.id==item_id,
        KnowledgeFile.organization_id==actor.organization_id, KnowledgeFile.complete==True))
    if item['kind'] != 'file' or not file or position < 0 or position * CHUNK_SIZE >= file.size:
        raise ApiError(404, 'KNOWLEDGE_NOT_FOUND', '文件或文件分段不存在。')
    part = session.get(KnowledgeChunk, (item_id, position))
    if part is None:
        raise ApiError(404, 'KNOWLEDGE_NOT_FOUND', '文件分段不存在。')
    return envelope(request, dict(data=base64.b64encode(part.data).decode()))
