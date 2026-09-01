"""
API Routes — CRUD de regras de alerta + histórico.
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from src.db import get_db, engine
from src.api.auth import get_current_user
from src.logging_config import get_logger

logger = get_logger("datahub.alerts_api")

router = APIRouter(prefix="/alerts", tags=["Alerts"])


# ─── Schemas ───
class AlertRuleCreate(BaseModel):
    name: str
    description: str = ""
    connection_name: str
    query: str
    column_name: str = ""
    condition: str = "gt"  # gt, lt, eq, neq, gte, lte
    threshold: float = 0
    schedule_type: str = "interval"
    interval_minutes: int = 5
    cron_expr: str = ""
    channels: list[str] = []
    message_template: str = ""
    is_active: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    connection_name: Optional[str] = None
    query: Optional[str] = None
    column_name: Optional[str] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    schedule_type: Optional[str] = None
    interval_minutes: Optional[int] = None
    cron_expr: Optional[str] = None
    channels: Optional[list[str]] = None
    message_template: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Helpers ───
def _to_dict(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "connection_name": row[3],
        "query": row[4],
        "column_name": row[5],
        "condition": row[6],
        "threshold": row[7],
        "schedule_type": row[8],
        "interval_minutes": row[9],
        "cron_expr": row[10],
        "channels": json.loads(row[11]) if isinstance(row[11], str) else row[11],
        "message_template": row[12],
        "is_active": bool(row[13]),
        "last_checked_at": str(row[14]) if row[14] else None,
        "last_triggered_at": str(row[15]) if row[15] else None,
        "last_value": row[16],
        "created_at": str(row[17]) if row[17] else None,
    }


# ─── Endpoints ───
@router.get("/")
async def list_alerts(user=Depends(get_current_user)):
    """Lista todas as regras de alerta."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT * FROM alert_rules ORDER BY created_at DESC")
        )
        rules = [_to_dict(row) for row in result]
    return rules


@router.post("/")
async def create_alert(rule: AlertRuleCreate, user=Depends(get_current_user)):
    """Cria uma nova regra de alerta."""
    channels_json = json.dumps(rule.channels)

    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                INSERT INTO alert_rules
                (name, description, connection_name, query, column_name,
                 condition, threshold, schedule_type, interval_minutes, cron_expr,
                 channels, message_template, is_active)
                VALUES (:name, :description, :connection_name, :query, :column_name,
                        :condition, :threshold, :schedule_type, :interval_minutes, :cron_expr,
                        :channels, :message_template, :is_active)
                RETURNING id
            """),
            {
                "name": rule.name,
                "description": rule.description,
                "connection_name": rule.connection_name,
                "query": rule.query,
                "column_name": rule.column_name,
                "condition": rule.condition,
                "threshold": rule.threshold,
                "schedule_type": rule.schedule_type,
                "interval_minutes": rule.interval_minutes,
                "cron_expr": rule.cron_expr,
                "channels": channels_json,
                "message_template": rule.message_template,
                "is_active": rule.is_active,
            },
        )
        row = result.fetchone()
        rule_id = row[0]

    # Atualizar scheduler
    from src.core.alert_scheduler import alert_scheduler
    new_rule = {**rule.model_dump(), "id": rule_id, "channels": rule.channels}
    alert_scheduler.add_rule(new_rule)

    logger.info("alert_created", extra={"extra_data": {"rule_id": rule_id, "name": rule.name}})

    return {"id": rule_id, "message": "Regra criada"}


@router.get("/{rule_id}")
async def get_alert(rule_id: int, user=Depends(get_current_user)):
    """Busca uma regra de alerta por ID."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT * FROM alert_rules WHERE id = :id"),
            {"id": rule_id},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    return _to_dict(row)


@router.put("/{rule_id}")
async def update_alert(rule_id: int, update: AlertRuleUpdate, user=Depends(get_current_user)):
    """Atualiza uma regra de alerta."""
    # Buscar regra atual
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT * FROM alert_rules WHERE id = :id"),
            {"id": rule_id},
        )
        current = result.fetchone()

    if not current:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    # Aplicar updates
    updates = update.model_dump(exclude_unset=True)
    if "channels" in updates:
        updates["channels"] = json.dumps(updates["channels"])

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates.keys())
    updates["id"] = rule_id
    updates["updated_at"] = datetime.now(timezone.utc)

    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE alert_rules SET {set_clauses}, updated_at = :updated_at WHERE id = :id"),
            updates,
        )

    # Atualizar scheduler
    from src.core.alert_scheduler import alert_scheduler
    updated_data = _to_dict(current)
    updated_data.update(update.model_dump(exclude_unset=True))
    updated_data["id"] = rule_id
    if "channels" in updated_data and isinstance(updated_data["channels"], str):
        updated_data["channels"] = json.loads(updated_data["channels"])
    alert_scheduler.add_rule(updated_data)

    logger.info("alert_updated", extra={"extra_data": {"rule_id": rule_id}})

    return {"message": "Regra atualizada"}


@router.delete("/{rule_id}")
async def delete_alert(rule_id: int, user=Depends(get_current_user)):
    """Deleta uma regra de alerta."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("DELETE FROM alert_rules WHERE id = :id RETURNING id"),
            {"id": rule_id},
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Regra não encontrada")

    from src.core.alert_scheduler import alert_scheduler
    alert_scheduler.remove_rule(rule_id)

    logger.info("alert_deleted", extra={"extra_data": {"rule_id": rule_id}})

    return {"message": "Regra deletada"}


@router.post("/{rule_id}/test")
async def test_alert(rule_id: int, user=Depends(get_current_user)):
    """Testa uma regra de alerta executando a query manualmente."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT * FROM alert_rules WHERE id = :id"),
            {"id": rule_id},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    rule = _to_dict(row)

    # Executar query
    from src.core.hub import hub
    from src.adapters import get_adapter
    from src.core.alert_engine import evaluate_condition, extract_value, format_alert_message

    config = hub.adapters.get(rule["connection_name"])
    if not config:
        raise HTTPException(status_code=400, detail=f"Conexão '{rule['connection_name']}' não encontrada")

    adapter = get_adapter(config["db_type"], config.get("config", config))
    await adapter.connect()
    query_result = await adapter.execute(rule["query"])
    await adapter.disconnect()

    # Avaliar
    value = extract_value(query_result, rule["column_name"])
    triggered = evaluate_condition(value, rule["condition"], rule["threshold"]) if value is not None else False
    message = format_alert_message(rule, value or 0, query_result, triggered)

    # Converter QueryResult para dict para serialização JSON
    result_dict = {
        "columns": query_result.columns,
        "rows": query_result.rows,
        "row_count": query_result.row_count,
    }

    return {
        "rule_id": rule_id,
        "value": value,
        "triggered": triggered,
        "condition": rule["condition"],
        "threshold": rule["threshold"],
        "query_result": result_dict,
        "message": message,
    }


@router.get("/{rule_id}/history")
async def alert_history(
    rule_id: int,
    limit: int = 50,
    user=Depends(get_current_user),
):
    """Busca histórico de execuções de uma regra."""
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
                SELECT * FROM alert_history
                WHERE rule_id = :rule_id
                ORDER BY executed_at DESC
                LIMIT :limit
            """),
            {"rule_id": rule_id, "limit": limit},
        )
        rows = result.fetchall()

    return [
        {
            "id": row[0],
            "rule_id": row[1],
            "executed_at": str(row[2]) if row[2] else None,
            "triggered": bool(row[3]),
            "query_result": json.loads(row[4]) if isinstance(row[4], str) else row[4],
            "value": row[5],
            "message": row[6],
            "error": row[7],
            "notifications_sent": json.loads(row[8]) if isinstance(row[8], str) else row[8],
        }
        for row in rows
    ]


@router.get("/stats/summary")
async def alert_stats(user=Depends(get_current_user)):
    """Resumo das estatísticas de alertas."""
    async with engine.begin() as conn:
        # Total de regras
        total = await conn.execute(text("SELECT COUNT(*) FROM alert_rules"))
        total_rules = total.scalar()

        # Regras ativas
        active = await conn.execute(text("SELECT COUNT(*) FROM alert_rules WHERE is_active = 1"))
        active_rules = active.scalar()

        # Total de triggers hoje
        today = await conn.execute(text("""
            SELECT COUNT(*) FROM alert_history
            WHERE triggered = 1 AND date(executed_at) = date('now')
        """))
        today_triggers = today.scalar()

        # Total de execuções hoje
        today_executions = await conn.execute(text("""
            SELECT COUNT(*) FROM alert_history
            WHERE date(executed_at) = date('now')
        """))
        today_executions_count = today_executions.scalar()

    return {
        "total_rules": total_rules,
        "active_rules": active_rules,
        "today_triggers": today_triggers,
        "today_executions": today_executions_count,
    }
