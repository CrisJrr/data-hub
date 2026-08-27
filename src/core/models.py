from sqlalchemy import (
    Column, String, Integer, DateTime, JSON, Text, Boolean, Float
)
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone


class Base(DeclarativeBase):
    """Base para todas as tabelas do hub."""
    pass


class DBConnection(Base):
    """Conexões de database registradas no hub."""
    __tablename__ = "db_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    db_type = Column(String(50), nullable=False)  # postgres, mysql, sqlite, mongodb, api_rest
    config = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Channel(Base):
    """Canais de mensageria registrados."""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    channel_type = Column(String(50), nullable=False)  # telegram, whatsapp
    config = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class IntentRule(Base):
    """Regras de intenção (Regex ou LLM)."""
    __tablename__ = "intent_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    pattern = Column(String(500), nullable=False)          # regex pattern
    connection_name = Column(String(100), nullable=False)  # qual DB consultar
    query_template = Column(Text, nullable=False)           # SQL com {placeholders}
    priority = Column(Integer, default=0)                   # maior = primeiro match
    is_active = Column(Boolean, default=True)
    use_llm = Column(Boolean, default=False)                # true = usa LLM em vez de regex
    llm_description = Column(Text, default="")              # descrição pro LLM
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MessageLog(Base):
    """Log de todas as mensagens processadas."""
    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(Integer, nullable=False)
    channel_type = Column(String(50), nullable=False)
    recipient = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    direction = Column(String(10), nullable=False)    # "in" ou "out"
    matched_rule = Column(String(200), default="")
    method = Column(String(20), default="")            # "regex" ou "llm"
    query_used = Column(Text, default="")
    result = Column(Text, default="")
    latency_ms = Column(Float, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
