from fastapi import APIRouter, Request
import logging

router = APIRouter(tags=["whatsapp"])
logger = logging.getLogger(__name__)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """Receive Evolution API webhook events for WhatsApp messages."""
    try:
        payload = await request.json()
        logger.info(f"Webhook received: event={payload.get('event')}, instance={payload.get('instance')}")

        from src.channels.whatsapp_receiver import handle_webhook_event
        await handle_webhook_event(payload)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {"status": "error", "message": str(e)}
