"""
Alert Engine — avaliação de condições e envio de notificações.

Compara resultados de queries com thresholds e dispara alertas
quando as condições são atingidas.
"""
import json
from datetime import datetime, timezone
from typing import Any, Optional
from src.logging_config import get_logger

logger = get_logger("datahub.alerts")

# Operadores de comparação
OPERATORS = {
    "gt": lambda val, thr: val > thr,      # maior que
    "lt": lambda val, thr: val < thr,      # menor que
    "gte": lambda val, thr: val >= thr,    # maior ou igual
    "lte": lambda val, thr: val <= thr,    # menor ou igual
    "eq": lambda val, thr: val == thr,     # igual
    "neq": lambda val, thr: val != thr,    # diferente
}

OPERATOR_LABELS = {
    "gt": ">",
    "lt": "<",
    "gte": ">=",
    "lte": "<=",
    "eq": "=",
    "neq": "≠",
}


def evaluate_condition(value: float, condition: str, threshold: float) -> bool:
    """Avalia se o valor atende a condição."""
    op = OPERATORS.get(condition)
    if not op:
        logger.warning("invalid_condition", extra={"extra_data": {"condition": condition}})
        return False
    return op(value, threshold)


def extract_value(query_result, column_name: str) -> Optional[float]:
    """
    Extrai o valor numérico do resultado de uma query.

    Aceita QueryResult ou dict com formato:
    {"columns": [...], "rows": [{...}], "row_count": N}
    """
    # Suporta tanto QueryResult quanto dict
    if hasattr(query_result, 'rows'):
        rows = query_result.rows
    elif isinstance(query_result, dict):
        rows = query_result.get("rows", [])
    else:
        return None

    if not rows:
        return None

    row = rows[0]

    if column_name and column_name in row:
        # Valor específico de uma coluna
        val = row[column_name]
    elif len(row) == 1:
        # Primeira (e única) coluna
        val = list(row.values())[0]
    else:
        # Fallback: primeira coluna
        val = list(row.values())[0]

    try:
        return float(val)
    except (TypeError, ValueError):
        logger.warning("non_numeric_value", extra={"extra_data": {"value": val, "column": column_name}})
        return None


def format_alert_message(
    rule: dict,
    value: float,
    query_result,
    triggered: bool,
) -> str:
    """Formata a mensagem de alerta."""
    op_label = OPERATOR_LABELS.get(rule.get("condition", "gt"), "?")
    threshold = rule.get("threshold", 0)

    if triggered:
        status = "🔴 ALERTA ATIVADO"
    else:
        status = "🟢 Alerta normalizado"

    lines = [
        f"{status}: {rule['name']}",
        "",
        f"Valor atual: {value}",
        f"Condição: {value} {op_label} {threshold}",
        f"Conexão: {rule.get('connection_name', '?')}",
        f"Query: {rule.get('query', '?')[:100]}",
        "",
        f"Hora: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
    ]

    # Adicionar resultado da query se disponível
    # Suporta tanto QueryResult quanto dict
    if hasattr(query_result, 'rows'):
        rows = query_result.rows
    elif isinstance(query_result, dict):
        rows = query_result.get("rows", [])
    else:
        rows = []

    if rows and len(rows) <= 5:
        lines.append("")
        lines.append("Resultado:")
        for i, row in enumerate(rows[:5]):
            lines.append(f"  {i+1}. {row}")

    return "\n".join(lines)
