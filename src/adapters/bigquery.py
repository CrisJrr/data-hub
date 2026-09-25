"""Adapter para Google BigQuery."""
import json
from src.logging_config import get_logger
from typing import Any
from src.adapters.base import BaseAdapter, QueryResult

logger = get_logger("datahub.bigquery")


class BigQueryAdapter(BaseAdapter):
    """Adapter para Google BigQuery."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.project_id = config.get("project_id", "")
        self.dataset = config.get("dataset", "")  # padrão
        self.credentials_json = config.get("credentials_json", "")  # service account JSON
        self._client = None

    async def connect(self):
        """Estabelece conexão com BigQuery."""
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
            import tempfile
            import os

            if self.credentials_json:
                # Parse JSON credentials
                if isinstance(self.credentials_json, str):
                    creds_dict = json.loads(self.credentials_json)
                else:
                    creds_dict = self.credentials_json

                creds = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=["https://www.googleapis.com/auth/bigquery"],
                )
            else:
                # Use Application Default Credentials
                creds = None

            self._client = bigquery.Client(
                project=self.project_id,
                credentials=creds,
            )
            logger.info(f"BigQuery connected: project={self.project_id}")
        except ImportError:
            raise Exception("google-cloud-bigquery não instalado. Execute: pip install google-cloud-bigquery")
        except Exception as e:
            raise Exception(f"Erro ao conectar BigQuery: {e}")

    async def disconnect(self):
        """Fecha a conexão."""
        if self._client:
            self._client.close()
            self._client = None

    async def execute(self, sql: str, params: dict = None) -> QueryResult:
        """Executa query no BigQuery."""
        if not self._client:
            await self.connect()

        try:
            from google.cloud import bigquery

            # BigQuery não usa %s placeholders, usa @param
            if params:
                job_config = bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter(k, "STRING", v)
                    for k, v in params.items()
                ])
            else:
                job_config = None

            query_job = self._client.query(sql, job_config=job_config)
            results = query_job.result()

            columns = [field.name for field in results.schema]
            rows = []
            for row in results:
                rows.append({col: getattr(row, col, None) for col in columns})

            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
            )
        except Exception as e:
            logger.error(f"BigQuery query error: {e}")
            raise

    async def list_schemas(self) -> list[str]:
        """Lista datasets (schemas) do BigQuery."""
        if not self._client:
            await self.connect()

        try:
            datasets = list(self._client.list_datasets())
            return [d.dataset_id for d in datasets]
        except Exception as e:
            logger.error(f"BigQuery list_schemas error: {e}")
            return []

    async def list_tables(self, schema: str = None) -> list[dict]:
        """Lista tabelas de um dataset."""
        if not self._client:
            await self.connect()

        schema = schema or self.dataset
        if not schema:
            # Se não tem dataset padrão, lista todos
            schemas = await self.list_schemas()
            tables = []
            for s in schemas:
                try:
                    t = await self.list_tables(s)
                    tables.extend(t)
                except:
                    pass
            return tables

        try:
            dataset_ref = self._client.dataset(schema)
            tables = list(self._client.list_tables(dataset_ref))
            return [{"schema": schema, "table": t.table_id} for t in tables]
        except Exception as e:
            logger.error(f"BigQuery list_tables error: {e}")
            return []

    async def describe_table(self, table: str, schema: str = None) -> list[dict]:
        """Retorna colunas e tipos da tabela."""
        if not self._client:
            await self.connect()

        schema = schema or self.dataset

        try:
            table_ref = self._client.dataset(schema).table(table)
            table_obj = self._client.get_table(table_ref)

            columns = []
            for field in table_obj.schema:
                columns.append({
                    "name": field.name,
                    "type": field.field_type,
                    "nullable": field.is_nullable,
                    "description": field.description or "",
                })
            return columns
        except Exception as e:
            logger.error(f"BigQuery describe_table error: {e}")
            return []
