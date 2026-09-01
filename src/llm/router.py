"""Router LLM via LiteLLM — suporta OpenAI, Claude, Ollama, 9router, etc."""
import re
import asyncio
from datetime import date
import litellm
from src.config import settings
from src.llm.prompts import SYSTEM_PROMPT
from src.logging_config import get_logger

logger = get_logger("datahub.llm")

# Desabilita telemetria do LiteLLM
litellm.suppress_debug_info = True

# Configuração de retry
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # segundos


async def _get_active_provider() -> dict | None:
    """Busca o provider LLM ativo (padrão) do banco."""
    try:
        from src.db import async_session
        from sqlalchemy import text
        async with async_session() as session:
            result = await session.execute(
                text("SELECT provider, model, api_key, api_base, max_tokens, temperature "
                     "FROM llm_providers WHERE is_active = true AND is_default = true LIMIT 1")
            )
            row = result.fetchone()
            if not row:
                # Fallback: qualquer um ativo
                result = await session.execute(
                    text("SELECT provider, model, api_key, api_base, max_tokens, temperature "
                         "FROM llm_providers WHERE is_active = true LIMIT 1")
                )
                row = result.fetchone()
            if row:
                return {
                    "provider": row[0], "model": row[1], "api_key": row[2],
                    "api_base": row[3], "max_tokens": row[4], "temperature": row[5]
                }
    except Exception:
        pass
    return None


def _extract_sql(text: str) -> str:
    """Tenta extrair um SELECT de um texto (pode vir com markdown ou reasoning)."""
    if not text:
        return ""

    # Limpa code blocks markdown
    text = re.sub(r"```sql?\s*", "", text)
    text = re.sub(r"```\s*$", "", text).strip()

    # Se já começa com SELECT, retorna direto
    if text.upper().startswith("SELECT"):
        return text

    # Procura um SELECT no texto (pode estar misturado com reasoning)
    match = re.search(r"(SELECT\s+.+?)(?:\n\n|$|;)", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    # Último recurso: procura qualquer linha que comece com SELECT
    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("SELECT"):
            return line

    return text


async def generate_sql(question: str, schema: str, business_context: str = "") -> dict:
    """
    Interpreta pergunta em linguagem natural e gera SQL seguro.
    Retorna: {"success": True, "query": "SELECT ...", "method": "llm"}
             ou {"success": False, "error": "QUERY_NOT_POSSIBLE"}
    """
    # Busca provider ativo do banco
    provider_config = await _get_active_provider()
    if not provider_config:
        # Fallback pra configuração antiga via .env
        if not settings.llm_enabled:
            return {"success": False, "error": "LLM desabilitado"}
        provider_config = {
            "provider": "openai",
            "model": settings.llm_model,
            "api_key": settings.openai_api_key,
            "api_base": settings.llm_api_base,
            "max_tokens": 4000,
            "temperature": 0,
        }

    context_block = ""
    if business_context:
        context_block = f"\n\nCONTEXTO DO NEGÓCIO:\n{business_context}\n"

    prompt = SYSTEM_PROMPT.format(schema=schema, data_atual=date.today().strftime("%d/%m/%Y"))
    prompt = prompt.replace("SCHEMAS DO BANCO DE DADOS:", f"{context_block}\nSCHEMAS DO BANCO DE DADOS:")

    # Monta model string pro LiteLLM
    prov = provider_config["provider"]
    model = provider_config["model"]
    if prov not in model:
        model = f"{prov}/{model}"

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": question},
                ],
                "temperature": provider_config.get("temperature", 0),
                "max_tokens": provider_config.get("max_tokens", 4000),
            }

            if provider_config.get("api_key"):
                kwargs["api_key"] = provider_config["api_key"]

            if provider_config.get("api_base"):
                kwargs["api_base"] = provider_config["api_base"]

            response = await litellm.acompletion(**kwargs)

            msg = response.choices[0].message
            raw = msg.content or ""
            logger.info("llm_raw_response", extra={"extra_data": {"response": raw[:500], "attempt": attempt + 1}})

            # Modelos de raciocínio: se content vazio, tenta extrair do reasoning
            if not raw.strip() and getattr(msg, "reasoning_content", None):
                raw = msg.reasoning_content
                logger.info("llm_reasoning_content", extra={"extra_data": {"response": raw[:500]}})

            if not raw.strip():
                last_error = "LLM retornou resposta vazia"
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE ** (attempt + 1)
                    logger.warning(f"llm_empty_response_retry", extra={"extra_data": {"attempt": attempt + 1, "delay": delay}})
                    await asyncio.sleep(delay)
                    continue
                return {"success": False, "error": last_error}

            # Extrai o SQL do texto
            sql = _extract_sql(raw)

            # Valida que é SELECT
            if not sql.upper().startswith("SELECT"):
                return {"success": False, "error": "QUERY_NOT_POSSIBLE: não é SELECT"}

            # Bloqueia comandos perigosos
            forbidden = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "EXEC", "EXECUTE"]
            sql_upper = sql.upper()
            for cmd in forbidden:
                if re.search(r'\b' + cmd + r'\b', sql_upper):
                    return {"success": False, "error": f"QUERY_NOT_POSSIBLE: contém {cmd}"}

            return {"success": True, "query": sql, "method": "llm"}

        except Exception as e:
            last_error = str(e)
            logger.warning(f"llm_error_retry", extra={"extra_data": {"attempt": attempt + 1, "error": last_error}})
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE ** (attempt + 1)
                await asyncio.sleep(delay)
                continue

    return {"success": False, "error": f"Erro LLM após {MAX_RETRIES} tentativas: {last_error}"}


async def build_schema_summary(adapter, connection_name: str = "", schema_configs: dict = None, table_configs: dict = None) -> str:
    """Gera resumo do schema de um adapter para enviar ao LLM."""
    if schema_configs is None:
        schema_configs = {}
    if table_configs is None:
        table_configs = {}
    try:
        schemas = await adapter.list_schemas()
        parts = []
        for schema_name in schemas:
            # Verificar se o schema está habilitado
            config_key = f"{connection_name}.{schema_name}"
            config = schema_configs.get(config_key, {})
            if config.get("is_active") is False:
                continue  # Schema desabilitado, pular

            # Adicionar descrição do schema se existir
            description = config.get("description", "")

            # Listar tabelas do schema
            tables = await adapter.list_tables(schema_name)
            if not tables:
                continue

            schema_parts = []
            if description:
                schema_parts.append(f"# {description}")

            for t in tables[:10]:  # Limita a 10 tabelas por schema
                try:
                    table_name = t["table"] if isinstance(t, dict) else t
                    cols = await adapter.describe_table(table_name, schema_name)
                    col_strs = [f"{c['column_name']} {c['data_type']}" for c in cols[:15]]  # Max 15 colunas

                    # Verificar se tem descrição de tabela
                    table_key = f"{connection_name}.{schema_name}.{table_name}"
                    tbl_config = table_configs.get(table_key, {})
                    tbl_desc = tbl_config.get("description", "")
                    tbl_active = tbl_config.get("is_active", True)

                    if not tbl_active:
                        continue  # Tabela desabilitada

                    # Detectar range de datas automaticamente
                    date_info = ""
                    date_cols = [c for c in cols if c["data_type"] in ("date", "timestamp without time zone", "timestamp with time zone")]
                    if date_cols:
                        try:
                            dc = date_cols[0]
                            q = f"SELECT MIN({dc['column_name']}) as min_d, MAX({dc['column_name']}) as max_d FROM {schema_name}.{table_name}"
                            dr = await adapter.execute(q)
                            if dr.rows and dr.rows[0].get("min_d"):
                                min_d = str(dr.rows[0]["min_d"])[:10]
                                max_d = str(dr.rows[0]["max_d"])[:10]
                                date_info = f" [dados: {min_d} a {max_d}]"
                        except Exception:
                            pass

                    col_str = ", ".join(col_strs)
                    if tbl_desc:
                        schema_parts.append(f"{schema_name}.{table_name}({col_str}) # {tbl_desc}{date_info}")
                    else:
                        schema_parts.append(f"{schema_name}.{table_name}({col_str}){date_info}")
                except Exception:
                    schema_parts.append(f"{schema_name}.{table_name}")

            if schema_parts:
                parts.append("\n".join(schema_parts))
        return "\n\n".join(parts)
    except Exception:
        return ""
