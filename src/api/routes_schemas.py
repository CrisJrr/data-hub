"""Rotas de configuração de schemas pra IA."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from src.api.auth import get_current_user
from src.db import async_session

router = APIRouter(prefix="/schemas", tags=["schemas"])


class SchemaConfigCreate(BaseModel):
    connection_name: str
    schema_name: str
    table_name: Optional[str] = None
    description: str = ""
    is_active: bool = True


class SchemaConfigUpdate(BaseModel):
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/")
async def list_schema_configs(user=Depends(get_current_user)):
    """Lista todas as configurações de schemas/tabelas."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, connection_name, schema_name, table_name, description, is_active FROM schema_configs ORDER BY connection_name, schema_name, table_name")
        )
        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "connection_name": r[1],
                "schema_name": r[2],
                "table_name": r[3],
                "description": r[4],
                "is_active": r[5],
            }
            for r in rows
        ]


@router.post("/")
async def create_schema_config(config: SchemaConfigCreate, user=Depends(get_current_user)):
    """Cria uma nova configuração."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id FROM schema_configs WHERE connection_name = :conn AND schema_name = :schema AND (table_name = :tbl OR (table_name IS NULL AND :tbl IS NULL))"),
            {"conn": config.connection_name, "schema": config.schema_name, "tbl": config.table_name}
        )
        if result.fetchone():
            raise HTTPException(status_code=400, detail="Configuração já existe")

        await session.execute(
            text("INSERT INTO schema_configs (connection_name, schema_name, table_name, description, is_active) VALUES (:conn, :schema, :tbl, :desc, :active)"),
            {
                "conn": config.connection_name,
                "schema": config.schema_name,
                "tbl": config.table_name,
                "desc": config.description,
                "active": config.is_active,
            }
        )
        await session.commit()
        return {"ok": True, "message": "Configuração criada"}


@router.put("/{config_id}")
async def update_schema_config(config_id: int, config: SchemaConfigUpdate, user=Depends(get_current_user)):
    """Atualiza uma configuração."""
    async with async_session() as session:
        updates = []
        params = {"id": config_id}

        if config.description is not None:
            updates.append("description = :desc")
            params["desc"] = config.description
        if config.is_active is not None:
            updates.append("is_active = :active")
            params["active"] = config.is_active

        if not updates:
            return {"ok": True, "message": "Nada para atualizar"}

        await session.execute(
            text(f"UPDATE schema_configs SET {', '.join(updates)} WHERE id = :id"),
            params
        )
        await session.commit()
        return {"ok": True, "message": "Configuração atualizada"}


@router.delete("/{config_id}")
async def delete_schema_config(config_id: int, user=Depends(get_current_user)):
    """Deleta uma configuração."""
    async with async_session() as session:
        await session.execute(text("DELETE FROM schema_configs WHERE id = :id"), {"id": config_id})
        await session.commit()
        return {"ok": True, "message": "Configuração deletada"}


@router.post("/sync")
async def sync_schemas(user=Depends(get_current_user)):
    """Sincroniza schemas e tabelas de todas as conexões."""
    from src.core.hub import hub
    from src.adapters import get_adapter

    synced = 0
    async with async_session() as session:
        for conn_name in hub.adapters.list_names():
            config = hub.adapters.get(conn_name)
            try:
                adapter = get_adapter(config["db_type"], config.get("config", config))
                await adapter.connect()
                schemas = await adapter.list_schemas()

                for schema_name in schemas:
                    # Sync schema entry
                    result = await session.execute(
                        text("SELECT id FROM schema_configs WHERE connection_name = :conn AND schema_name = :schema AND table_name IS NULL"),
                        {"conn": conn_name, "schema": schema_name}
                    )
                    if not result.fetchone():
                        await session.execute(
                            text("INSERT INTO schema_configs (connection_name, schema_name, table_name, description, is_active) VALUES (:conn, :schema, NULL, '', true)"),
                            {"conn": conn_name, "schema": schema_name}
                        )
                        synced += 1

                    # Sync table entries
                    try:
                        tables = await adapter.list_tables(schema_name)
                        for tbl_item in tables:
                            table_name = tbl_item["table"] if isinstance(tbl_item, dict) else tbl_item
                            result = await session.execute(
                                text("SELECT id FROM schema_configs WHERE connection_name = :conn AND schema_name = :schema AND table_name = :tbl"),
                                {"conn": conn_name, "schema": schema_name, "tbl": table_name}
                            )
                            if not result.fetchone():
                                await session.execute(
                                    text("INSERT INTO schema_configs (connection_name, schema_name, table_name, description, is_active) VALUES (:conn, :schema, :tbl, '', true)"),
                                    {"conn": conn_name, "schema": schema_name, "tbl": table_name}
                                )
                                synced += 1
                    except Exception as e:
                        pass

                await adapter.disconnect()
            except Exception as e:
                continue

        await session.commit()
    return {"ok": True, "synced": synced, "message": f"{synced} novos registros sincronizados"}
