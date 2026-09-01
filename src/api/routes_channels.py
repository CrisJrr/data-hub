"""CRUD de canais de mensageria — persistido no SQLite."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db import get_db
from src.core.models import Channel
from src.api.auth import get_current_user

router = APIRouter(prefix="/channels", tags=["channels"])


class ChannelCreate(BaseModel):
    name: str
    channel_type: str  # telegram, whatsapp, slack, google_chat, teams
    config: dict


class ChannelResponse(BaseModel):
    id: int
    name: str
    channel_type: str
    config: dict
    is_active: bool


def _ch_to_dict(ch: Channel) -> dict:
    return {
        "id": ch.id,
        "name": ch.name,
        "channel_type": ch.channel_type,
        "config": ch.config,
        "is_active": ch.is_active,
    }


@router.post("/", response_model=ChannelResponse, status_code=201)
async def create_channel(payload: ChannelCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Registra um novo canal de mensageria."""
    # Verifica nome duplicado
    existing = await db.execute(select(Channel).where(Channel.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Canal '{payload.name}' já existe")

    ch = Channel(
        name=payload.name,
        channel_type=payload.channel_type,
        config=payload.config,
        is_active=True,
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)

    # Registra no Hub
    from src.core.hub import hub
    hub.channels.register(ch.name, payload.config | {"channel_type": ch.channel_type})

    return _ch_to_dict(ch)


@router.get("/", response_model=list[ChannelResponse])
async def list_channels(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Lista todos os canais registrados."""
    result = await db.execute(select(Channel).order_by(Channel.id))
    return [_ch_to_dict(c) for c in result.scalars().all()]


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Busca um canal por ID."""
    ch = await db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(404, "Canal não encontrado")
    return _ch_to_dict(ch)


@router.delete("/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Remove um canal."""
    ch = await db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(404, "Canal não encontrado")

    name = ch.name
    await db.delete(ch)
    await db.commit()

    from src.core.hub import hub
    hub.channels.remove(name)

    return {"deleted": channel_id, "name": name}


@router.post("/{channel_id}/test")
async def test_channel(channel_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Testa se o canal está funcionando."""
    ch = await db.get(Channel, channel_id)
    if not ch:
        raise HTTPException(404, "Canal não encontrado")

    from src.channels.telegram import TelegramChannel
    from src.channels.whatsapp import WhatsAppChannel
    from src.channels.slack import SlackChannel
    from src.channels.google_chat import GoogleChatChannel
    from src.channels.teams import TeamsChannel

    channel_map = {
        "telegram": TelegramChannel,
        "whatsapp": WhatsAppChannel,
        "slack": SlackChannel,
        "google_chat": GoogleChatChannel,
        "teams": TeamsChannel,
    }
    cls = channel_map.get(ch.channel_type)
    if not cls:
        return {"connected": False, "error": f"Tipo '{ch.channel_type}' não suportado"}

    try:
        instance = cls(ch.config)
        healthy = await instance.health_check()
        return {"connected": healthy, "name": ch.name}
    except Exception as e:
        return {"connected": False, "error": str(e)}
