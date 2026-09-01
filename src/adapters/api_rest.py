"""Adapter para APIs REST externas (fonte de dados via HTTP)."""
import httpx
from src.adapters.base import BaseAdapter, QueryResult


class APIRestAdapter(BaseAdapter):

    async def connect(self):
        self.client = httpx.AsyncClient(
            base_url=self.config["base_url"],
            headers=self.config.get("headers", {}),
            timeout=30.0,
        )

    async def disconnect(self):
        if hasattr(self, "client") and self.client:
            await self.client.aclose()

    async def execute(self, endpoint: str, params: dict = None) -> QueryResult:
        """endpoint = path do endpoint, params = query params."""
        resp = await self.client.get(endpoint, params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            data = [data]
        if not data:
            return QueryResult(columns=[], rows=[], row_count=0)
        columns = list(data[0].keys()) if isinstance(data[0], dict) else []
        rows = data if isinstance(data[0], dict) else [{"value": d} for d in data]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows))

    async def list_tables(self, schema: str = None) -> list[dict]:
        """Retorna endpoints disponíveis definidos na config."""
        eps = self.config.get("endpoints", [])
        return [{"schema": "api", "table": e} for e in eps]

    async def describe_table(self, table: str, schema: str = "api") -> list[dict]:
        """Faz request de amostra pra detectar campos."""
        try:
            result = await self.execute(table)
            if result.rows:
                return [{"column_name": c, "data_type": "dynamic"} for c in result.columns]
        except Exception:
            pass
        return []
