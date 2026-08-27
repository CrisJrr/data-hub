"""CRUD de conexões de database."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectionCreate(BaseModel):
    name: str
    db_type: str  # postgres, mysql, sqlite, mongodb, api_rest
    config: dict[str, Any]


class ConnectionResponse(ConnectionCreate):
    id: int
    is_active: bool = True


# Armazenamento simplificado (em produção: SQLAlchemy)
_store: dict[int, dict] = {}
_next_id = 1


@router.post("/", response_model=ConnectionResponse, status_code=201)
async def create_connection(conn: ConnectionCreate):
    """Registra uma nova conexão de database."""
    global _next_id

    # Verifica nome duplicado
    for c in _store.values():
        if c["name"] == conn.name:
            raise HTTPException(409, f"Conexão '{conn.name}' já existe")

    entry = {**conn.model_dump(), "id": _next_id, "is_active": True}
    _store[_next_id] = entry

    # Registra no Hub
    from src.core.hub import hub
    hub.adapters.register(conn.name, conn.config | {"db_type": conn.db_type})

    _next_id += 1
    return entry


@router.get("/", response_model=list[ConnectionResponse])
async def list_connections():
    """Lista todas as conexões registradas."""
    return list(_store.values())


@router.get("/{conn_id}", response_model=ConnectionResponse)
async def get_connection(conn_id: int):
    """Busca uma conexão por ID."""
    if conn_id not in _store:
        raise HTTPException(404, "Conexão não encontrada")
    return _store[conn_id]


@router.delete("/{conn_id}")
async def delete_connection(conn_id: int):
    """Remove uma conexão."""
    if conn_id not in _store:
        raise HTTPException(404, "Conexão não encontrada")
    conn = _store.pop(conn_id)

    from src.core.hub import hub
    hub.adapters.remove(conn["name"])

    return {"deleted": conn_id, "name": conn["name"]}


@router.post("/{conn_id}/test")
async def test_connection(conn_id: int):
    """Testa se a conexão está funcionando."""
    if conn_id not in _store:
        raise HTTPException(404, "Conexão não encontrada")

    conn = _store[conn_id]
    from src.adapters import get_adapter
    try:
        adapter = get_adapter(conn["db_type"], conn["config"])
        await adapter.connect()
        healthy = await adapter.health_check()
        await adapter.disconnect()
        return {"connected": healthy, "name": conn["name"]}
    except Exception as e:
        return {"connected": False, "error": str(e)}
