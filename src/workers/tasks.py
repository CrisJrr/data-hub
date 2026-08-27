"""Workers de polling e envio de mensagens."""
from src.workers.celery_app import celery


@celery.task(name="poll_database")
def poll_database(connection_name: str, query: str, channel: str, recipient: str):
    """
    Polling de database: executa query periodicamente
    e envia resultado via canal se houver mudança.
    """
    import asyncio
    from src.core.hub import hub
    from src.adapters import get_adapter

    async def _poll():
        if not hub.adapters.exists(connection_name):
            return {"error": f"Conexão '{connection_name}' não encontrada"}

        config = hub.adapters.get(connection_name)
        adapter = get_adapter(config["db_type"], config)
        await adapter.connect()
        result = await adapter.execute(query)
        await adapter.disconnect()
        return {"rows": result.row_count, "data": result.to_text()}

    result = asyncio.get_event_loop().run_until_complete(_poll())
    return result


@celery.task(name="send_notification")
def send_notification(channel: str, recipient: str, content: str):
    """Envia notificação via canal."""
    import asyncio
    from src.core.hub import hub
    from src.channels.base import Message
    from src.channels.telegram import TelegramChannel
    from src.channels.whatsapp import WhatsAppChannel

    async def _send():
        if not hub.channels.exists(channel):
            return {"error": f"Canal '{channel}' não encontrado"}

        config = hub.channels.get(channel)
        channel_type = config.get("channel_type", channel)
        channel_map = {"telegram": TelegramChannel, "whatsapp": WhatsAppChannel}
        cls = channel_map.get(channel_type)
        if not cls:
            return {"error": f"Tipo '{channel_type}' não suportado"}

        instance = cls(config)
        msg = Message(recipient=recipient, content=content, channel=channel_type)
        sent = await instance.send(msg)
        return {"sent": sent}

    return asyncio.get_event_loop().run_until_complete(_send())
