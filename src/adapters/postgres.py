"""Adapter PostgreSQL via asyncpg."""
import asyncpg
from src.adapters.base import BaseAdapter, QueryResult


class PostgresAdapter(BaseAdapter):

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host=self.config["host"],
            port=self.config.get("port", 5432),
            database=self.config["database"],
            user=self.config["user"],
            password=self.config["password"],
            min_size=1,
            max_size=5,
        )

    async def disconnect(self):
        if hasattr(self, "pool") and self.pool:
            await self.pool.close()

    async def execute(self, sql: str, params: dict = None) -> QueryResult:
        async with self.pool.acquire() as conn:
            stmt = await conn.prepare(sql)
            records = await stmt.fetch()
            if not records:
                return QueryResult(columns=[], rows=[], row_count=0)
            columns = list(records[0].keys())
            rows = [dict(r) for r in records]
            return QueryResult(columns=columns, rows=rows, row_count=len(rows))

    async def list_tables(self) -> list[str]:
        result = await self.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        )
        return [r["table_name"] for r in result.rows]

    async def describe_table(self, table: str) -> list[dict]:
        result = await self.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = $1 ORDER BY ordinal_position",
        )
        return result.rows
