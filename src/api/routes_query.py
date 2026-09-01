"""Consulta direta em databases conectados."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from src.api.auth import get_current_user

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    connection: str
    query: str


@router.post("/")
async def execute_query(req: QueryRequest, user=Depends(get_current_user)):
    """Executa query direta numa conexão registrada."""
    from src.core.hub import hub
    from src.adapters import get_adapter

    if not hub.adapters.exists(req.connection):
        raise HTTPException(404, f"Conexão '{req.connection}' não encontrada")

    config = hub.adapters.get(req.connection)
    adapter = get_adapter(config["db_type"], config.get("config", config))

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
async def get_schema(connection: str, schema: str = None, user=Depends(get_current_user)):
    """Retorna schema (schemas > tabelas + colunas) de uma conexão."""
    from src.core.hub import hub
    from src.adapters import get_adapter

    if not hub.adapters.exists(connection):
        raise HTTPException(404, f"Conexão '{connection}' não encontrada")

    config = hub.adapters.get(connection)
    adapter = get_adapter(config["db_type"], config.get("config", config))

    try:
        await adapter.connect()

        # Busca schemas (só pra PG)
        schemas = {}
        if hasattr(adapter, 'list_schemas'):
            schema_names = await adapter.list_schemas()
        else:
            schema_names = []

        # Busca tabelas
        tables_list = await adapter.list_tables(schema=schema)

        # Agrupa por schema
        for item in tables_list:
            s = item["schema"]
            t = item["table"]
            if s not in schemas:
                schemas[s] = {}
            cols = await adapter.describe_table(t, schema=s)
            schemas[s][t] = cols

        await adapter.disconnect()
        return {"connection": connection, "schemas": schemas, "schema_list": schema_names}
    except Exception as e:
        raise HTTPException(500, f"Erro ao obter schema: {str(e)}")
