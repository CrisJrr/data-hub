"""Envio de mensagens via Intent Engine."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from src.api.auth import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    message: str                          # texto do usuario
    channel: Optional[str] = None         # canal de resposta (telegram/whatsapp)
    recipient: Optional[str] = None       # chat_id ou numero
    connection: Optional[str] = None      # DB especifico (opcional)


class IntentResponse(BaseModel):
    success: bool
    method: str
    query: str
    answer: str
    latency_ms: float
    rule_name: str = ""
    error: str = ""


def format_answer(result) -> str:
    """Formata resposta do Intent Engine de forma legivel."""
    if not result.success:
        if result.error:
            return f"Erro: {result.error}"
        return "Nao consegui processar essa pergunta."

    if not result.result or not result.result.rows:
        return "Nenhum resultado encontrado."

    rows = result.result.rows
    cols = result.result.columns

    lines = []

    # Se poucos registros, formata como lista
    if len(rows) <= 10 and len(cols) <= 4:
        for row in rows:
            parts = []
            for c in cols:
                val = row.get(c, "")
                parts.append(f"{c}: {val}")
            lines.append(" | ".join(parts))
    else:
        # Tabela compacta
        header_line = " / ".join(cols)
        lines.append(header_line)
        lines.append("-" * max(len(header_line), 10))
        for row in rows:
            vals = [str(row.get(c, "")) for c in cols]
            lines.append(" | ".join(vals))

    lines.append(f"\n({len(rows)} registros)")

    return "\n".join(lines)


@router.post("/ask", response_model=IntentResponse)
async def ask(req: SendMessageRequest, user=Depends(get_current_user)):
    """
    Processa uma mensagem via Intent Engine.
    1. Tenta Regex (gratis, rapido)
    2. Fallback LLM (interpreta e gera SQL)
    Retorna a resposta formatada.
    """
    from src.core.hub import hub
    from src.core.intent_engine import IntentEngine

    # Carrega regras do registry
    rules_data = list(hub.rules.list_all().values())

    engine = IntentEngine(rules=rules_data, llm_enabled=True)
    result = await engine.process(req.message, target_connection=req.connection)

    answer = format_answer(result)

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
async def send_message(channel: str, recipient: str, content: str, user=Depends(get_current_user)):
    """Envia mensagem via canal especifico."""
    from src.core.hub import hub
    from src.channels.telegram import TelegramChannel
    from src.channels.whatsapp import WhatsAppChannel
    from src.channels.base import Message

    if not hub.channels.exists(channel):
        raise HTTPException(404, f"Canal '{channel}' nao registrado")

    config = hub.channels.get(channel)
    channel_type = config.get("channel_type", channel)

    channel_map = {"telegram": TelegramChannel, "whatsapp": WhatsAppChannel}
    cls = channel_map.get(channel_type)
    if not cls:
        raise HTTPException(400, f"Tipo '{channel_type}' nao suportado")

    instance = cls(config)
    msg = Message(recipient=recipient, content=content, channel=channel_type)
    sent = await instance.send(msg)

    return {"sent": sent, "channel": channel, "recipient": recipient}
