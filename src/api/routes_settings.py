"""Rotas de configurações globais do app."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from src.api.auth import get_current_user
from src.db import async_session

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingUpdate(BaseModel):
    value: str


@router.get("/{key}")
async def get_setting(key: str, user=Depends(get_current_user)):
    """Busca uma configuração pela chave."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT key, value, updated_at FROM app_settings WHERE key = :key"),
            {"key": key}
        )
        row = result.fetchone()
        if row:
            return {"key": row[0], "value": row[1], "updated_at": str(row[2])}
        return {"key": key, "value": "", "updated_at": None}


@router.put("/{key}")
async def update_setting(key: str, body: SettingUpdate, user=Depends(get_current_user)):
    """Salva ou atualiza uma configuração."""
    async with async_session() as session:
        await session.execute(
            text("INSERT INTO app_settings (key, value) VALUES (:key, :value) "
                 "ON CONFLICT(key) DO UPDATE SET value = :value, updated_at = CURRENT_TIMESTAMP"),
            {"key": key, "value": body.value}
        )
        await session.commit()
    return {"ok": True, "key": key}
