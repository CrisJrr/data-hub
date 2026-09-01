"""Adapter SQLite via aiosqlite."""
import aiosqlite
from src.adapters.base import BaseAdapter, QueryResult


class SQLiteAdapter(BaseAdapter):

    async def connect(self):
        db_path = self.config.get("path", "hub.db")
        self.db = await aiosqlite.connect(db_path)
        self.db.row_factory = aiosqlite.Row

    async def disconnect(self):
        if hasattr(self, "db") and self.db:
            await self.db.close()

    async def execute(self, sql: str, params: dict = None) -> QueryResult:
        async with self.db.execute(sql) as cursor:
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            records = await cursor.fetchall()
            rows = [dict(zip(columns, row)) for row in records]
            return QueryResult(columns=columns, rows=rows, row_count=len(rows))

    async def list_tables(self, schema: str = None) -> list[dict]:
        result = await self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [{"schema": "main", "table": r["name"]} for r in result.rows]

    async def describe_table(self, table: str, schema: str = "main") -> list[dict]:
        result = await self.execute(f"PRAGMA table_info('{table}')")
        return [{"column_name": r["name"], "data_type": r["type"]} for r in result.rows]
