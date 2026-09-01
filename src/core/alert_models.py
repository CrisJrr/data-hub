"""
Models de alertas e polling automático de bancos de dados.
"""
from sqlalchemy import (
    Column, String, Integer, DateTime, JSON, Text, Boolean, Float
)
from datetime import datetime, timezone
from src.core.models import Base


class AlertRule(Base):
    """Regra de alerta — define o que monitorar e quando."""
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")

    # Configuração da query
    connection_name = Column(String(100), nullable=False)  # qual DB consultar
    query = Column(Text, nullable=False)                    # SQL a executar
    column_name = Column(String(100), default="")           # coluna para avaliar (vazio = contagem)

    # Condição de alerta
    condition = Column(String(20), nullable=False)  # gt, lt, eq, neq, gte, lte
    threshold = Column(Float, nullable=False)        # valor de referência

    # Agendamento (cron simplificado)
    schedule_type = Column(String(20), nullable=False)  # interval, cron
    interval_minutes = Column(Integer, default=5)        # para schedule_type=interval
    cron_expr = Column(String(100), default="")          # para schedule_type=cron (futuro)

    # Canais de notificação
    channels = Column(JSON, nullable=False)  # ["telegram", "whatsapp", ...]
    message_template = Column(Text, default="🚨 Alerta: {name}\n\n{result}")

    # Estado
    is_active = Column(Boolean, default=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_triggered_at = Column(DateTime, nullable=True)
    last_value = Column(Float, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AlertHistory(Base):
    """Histórico de execuções de alertas."""
    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, nullable=False, index=True)
    executed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Resultado da execução
    triggered = Column(Boolean, nullable=False)   # True se atingiu threshold
    query_result = Column(JSON, nullable=True)     # resultado bruto da query
    value = Column(Float, nullable=True)           # valor avaliado
    message = Column(Text, default="")             # mensagem enviada
    error = Column(Text, default="")               # erro se query falhou
    notifications_sent = Column(JSON, default="[]") # canais notificados
