"""Google Chat webhook receiver for incoming messages."""
import asyncio
from src.logging_config import get_logger
from fastapi import APIRouter, Request
from src.channels.google_chat import GoogleChatChannel
from src.core.intent_engine import intent_engine
from src.api.routes_messages import format_answer

logger = get_logger("datahub.google_chat")

router = APIRouter()

# Store active channel configs
_active_channels: dict[str, GoogleChatChannel] = {}


@router.post("/google-chat/webhook")
async def google_chat_webhook(request: Request):
    """Handle incoming Google Chat webhook events."""
    try:
        data = await request.json()
        
        # Verify this is a message event
        event_type = data.get("type")
        if event_type != "MESSAGE":
            return {"status": "ignored"}
        
        # Extract message details
        message = data.get("message", {})
        text = message.get("text", "")
        space = message.get("space", {}).get("name", "")
        sender = message.get("sender", {}).get("name", "")
        
        # Remove bot mention if present
        if text.startswith("<bot>"):
            text = text[4:].strip()
        
        logger.info(f"Google Chat message in {space}: {text[:50]}...")
        
        # Process through intent engine
        result = await intent_engine.process(text)
        response = format_answer(result)
        
        # Send response back
        channel = _active_channels.get(space)
        if channel:
            from src.channels.base import Message
            await channel.send(Message(
                recipient=space,
                content=response,
                channel="google_chat",
            ))
        
        # Return response for webhook
        return {"text": response}
        
    except Exception as e:
        logger.error(f"Google Chat webhook error: {e}")
        return {"text": f"Erro: {str(e)}"}


def register_channel(space_name: str, channel: GoogleChatChannel):
    """Register a Google Chat channel for webhook handling."""
    _active_channels[space_name] = channel
    logger.info(f"Google Chat channel registered for space: {space_name}")


def unregister_channel(space_name: str):
    """Unregister a Google Chat channel."""
    _active_channels.pop(space_name, None)
    logger.info(f"Google Chat channel unregistered for space: {space_name}")
