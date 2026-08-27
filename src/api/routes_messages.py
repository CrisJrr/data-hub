"""Envio de mensagens via Intent Engine."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    message: str                          # texto do usuário
    channel: Optional[str] = None         # canal de resposta (telegram/whatsapp)
    recipient: Optional[str] = None       # chat_id ou número
    connection: Optional[str] = None      # DB específico (opcional)


class IntentResponse(BaseModel):
    success: bool
    method: str
    query: str
    answer: str
    latency_ms: float
    rule_name: str = ""
    error: str = ""


@router.post("/ask", response_model=IntentResponse)
async def ask(req: SendMessageRequest):
    """
    Processa uma mensagem via Intent Engine.
    1. Tenta Regex (grátis, rápido)
    2. Fallback LLM (interpreta e gera SQL)
    Retorna a resposta formatada.
    """
    from src.core.hub import hub
    from src.core.intent_engine import IntentEngine
    from src.core.models import IntentRule

    # Carrega regras do registry
    rules_data = list(hub.rules.list_all().values())

    engine = IntentEngine(rules=rules_data, llm_enabled=True)
    result = await engine.process(req.message, target_connection=req.connection)

    if result.success and result.result:
        answer = result.result.to_text()
    elif result.error:
        answer = f"Erro: {result.error}"
    else:
        answer = "Não consegui processar essa pergunta."

    # Loga no banco (simplificado)
    # TODO: persistir em MessageLog via SQLAlchemy

    return IntentResponse(
        success=result.success,
        method=result.method,
        query=result.query,
        answer=answer,
        latency_ms=result.latency_ms,
        rule_name=result.rule_name,
        error=result.error,
    )


@router.post("/send")
async def send_message(channel: str, recipient: str, content: str):
    """Envia mensagem via canal específico."""
    from src.core.hub import hub
    from src.channels.telegram import TelegramChannel
    from src.channels.whatsapp import WhatsAppChannel
    from src.channels.base import Message

    if not hub.channels.exists(channel):
        raise HTTPException(404, f"Canal '{channel}' não registrado")

    config = hub.channels.get(channel)
    channel_type = config.get("channel_type", channel)

    channel_map = {"telegram": TelegramChannel, "whatsapp": WhatsAppChannel}
    cls = channel_map.get(channel_type)
    if not cls:
        raise HTTPException(400, f"Tipo '{channel_type}' não suportado")

    instance = cls(config)
    msg = Message(recipient=recipient, content=content, channel=channel_type)
    sent = await instance.send(msg)

    return {"sent": sent, "channel": channel, "recipient": recipient}
