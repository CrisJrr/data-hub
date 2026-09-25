from fastapi import APIRouter, Request
from src.logging_config import get_logger

router = APIRouter(tags=["whatsapp"])
logger = get_logger("datahub.whatsapp_api")


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
