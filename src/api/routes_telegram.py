from fastapi import APIRouter, Depends
from src.api.auth import get_current_user
from src.config import settings
import src.state as state
from src.logging_config import get_logger

router = APIRouter(tags=["telegram"])
logger = get_logger("datahub.telegram_api")


@router.post("/telegram/start")
async def start_telegram_polling(user=Depends(get_current_user)):
    if state._telegram_task and not state._telegram_task.done():
        return {"status": "already_running", "message": "Telegram polling ja esta ativo"}

    if not settings.telegram_bot_token:
        return {"status": "error", "message": "TELEGRAM_BOT_TOKEN nao configurado no .env"}

    import asyncio
    from src.channels.telegram_receiver import HubTelegramLoop

    state._telegram_loop = HubTelegramLoop(settings.telegram_bot_token, poll_interval=2.0)
    state._telegram_task = asyncio.create_task(state._telegram_loop.start())

    return {"status": "started", "message": "Telegram polling iniciado"}


@router.post("/telegram/stop")
async def stop_telegram_polling(user=Depends(get_current_user)):
    if not state._telegram_loop:
        return {"status": "not_running", "message": "Telegram polling nao esta ativo"}

    state._telegram_loop.stop()
    if state._telegram_task and not state._telegram_task.done():
        state._telegram_task.cancel()

    state._telegram_task = None
    state._telegram_loop = None

    return {"status": "stopped", "message": "Telegram polling parado"}


@router.get("/telegram/status")
async def telegram_status(user=Depends(get_current_user)):
    running = state._telegram_task is not None and not state._telegram_task.done()
    return {
        "polling": running,
        "token_configured": bool(settings.telegram_bot_token),
    }
