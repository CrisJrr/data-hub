"""Consulta direta em databases conectados."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    connection: str
    query: str


@router.post("/")
async def execute_query(req: QueryRequest):
    """Executa query direta numa conexão registrada."""
    from src.core.hub import hub
    from src.adapters import get_adapter

    if not hub.adapters.exists(req.connection):
        raise HTTPException(404, f"Conexão '{req.connection}' não encontrada")

    config = hub.adapters.get(req.connection)
    adapter = get_adapter(config["db_type"], config)

    try:
        await adapter.connect()
        result = await adapter.execute(req.query)
        await adapter.disconnect()
        return {
            "connection": req.connection,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "formatted": result.to_text(),
        }
    except Exception as e:
        raise HTTPException(500, f"Erro ao executar query: {str(e)}")


@router.get("/schema/{connection}")
async def get_schema(connection: str):
    """Retorna schema (tabelas + colunas) de uma conexão."""
    from src.core.hub import hub
    from src.adapters import get_adapter

    if not hub.adapters.exists(connection):
        raise HTTPException(404, f"Conexão '{connection}' não encontrada")

    config = hub.adapters.get(connection)
    adapter = get_adapter(config["db_type"], config)

    try:
        await adapter.connect()
        tables = await adapter.list_tables()
        schema = {}
        for table in tables[:20]:
            cols = await adapter.describe_table(table)
            schema[table] = cols
        await adapter.disconnect()
        return {"connection": connection, "tables": schema}
    except Exception as e:
        raise HTTPException(500, f"Erro ao obter schema: {str(e)}")
