"""Intent Engine — Motor de decisão Regex + LLM."""
import re
import time
from src.logging_config import get_logger
from dataclasses import dataclass
from typing import Optional

from src.core.hub import hub
from src.adapters.base import QueryResult
from src.adapters import get_adapter

logger = get_logger("datahub.intent_engine")


@dataclass
class IntentResult:
    """Resultado do processamento de uma intenção."""
    success: bool
    method: str           # "regex" | "llm" | "none"
    query: str
    result: Optional[QueryResult] = None
    error: str = ""
    latency_ms: float = 0
    rule_name: str = ""


class IntentEngine:
    """
    Motor de intenção híbrido:
    1. Tenta matching Regex (grátis, instantâneo)
    2. Fallback pra LLM (custo mínimo, mais flexível)
    """

    def __init__(self, rules: list[dict], llm_enabled: bool = True):
        self.rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
        self.llm_enabled = llm_enabled

    async def process(self, message: str, target_connection: str = None) -> IntentResult:
        """Processa uma mensagem e retorna o resultado."""
        start = time.time()

        # 1. Tentar Regex
        for rule in self.rules:
            if not rule.get("is_active", True) or rule.get("use_llm", False):
                continue

            pattern = rule.get("pattern", "")
            match = re.search(pattern, message, re.IGNORECASE)

            if match:
                logger.info(f"Regex match: rule '{rule.get('name')}' pattern='{pattern}'")
                query = self._fill_query(rule.get("query_template", ""), match)
                conn_name = target_connection or rule.get("connection")
                result = await self._execute_query(conn_name, query)
                latency = (time.time() - start) * 1000

                return IntentResult(
                    success=True, method="regex", query=query,
                    result=result, latency_ms=latency,
                    rule_name=rule.get("name", ""),
                )

        # 2. Fallback LLM
        if self.llm_enabled:
            return await self._llm_fallback(message, target_connection, start)

        latency = (time.time() - start) * 1000
        return IntentResult(
            success=False, method="none", query="",
            error="Nenhuma regra regex encontrada e LLM desabilitado",
            latency_ms=latency,
        )

    def _fill_query(self, template: str, match) -> str:
        """Preenche placeholders na query template."""
        query = template
        for key, value in match.groupdict().items():
            query = query.replace(f"{{{key}}}", value)
        if "{" in query and "}" in query:
            full_match = match.group(0)
            query = re.sub(r"\{[^}]+\}", full_match, query)
        return query

    async def _llm_fallback(
        self, message: str, target_connection: str, start: float
    ) -> IntentResult:
        """Interpreta via LLM e gera SQL automaticamente."""
        from src.llm.router import generate_sql, build_schema_summary
        from src.db.queries import load_schema_configs, load_business_context

        conn_names = self._get_connection_names(target_connection)
        if not conn_names:
            latency = (time.time() - start) * 1000
            return IntentResult(
                success=False, method="llm", query="",
                error="Nenhum adapter registrado", latency_ms=latency,
            )

        # Carrega configs do banco
        schema_configs, table_configs = await load_schema_configs()
        business_context = await load_business_context()

        # Monta schema de todas as conexões
        combined_schema = await self._build_all_schemas(conn_names, schema_configs, table_configs)
        if not combined_schema:
            latency = (time.time() - start) * 1000
            return IntentResult(
                success=False, method="llm", query="",
                error="Nenhum schema disponível", latency_ms=latency,
            )

        # Gera SQL via LLM
        response = await generate_sql(message, combined_schema, business_context)
        if not response["success"]:
            latency = (time.time() - start) * 1000
            return IntentResult(
                success=False, method="llm", query="",
                error=response["error"], latency_ms=latency,
            )

        # Executa em todas as conexões, usa a primeira que funcionar
        query = response["query"]
        last_error = None
        for cn in conn_names:
            try:
                result = await self._execute_query(cn, query)
                latency = (time.time() - start) * 1000
                return IntentResult(
                    success=True, method="llm", query=query,
                    result=result, latency_ms=latency,
                )
            except Exception as e:
                last_error = str(e)
                continue

        latency = (time.time() - start) * 1000
        return IntentResult(
            success=False, method="llm", query=query,
            error=f"Query gerada mas falhou: {last_error}", latency_ms=latency,
        )

    def _get_connection_names(self, target_connection: str = None) -> list[str]:
        """Retorna nomes das conexões alvo."""
        if target_connection and hub.adapters.exists(target_connection):
            return [target_connection]
        return hub.adapters.list_names()

    async def _build_all_schemas(
        self, conn_names: list[str], schema_configs: dict, table_configs: dict
    ) -> str:
        """Monta schema combinado de todas as conexões."""
        from src.llm.router import build_schema_summary
        all_schemas = []
        for cn in conn_names:
            config = hub.adapters.get(cn)
            try:
                adapter = get_adapter(config["db_type"], config.get("config", config))
                await adapter.connect()
                schema = await build_schema_summary(adapter, cn, schema_configs, table_configs)
                await adapter.disconnect()
                if schema.strip():
                    all_schemas.append(f"=== Conexão: {cn} ===\n{schema}")
            except Exception as e:
                logger.warning(f"Erro ao obter schema de {cn}: {e}")
        return "\n\n".join(all_schemas)

    async def _execute_query(self, conn_name: str, query: str) -> QueryResult:
        """Executa query num adapter específico."""
        config = hub.adapters.get(conn_name)
        adapter = get_adapter(config["db_type"], config.get("config", config))
        await adapter.connect()
        logger.info(f"Executing query on {conn_name}: {query[:200]}")
        try:
            result = await adapter.execute(query)
            logger.info(f"Query result: {result.row_count} rows")
            return result
        finally:
            await adapter.disconnect()
