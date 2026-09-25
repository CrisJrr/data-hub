"""WhatsApp message receiver via Evolution API v2.

In v2.3.7, /chat/findChats no longer includes lastMessage in chat objects,
so polling chats won't give us new messages. Instead, we use a webhook-based
approach: Evolution API pushes events to our /whatsapp/webhook endpoint.
"""
import asyncio
import json
import logging
import httpx
from src.channels.base import Message
from src.core.hub import hub
from src.api.routes_messages import format_answer
from src.logging_config import get_logger

logger = get_logger("datahub.whatsapp")

# Track last processed message timestamp to avoid duplicates
_last_message_time: dict[str, str] = {}


# ── Parsing ──────────────────────────────────────────────────────────────────


def _parse_webhook_event(event: dict) -> dict | None:
    """Extrai dados relevantes de um evento webhook.

    Returns dict with keys: text, from, timestamp, instance
    or None if the event should be ignored.
    """
    event_type = event.get("event", "")
    if event_type not in ("messages.upsert",):
        return None

    data = event.get("data", {})
    key = data.get("key", {})

    if key.get("fromMe", False):
        return None

    text = (
        data.get("message", {}).get("conversation")
        or data.get("message", {}).get("extendedTextMessage", {}).get("text", "")
    )
    sender = key.get("remoteJid", "")
    timestamp = data.get("messageTimestamp", 0)

    if not text or not sender:
        return None

    return {
        "text": text,
        "from": sender,
        "timestamp": timestamp,
        "instance": event.get("instance", ""),
    }


# ── Permissão ────────────────────────────────────────────────────────────────


async def _is_recipient_allowed(msg_from: str) -> bool:
    """Verifica se o destinatário pode receber mensagens.

    Modo whitelist: só envia pra números na lista (ou qualquer um se lista vazia)
    Modo blocklist: envia pra todos EXCETO números na lista
    """
    from src.db import async_session
    from sqlalchemy import text

    try:
        async with async_session() as session:
            # Modo atual
            result = await session.execute(
                text("SELECT value FROM app_settings WHERE key = 'whatsapp_mode'")
            )
            row = result.fetchone()
            mode = row[0] if row else "blocklist"

            # Política padrão
            result2 = await session.execute(
                text("SELECT value FROM app_settings WHERE key = 'whatsapp_default_policy'")
            )
            row2 = result2.fetchone()
            default_policy = row2[0] if row2 else "allow"

            # Verificar se o número está na lista
            result3 = await session.execute(
                text("SELECT id, is_active FROM whatsapp_recipients WHERE number = :num"),
                {"num": msg_from}
            )
            recipient = result3.fetchone()

            if recipient is None:
                if mode == "whitelist":
                    result4 = await session.execute(
                        text("SELECT COUNT(*) FROM whatsapp_recipients WHERE list_type = 'whitelist' AND is_active = true")
                    )
                    count = result4.fetchone()[0]
                    if count == 0:
                        return True  # Lista vazia, permite tudo
                    return default_policy == "allow"
                else:
                    return default_policy == "allow"
            else:
                is_active = recipient[1]
                if mode == "whitelist":
                    return is_active
                else:
                    return not is_active
    except Exception as e:
        logger.error(f"Error checking recipient permission: {e}")
        return False


# ── Formatação ───────────────────────────────────────────────────────────────


async def _format_whatsapp_response(answer) -> str:
    """Format intent result for WhatsApp."""
    if hasattr(answer, 'result') and answer.result:
        result = answer.result
        if hasattr(result, 'to_text'):
            text = result.to_text()
            lines = text.split('\n')
            cleaned = [line.strip() for line in lines if line.strip() and not all(c in '|-─' for c in line.strip())]
            return '\n'.join(cleaned) if cleaned else str(text)
    return format_answer(answer)


# ── Envio ────────────────────────────────────────────────────────────────────


async def _send_whatsapp_response(msg_from: str, response: str, instance: str):
    """Envia resposta via Evolution API."""
    api_url = "http://evolution:8080"
    api_key = ""

    try:
        wa_config = hub.channels.get("whatsapp-evolution")
        if wa_config:
            cfg = wa_config.get("config", {})
            api_url = cfg.get("api_url", api_url)
            api_key = cfg.get("api_key", "")
    except Exception:
        pass

    if not api_key:
        from src.config import settings
        api_url = settings.whatsapp_api_url or api_url
        api_key = settings.whatsapp_api_key or ""

    if not api_key:
        logger.warning("WhatsApp: no API key configured, cannot send response")
        return

    try:
        async with httpx.AsyncClient() as send_client:
            resp = await send_client.post(
                f"{api_url}/message/sendText/{instance}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": msg_from, "text": response},
            )
            logger.info(f"WhatsApp response sent: status={resp.status_code}")
    except Exception as e:
        logger.error(f"Failed to send WhatsApp response: {e}")


# ── Handler principal ────────────────────────────────────────────────────────


async def handle_webhook_event(event: dict):
    """Processa um evento webhook do Evolution API."""
    parsed = _parse_webhook_event(event)
    if not parsed:
        return

    msg_text = parsed["text"]
    msg_from = parsed["from"]
    msg_time = parsed["timestamp"]
    instance = parsed["instance"]

    # Deduplicação
    last_time = _last_message_time.get(msg_from, 0)
    if msg_time <= last_time:
        return
    _last_message_time[msg_from] = msg_time

    logger.info(f"WhatsApp message from {msg_from}: {msg_text[:50]}...")

    # Verificar permissão
    if not await _is_recipient_allowed(msg_from):
        logger.info(f"WhatsApp message blocked for {msg_from}")
        return

    # Processar via Intent Engine
    try:
        from src.core.intent_engine import IntentEngine
        rules_data = list(hub.rules.list_all().values())
        engine = IntentEngine(rules=rules_data, llm_enabled=True)
        result = await engine.process(msg_text)
        response = await _format_whatsapp_response(result)
        await _send_whatsapp_response(msg_from, response, instance)
    except Exception as e:
        logger.error(f"Error processing WhatsApp message: {e}")


# ── Polling (fallback) ───────────────────────────────────────────────────────


async def poll_whatsapp(channel_config: dict, interval: int = 30):
    """Poll WhatsApp for new chats via Evolution API v2."""
    base_url = channel_config.get("api_url", "http://evolution:8080")
    api_key = channel_config.get("api_key", "")
    instance = channel_config.get("instance", "hub")

    if not api_key:
        logger.warning("WhatsApp: No API key configured, skipping poll")
        return

    logger.info(f"WhatsApp polling started for instance {instance}")

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                resp = await client.post(
                    f"{base_url}/chat/findChats/{instance}",
                    headers={"apikey": api_key, "Content-Type": "application/json"},
                    json={"limit": 50, "offset": 0},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    chats = data.get("chats", []) if isinstance(data, dict) else []
                    logger.debug(f"WhatsApp: {len(chats)} chats found")
            except Exception as e:
                logger.error(f"WhatsApp polling error: {e}")

            await asyncio.sleep(interval)


async def start_whatsapp_polling(channel_config: dict):
    """Start WhatsApp polling in background."""
    task = asyncio.create_task(poll_whatsapp(channel_config))
    return task


async def stop_whatsapp_polling(task):
    """Stop WhatsApp polling."""
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
