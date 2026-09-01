from src.adapters.base import BaseAdapter, QueryResult
from src.adapters.postgres import PostgresAdapter
from src.adapters.mysql import MySQLAdapter
from src.adapters.sqlite_adapter import SQLiteAdapter
from src.adapters.mongodb import MongoAdapter
from src.adapters.api_rest import APIRestAdapter
from src.adapters.bigquery import BigQueryAdapter

ADAPTER_MAP = {
    "postgres": PostgresAdapter,
    "mysql": MySQLAdapter,
    "sqlite": SQLiteAdapter,
    "mongodb": MongoAdapter,
    "api_rest": APIRestAdapter,
    "bigquery": BigQueryAdapter,
}


def get_adapter(db_type: str, config: dict) -> BaseAdapter:
    """Factory: retorna o adapter correto pro tipo de DB."""
    cls = ADAPTER_MAP.get(db_type)
    if not cls:
        raise ValueError(f"Tipo de DB desconhecido: {db_type}. Disponíveis: {list(ADAPTER_MAP.keys())}")
    return cls(config)
