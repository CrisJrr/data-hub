"""Queries centralizadas — evita SQL espalhado pelo código."""
from sqlalchemy import text
from src.db import async_session
from src.logging_config import get_logger

logger = get_logger("datahub.queries")


async def load_schema_configs() -> tuple[dict, dict]:
    """Carrega schema_configs e table_configs do banco.
    
    Returns:
        (schema_configs, table_configs) — dicts com chaves 'connection.schema[.table]'
    """
    schema_configs = {}
    table_configs = {}
    try:
        async with async_session() as session:
            result = await session.execute(
                text("SELECT connection_name, schema_name, table_name, description, is_active "
                     "FROM schema_configs")
            )
            for row in result.fetchall():
                if row[2] is None:
                    key = f"{row[0]}.{row[1]}"
                    schema_configs[key] = {"description": row[3], "is_active": row[4]}
                else:
                    key = f"{row[0]}.{row[1]}.{row[2]}"
                    table_configs[key] = {"description": row[3], "is_active": row[4]}
    except Exception as e:
        logger.warning(f"Erro ao carregar schema/table configs: {e}")
    return schema_configs, table_configs


async def load_business_context() -> str:
    """Carrega business_context do app_settings."""
    try:
        async with async_session() as session:
            result = await session.execute(
                text("SELECT value FROM app_settings WHERE key = 'business_context'")
            )
            row = result.fetchone()
            return row[0] if row else ""
    except Exception:
        return ""


async def load_intent_rules() -> list[dict]:
    """Carrega regras de intenção do banco."""
    from src.db import engine
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, name, pattern, connection_name, query_template, "
                 "priority, is_active, use_llm, llm_description "
                 "FROM intent_rules ORDER BY priority DESC")
        )
        rules = []
        for row in result:
            rules.append({
                "id": row[0], "name": row[1], "pattern": row[2],
                "connection": row[3], "query_template": row[4],
                "priority": row[5], "is_active": bool(row[6]),
                "use_llm": bool(row[7]), "llm_description": row[8] or "",
            })
        return rules


async def load_alert_rules() -> list[dict]:
    """Carrega regras de alerta ativas do banco."""
    import json
    from src.db import engine
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, name, description, connection_name, query, column_name, "
                 "condition, threshold, schedule_type, interval_minutes, cron_expr, "
                 "channels, message_template, is_active, last_checked_at, "
                 "last_triggered_at, last_value, created_at "
                 "FROM alert_rules WHERE is_active = 1")
        )
        alert_rules = []
        for row in result:
            alert_rules.append({
                "id": row[0], "name": row[1], "description": row[2],
                "connection_name": row[3], "query": row[4], "column_name": row[5],
                "condition": row[6], "threshold": row[7], "schedule_type": row[8],
                "interval_minutes": row[9], "cron_expr": row[10],
                "channels": json.loads(row[11]) if isinstance(row[11], str) else row[11],
                "message_template": row[12], "is_active": bool(row[13]),
                "last_checked_at": row[14], "last_triggered_at": row[15],
                "last_value": row[16],
            })
        return alert_rules


async def load_connections() -> list[dict]:
    """Carrega conexões do banco."""
    import json
    from src.db import engine
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, name, db_type, config FROM db_connections")
        )
        conns = []
        for row in result:
            cfg = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            conns.append({"id": row[0], "name": row[1], "db_type": row[2], "config": cfg})
        return conns


async def load_channels() -> list[dict]:
    """Carrega canais do banco."""
    import json
    from src.db import engine
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, name, channel_type, config FROM channels")
        )
        channels = []
        for row in result:
            cfg = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            channels.append({"id": row[0], "name": row[1], "channel_type": row[2], "config": cfg})
        return channels


async def load_llm_providers() -> list[dict]:
    """Carrega provedores LLM do banco."""
    from src.db import engine
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT provider, model, api_key, api_base, max_tokens, temperature "
                 "FROM llm_providers WHERE is_active = true")
        )
        providers = []
        for row in result:
            providers.append({
                "provider": row[0], "model": row[1], "api_key": row[2],
                "api_base": row[3], "max_tokens": row[4], "temperature": row[5],
            })
        return providers
