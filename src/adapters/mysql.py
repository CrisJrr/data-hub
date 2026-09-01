"""Adapter MySQL via aiomysql."""
import aiomysql
from src.adapters.base import BaseAdapter, QueryResult


class MySQLAdapter(BaseAdapter):

    async def connect(self):
        self.pool = await aiomysql.create_pool(
            host=self.config["host"],
            port=self.config.get("port", 3306),
            db=self.config["database"],
            user=self.config["user"],
            password=self.config["password"],
            minsize=1,
            maxsize=5,
        )

    async def disconnect(self):
        if hasattr(self, "pool") and self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def execute(self, sql: str, params: dict = None) -> QueryResult:
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql)
                records = await cur.fetchall()
                if not records:
                    return QueryResult(columns=[], rows=[], row_count=0)
                columns = [desc[0] for desc in cur.description]
                rows = [dict(r) for r in records]
                return QueryResult(columns=columns, rows=rows, row_count=len(rows))

    async def list_tables(self, schema: str = None) -> list[dict]:
        result = await self.execute(
            f"SHOW TABLES" if not schema else f"SHOW TABLES FROM `{schema}`"
        )
        if result.rows:
            key = list(result.rows[0].keys())[0]
            tables = [r[key] for r in result.rows]
            s = schema or "main"
            return [{"schema": s, "table": t} for t in tables]
        return []

    async def describe_table(self, table: str, schema: str = "main") -> list[dict]:
        prefix = f"`{schema}`." if schema and schema != "main" else ""
        result = await self.execute(f"DESCRIBE {prefix}`{table}`")
        return [{"column_name": r.get("Field", ""), "data_type": r.get("Type", "")} for r in result.rows]
