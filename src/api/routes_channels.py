"""CRUD de canais de mensageria."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

router = APIRouter(prefix="/channels", tags=["channels"])


class ChannelCreate(BaseModel):
    name: str
    channel_type: str  # telegram, whatsapp
    config: dict[str, Any]


class ChannelResponse(ChannelCreate):
    id: int
    is_active: bool = True


_store: dict[int, dict] = {}
_next_id = 1


@router.post("/", response_model=ChannelResponse, status_code=201)
async def create_channel(ch: ChannelCreate):
    global _next_id
    for c in _store.values():
        if c["name"] == ch.name:
            raise HTTPException(409, f"Canal '{ch.name}' já existe")

    entry = {**ch.model_dump(), "id": _next_id, "is_active": True}
    _store[_next_id] = entry

    from src.core.hub import hub
    hub.channels.register(ch.name, ch.config | {"channel_type": ch.channel_type})

    _next_id += 1
    return entry


@router.get("/", response_model=list[ChannelResponse])
async def list_channels():
    return list(_store.values())


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: int):
    if channel_id not in _store:
        raise HTTPException(404, "Canal não encontrado")
    return _store[channel_id]


@router.delete("/{channel_id}")
async def delete_channel(channel_id: int):
    if channel_id not in _store:
        raise HTTPException(404, "Canal não encontrado")
    ch = _store.pop(channel_id)
    from src.core.hub import hub
    hub.channels.remove(ch["name"])
    return {"deleted": channel_id, "name": ch["name"]}


@router.post("/{channel_id}/test")
async def test_channel(channel_id: int):
    if channel_id not in _store:
        raise HTTPException(404, "Canal não encontrado")

    ch = _store[channel_id]
    from src.channels.telegram import TelegramChannel
    from src.channels.whatsapp import WhatsAppChannel

    channel_map = {
        "telegram": TelegramChannel,
        "whatsapp": WhatsAppChannel,
    }
    cls = channel_map.get(ch["channel_type"])
    if not cls:
        return {"connected": False, "error": f"Tipo '{ch['channel_type']}' não suportado"}

    try:
        instance = cls(ch["config"])
        healthy = await instance.health_check()
        return {"connected": healthy, "name": ch["name"]}
    except Exception as e:
        return {"connected": False, "error": str(e)}
