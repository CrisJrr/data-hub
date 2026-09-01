"""Rotas de whitelist/blocklist para WhatsApp."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from src.api.auth import get_current_user
from src.db import async_session

router = APIRouter(prefix="/whatsapp-recipients", tags=["whatsapp-recipients"])


class RecipientCreate(BaseModel):
    number: str
    name: str = ""
    recipient_type: str = "individual"  # individual ou group
    list_type: str = "whitelist"        # whitelist ou blocklist
    is_active: bool = True


class RecipientUpdate(BaseModel):
    name: Optional[str] = None
    recipient_type: Optional[str] = None
    list_type: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/config")
async def get_recipient_config(user=Depends(get_current_user)):
    """Retorna a configuração do modo (whitelist/blocklist)."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT value FROM app_settings WHERE key = 'whatsapp_mode'")
        )
        row = result.fetchone()
        mode = row[0] if row else "blocklist"  # padrão: blocklist (envia pra todos, menos bloqueados)

        result2 = await session.execute(
            text("SELECT value FROM app_settings WHERE key = 'whatsapp_default_policy'")
        )
        row2 = result2.fetchone()
        policy = row2[0] if row2 else "allow"  # padrão: permitir quando não está na lista

        return {"mode": mode, "default_policy": policy}


class ModeUpdate(BaseModel):
    mode: str  # whitelist ou blocklist
    default_policy: str = "allow"  # allow ou deny


@router.put("/config")
async def update_recipient_config(body: ModeUpdate, user=Depends(get_current_user)):
    """Atualiza o modo whitelist/blocklist."""
    if body.mode not in ("whitelist", "blocklist"):
        raise HTTPException(status_code=400, detail="Modo deve ser 'whitelist' ou 'blocklist'")
    if body.default_policy not in ("allow", "deny"):
        raise HTTPException(status_code=400, detail="Política deve ser 'allow' ou 'deny'")

    async with async_session() as session:
        for key, val in [("whatsapp_mode", body.mode), ("whatsapp_default_policy", body.default_policy)]:
            await session.execute(
                text("INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (:key, :val, CURRENT_TIMESTAMP)"),
                {"key": key, "val": val}
            )
        await session.commit()
    return {"ok": True, "message": f"Modo alterado para {body.mode}"}


@router.get("/")
async def list_recipients(user=Depends(get_current_user)):
    """Lista todos os destinatários na whitelist/blocklist."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, number, name, recipient_type, list_type, is_active, created_at FROM whatsapp_recipients ORDER BY list_type, name")
        )
        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "number": r[1],
                "name": r[2],
                "recipient_type": r[3],
                "list_type": r[4],
                "is_active": r[5],
                "created_at": str(r[6]) if r[6] else None,
            }
            for r in rows
        ]


@router.post("/")
async def create_recipient(recipient: RecipientCreate, user=Depends(get_current_user)):
    """Adiciona um destinatário à whitelist/blocklist."""
    async with async_session() as session:
        # Check duplicate
        result = await session.execute(
            text("SELECT id FROM whatsapp_recipients WHERE number = :num AND list_type = :lt"),
            {"num": recipient.number, "lt": recipient.list_type}
        )
        if result.fetchone():
            raise HTTPException(status_code=400, detail="Destinatário já existe nesta lista")

        await session.execute(
            text("INSERT INTO whatsapp_recipients (number, name, recipient_type, list_type, is_active) VALUES (:num, :name, :rtype, :lt, :active)"),
            {
                "num": recipient.number,
                "name": recipient.name,
                "rtype": recipient.recipient_type,
                "lt": recipient.list_type,
                "active": recipient.is_active,
            }
        )
        await session.commit()
        return {"ok": True, "message": "Destinatário adicionado"}


@router.put("/{recipient_id}")
async def update_recipient(recipient_id: int, recipient: RecipientUpdate, user=Depends(get_current_user)):
    """Atualiza um destinatário."""
    async with async_session() as session:
        updates = []
        params = {"id": recipient_id}

        if recipient.name is not None:
            updates.append("name = :name")
            params["name"] = recipient.name
        if recipient.recipient_type is not None:
            updates.append("recipient_type = :rtype")
            params["rtype"] = recipient.recipient_type
        if recipient.list_type is not None:
            updates.append("list_type = :lt")
            params["lt"] = recipient.list_type
        if recipient.is_active is not None:
            updates.append("is_active = :active")
            params["active"] = recipient.is_active

        if not updates:
            return {"ok": True, "message": "Nada para atualizar"}

        await session.execute(
            text(f"UPDATE whatsapp_recipients SET {', '.join(updates)} WHERE id = :id"),
            params
        )
        await session.commit()
        return {"ok": True, "message": "Destinatário atualizado"}


@router.delete("/{recipient_id}")
async def delete_recipient(recipient_id: int, user=Depends(get_current_user)):
    """Remove um destinatário."""
    async with async_session() as session:
        await session.execute(text("DELETE FROM whatsapp_recipients WHERE id = :id"), {"id": recipient_id})
        await session.commit()
        return {"ok": True, "message": "Destinatário removido"}
