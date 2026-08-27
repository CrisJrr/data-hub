"""Adapter MongoDB via Motor (async)."""
from motor.motor_asyncio import AsyncIOMotorClient
from src.adapters.base import BaseAdapter, QueryResult


class MongoAdapter(BaseAdapter):

    async def connect(self):
        self.client = AsyncIOMotorClient(self.config["uri"])
        self.db = self.client[self.config["database"]]

    async def disconnect(self):
        if hasattr(self, "client") and self.client:
            self.client.close()

    async def execute(self, collection_name: str, params: dict = None) -> QueryResult:
        """collection_name = nome da coleção, params = filtro JSON."""
        collection = self.db[collection_name]
        filter_doc = params or {}
        cursor = collection.find(filter_doc).limit(50)
        docs = []
        async for doc in cursor:
            doc.pop("_id", None)
            docs.append(doc)
        columns = list(docs[0].keys()) if docs else []
        return QueryResult(columns=columns, rows=docs, row_count=len(docs))

    async def list_tables(self) -> list[str]:
        return await self.db.list_collection_names()

    async def describe_table(self, table: str) -> list[dict]:
        sample = await self.db[table].find_one()
        if not sample:
            return []
        return [{"column_name": k, "data_type": type(v).__name__} for k, v in sample.items() if k != "_id"]
