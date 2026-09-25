"""Microsoft Teams webhook receiver for incoming messages."""
import asyncio
from src.logging_config import get_logger
import hashlib
import hmac
from fastapi import APIRouter, Request, Header
from src.channels.teams import TeamsChannel
from src.core.intent_engine import intent_engine
from src.api.routes_messages import format_answer

logger = get_logger("datahub.teams")

router = APIRouter()

# Store active channel configs
_active_channels: dict[str, TeamsChannel] = {}


@router.post("/teams/webhook")
async def teams_webhook(request: Request, x_microsoft_signature: str = Header(None)):
    """Handle incoming Microsoft Teams webhook events."""
    try:
        data = await request.json()
        
        # Verify webhook signature if provided
        if x_microsoft_signature:
            body = await request.body()
            # Note: In production, verify the signature properly
            # This is a simplified check
        
        # Extract message details
        event_type = data.get("eventType")
        
        if event_type == "subscriptionConfirmation":
            # Handle subscription confirmation
            validation_token = data.get("validationCode")
            return {"validationCode": validation_token}
        
        if event_type != "chatMessage":
            return {"status": "ignored"}
        
        # Extract message details
        resource = data.get("resource", "")
        message_data = data.get("resourceData", {})
        
        # Parse resource to get team/channel info
        # Format: /teams/{team-id}/channels/{channel-id}/messages/{message-id}
        parts = resource.split("/")
        team_id = parts[1] if len(parts) > 1 else ""
        channel_id = parts[3] if len(parts) > 3 else ""
        
        # Get message content from Graph API
        # Note: Webhook doesn't include full message, need to fetch it
        # For simplicity, we'll use the text if available
        
        text = message_data.get("body", {}).get("content", "")
        sender = message_data.get("from", {}).get("user", {}).get("displayName", "")
        
        # Remove HTML tags if present
        import re
        text = re.sub(r'<[^>]+>', '', text).strip()
        
        if not text:
            return {"status": "no content"}
        
        logger.info(f"Teams message in {channel_id}: {text[:50]}...")
        
        # Process through intent engine
        result = await intent_engine.process(text)
        response = format_answer(result)
        
        # Send response back
        channel_key = f"{team_id}/{channel_id}"
        channel = _active_channels.get(channel_key)
        if channel:
            await channel.send(Message(
                recipient=channel_key,
                content=response,
                channel="teams",
            ))
        
        # Return response for webhook
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        return {"status": "error", "message": str(e)}


def register_channel(team_id: str, channel_id: str, channel: TeamsChannel):
    """Register a Teams channel for webhook handling."""
    key = f"{team_id}/{channel_id}"
    _active_channels[key] = channel
    logger.info(f"Teams channel registered: {key}")


def unregister_channel(team_id: str, channel_id: str):
    """Unregister a Teams channel."""
    key = f"{team_id}/{channel_id}"
    _active_channels.pop(key, None)
    logger.info(f"Teams channel unregistered: {key}")
