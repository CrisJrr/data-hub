"""CRUD de conexões de database — persistido no SQLite."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db import get_db
from src.core.models import DBConnection
from src.api.auth import get_current_user

router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectionCreate(BaseModel):
    name: str
    db_type: str  # postgres, mysql, sqlite, mongodb, api_rest
    config: dict


class ConnectionUpdate(BaseModel):
    name: str | None = None
    db_type: str | None = None
    config: dict | None = None


class ConnectionResponse(BaseModel):
    id: int
    name: str
    db_type: str
    config: dict
    is_active: bool


def _conn_to_dict(conn: DBConnection) -> dict:
    return {
        "id": conn.id,
        "name": conn.name,
        "db_type": conn.db_type,
        "config": conn.config,
        "is_active": conn.is_active,
    }


@router.post("/", response_model=ConnectionResponse, status_code=201)
async def create_connection(payload: ConnectionCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Registra uma nova conexão de database."""
    # Verifica nome duplicado
    existing = await db.execute(select(DBConnection).where(DBConnection.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Conexão '{payload.name}' já existe")

    conn = DBConnection(
        name=payload.name,
        db_type=payload.db_type,
        config=payload.config,
        is_active=True,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    # Registra no Hub
    from src.core.hub import hub
    hub.adapters.register(conn.name, payload.config | {"db_type": conn.db_type})

    return _conn_to_dict(conn)


@router.get("/", response_model=list[ConnectionResponse])
async def list_connections(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Lista todas as conexões registradas."""
    result = await db.execute(select(DBConnection).order_by(DBConnection.id))
    return [_conn_to_dict(c) for c in result.scalars().all()]


@router.get("/{conn_id}", response_model=ConnectionResponse)
async def get_connection(conn_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Busca uma conexão por ID."""
    conn = await db.get(DBConnection, conn_id)
    if not conn:
        raise HTTPException(404, "Conexão não encontrada")
    return _conn_to_dict(conn)


@router.put("/{conn_id}", response_model=ConnectionResponse)
async def update_connection(
    conn_id: int,
    payload: ConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Atualiza uma conexão existente."""
    conn = await db.get(DBConnection, conn_id)
    if not conn:
        raise HTTPException(404, "Conexão não encontrada")

    # Atualiza campos fornecidos
    if payload.name is not None:
        # Verifica nome duplicado
        existing = await db.execute(
            select(DBConnection).where(
                DBConnection.name == payload.name,
                DBConnection.id != conn_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"Conexão '{payload.name}' já existe")
        # Remove do hub com nome antigo
        from src.core.hub import hub
        hub.adapters.remove(conn.name)
        conn.name = payload.name

    if payload.db_type is not None:
        conn.db_type = payload.db_type

    if payload.config is not None:
        conn.config = payload.config

    await db.commit()
    await db.refresh(conn)

    # Registra no hub com dados atualizados
    from src.core.hub import hub
    hub.adapters.register(conn.name, conn.config | {"db_type": conn.db_type})

    return _conn_to_dict(conn)


@router.delete("/{conn_id}")
async def delete_connection(conn_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Remove uma conexão."""
    conn = await db.get(DBConnection, conn_id)
    if not conn:
        raise HTTPException(404, "Conexão não encontrada")

    name = conn.name
    await db.delete(conn)
    await db.commit()

    from src.core.hub import hub
    hub.adapters.remove(name)

    return {"deleted": conn_id, "name": name}


@router.post("/{conn_id}/test")
async def test_connection(conn_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Testa se a conexão está funcionando."""
    conn = await db.get(DBConnection, conn_id)
    if not conn:
        raise HTTPException(404, "Conexão não encontrada")

    from src.adapters import get_adapter
    from src.logging_config import get_logger
    logger = get_logger("datahub.connections")

    try:
        adapter = get_adapter(conn.db_type, conn.config)
        await adapter.connect()
        healthy = await adapter.health_check()
        await adapter.disconnect()
        logger.info("connection_test_ok", extra={"extra_data": {"name": conn.name, "db_type": conn.db_type}})
        return {"connected": healthy, "name": conn.name, "db_type": conn.db_type}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("connection_test_failed", extra={"extra_data": {"name": conn.name, "db_type": conn.db_type, "error": str(e), "traceback": tb}})
        return {"connected": False, "error": str(e), "db_type": conn.db_type, "traceback": tb}
