"""Rotas de configuração de provedores LLM."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from src.api.auth import get_current_user
from src.db import async_session

router = APIRouter(prefix="/llm-providers", tags=["llm-providers"])


class ProviderCreate(BaseModel):
    name: str
    provider: str  # gemini, openai, anthropic, ollama, custom
    model: str
    api_key: str = ""
    api_base: str = ""
    max_tokens: int = 4000
    temperature: int = 0
    is_active: bool = True
    is_default: bool = False


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


@router.get("/")
async def list_providers(user=Depends(get_current_user)):
    """Lista todos os provedores LLM."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, name, provider, model, api_key, api_base, "
                 "max_tokens, temperature, is_active, is_default, created_at "
                 "FROM llm_providers ORDER BY is_default DESC, name")
        )
        rows = result.fetchall()
        providers = []
        for r in rows:
            providers.append({
                "id": r[0], "name": r[1], "provider": r[2], "model": r[3],
                "api_key": r[4][:8] + "..." if r[4] and len(r[4]) > 8 else r[4],
                "api_base": r[5], "max_tokens": r[6], "temperature": r[7],
                "is_active": r[8], "is_default": r[9], "created_at": str(r[10])
            })
        return providers


@router.post("/")
async def create_provider(body: ProviderCreate, user=Depends(get_current_user)):
    """Cria um novo provedor LLM."""
    async with async_session() as session:
        # Se é o primeiro ou marcado como default, desmarcar outros
        if body.is_default:
            await session.execute(
                text("UPDATE llm_providers SET is_default = false")
            )

        result = await session.execute(
            text("INSERT INTO llm_providers "
                 "(name, provider, model, api_key, api_base, max_tokens, temperature, is_active, is_default) "
                 "VALUES (:name, :provider, :model, :api_key, :api_base, :max_tokens, :temperature, :is_active, :is_default) "
                 "RETURNING id"),
            body.model_dump()
        )
        new_id = result.fetchone()[0]
        await session.commit()
    return {"ok": True, "id": new_id}


@router.put("/{provider_id}")
async def update_provider(provider_id: int, body: ProviderUpdate, user=Depends(get_current_user)):
    """Atualiza um provedor LLM."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nenhum campo para atualizar")

    # Se marcando como default, desmarcar outros
    if updates.get("is_default"):
        async with async_session() as session:
            await session.execute(
                text("UPDATE llm_providers SET is_default = false")
            )

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = provider_id

    async with async_session() as session:
        await session.execute(
            text(f"UPDATE llm_providers SET {set_clause} WHERE id = :id"),
            updates
        )
        await session.commit()
    return {"ok": True}


@router.delete("/{provider_id}")
async def delete_provider(provider_id: int, user=Depends(get_current_user)):
    """Deleta um provedor LLM."""
    async with async_session() as session:
        await session.execute(
            text("DELETE FROM llm_providers WHERE id = :id"),
            {"id": provider_id}
        )
        await session.commit()
    return {"ok": True}


@router.post("/{provider_id}/set-default")
async def set_default_provider(provider_id: int, user=Depends(get_current_user)):
    """Define um provedor como padrão."""
    async with async_session() as session:
        await session.execute(
            text("UPDATE llm_providers SET is_default = false")
        )
        await session.execute(
            text("UPDATE llm_providers SET is_default = true WHERE id = :id"),
            {"id": provider_id}
        )
        await session.commit()
    return {"ok": True}


@router.get("/active")
async def get_active_provider():
    """Retorna o provider ativo (sem auth pra uso interno)."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, name, provider, model, api_key, api_base, "
                 "max_tokens, temperature FROM llm_providers "
                 "WHERE is_active = true AND is_default = true LIMIT 1")
        )
        row = result.fetchone()
        if not row:
            # Fallback: qualquer um ativo
            result = await session.execute(
                text("SELECT id, name, provider, model, api_key, api_base, "
                     "max_tokens, temperature FROM llm_providers "
                     "WHERE is_active = true LIMIT 1")
            )
            row = result.fetchone()
        if row:
            return {
                "id": row[0], "name": row[1], "provider": row[2], "model": row[3],
                "api_key": row[4], "api_base": row[5], "max_tokens": row[6],
                "temperature": row[7]
            }
        return None
