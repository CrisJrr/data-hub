"""WhatsApp message receiver via Evolution API v2.

In v2.3.7, /chat/findChats no longer includes lastMessage in chat objects,
so polling chats won't give us new messages. Instead, we use a webhook-based
approach: Evolution API pushes events to our /whatsapp/webhook endpoint.

This module provides:
  - Webhook event handler (called from the FastAPI webhook route)
  - Polling fallback using findChats for chat list monitoring
"""
import asyncio
import logging
import httpx
from src.channels.base import Message
from src.core.hub import hub
from src.api.routes_messages import format_answer
from src.core.intent_engine import intent_engine

logger = logging.getLogger(__name__)

# Track last processed message timestamp to avoid duplicates
_last_message_time: dict[str, str] = {}


async def _format_whatsapp_response(answer) -> str:
    """Format intent result for WhatsApp."""
    if hasattr(answer, 'result') and answer.result:
        result = answer.result
        if hasattr(result, 'to_text'):
            text = result.to_text()
            # Clean up pipe separators
            lines = text.split('\n')
            cleaned = []
            for line in lines:
                if line.strip() and not all(c in '|-─' for c in line.strip()):
                    cleaned.append(line.strip())
            return '\n'.join(cleaned) if cleaned else str(text)
    return format_answer(answer)


async def handle_webhook_event(event: dict):
    """Process an Evolution API webhook event for messages.

    Called from the /whatsapp/webhook route when Evolution API pushes
    message events (upsert, update, etc.).
    """
    event_type = event.get("event", "")
    instance = event.get("instance", "")
    data = event.get("data", {})

    # Only process incoming messages (upsert = new/updated message)
    if event_type not in ("messages.upsert",):
        return

    # Skip bot's own messages
    key = data.get("key", {})
    if key.get("fromMe", False):
        return

    msg_text = data.get("message", {}).get("conversation") or \
               data.get("message", {}).get("extendedTextMessage", {}).get("text", "")
    msg_from = key.get("remoteJid", "")
    msg_time = data.get("messageTimestamp", 0)

    if not msg_text or not msg_from:
        return

    # Check if we already processed this message
    last_time = _last_message_time.get(msg_from, 0)
    if msg_time <= last_time:
        return
    _last_message_time[msg_from] = msg_time

    logger.info(f"WhatsApp message from {msg_from}: {msg_text[:50]}...")

    # Process through intent engine
    try:
        result = await intent_engine.process(msg_text)
        response = await _format_whatsapp_response(result)

        # Send response back
        api_url = "http://evolution:8080"
        api_key = ""
        try:
            # Try to get config from channel registry
            from src.channels.registry import channel_registry
            wa_channel = channel_registry.get("whatsapp")
            if wa_channel:
                api_url = wa_channel.base_url
                api_key = wa_channel.api_key
        except Exception:
            pass

        if api_key:
            async with httpx.AsyncClient() as send_client:
                await send_client.post(
                    f"{api_url}/message/sendText/{instance}",
                    headers={"apikey": api_key, "Content-Type": "application/json"},
                    json={
                        "number": msg_from,
                        "text": response,
                    },
                )
            logger.info(f"WhatsApp response sent to {msg_from}")

    except Exception as e:
        logger.error(f"Error processing WhatsApp message: {e}")


async def poll_whatsapp(channel_config: dict, interval: int = 30):
    """Poll WhatsApp for new chats via Evolution API v2.

    NOTE: In v2.3.7, findChats no longer returns lastMessage.
    This polling monitors chat list changes. For actual message
    reception, configure webhooks on the Evolution API instance.
    """
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
                # v2.3.7: POST /chat/findChats/{instance} with body
                resp = await client.post(
                    f"{base_url}/chat/findChats/{instance}",
                    headers={"apikey": api_key, "Content-Type": "application/json"},
                    json={"limit": 50, "offset": 0},
                )

                if resp.status_code == 200:
                    data = resp.json()
                    # v2 response: {"chats": [...], "total": N}
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
