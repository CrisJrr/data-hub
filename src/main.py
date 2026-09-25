from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from src.config import settings
from src.logging_config import setup_logging, get_logger
import os
import redis.asyncio as aioredis

# Initialize structured logging
setup_logging(os.getenv("ENVIRONMENT", "production"))
logger = get_logger("datahub.main")

# Telegram polling state (shared module)
import src.state as state

# WebSocket manager
from src.ws import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    os.makedirs("data", exist_ok=True)

    # Inicializa DB interno (SQLite)
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import select
    from src.core.models import Base, IntentRule
    from src.core.alert_models import AlertRule, AlertHistory  # Importar para criar tabelas
    from src.db import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Cria default admin user se não existir
    from src.core.models import User
    from src.api.auth import hash_password
    from sqlalchemy import insert
    async with engine.begin() as conn:
        result = await conn.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            await conn.execute(
                insert(User).values(
                    username="admin",
                    email="admin@datahub.local",
                    hashed_password=hash_password("admin123"),
                    is_active=True,
                )
            )
            logger.info("default_admin_created", extra={"extra_data": {"username": "admin"}})

    # Carrega regras do DB pro hub em memória
    from src.core.hub import hub
    from sqlalchemy import text
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, name, pattern, connection_name, query_template, priority, is_active, use_llm, llm_description FROM intent_rules ORDER BY priority DESC")
        )
        rules = []
        for row in result:
            rule = {
                "id": row[0], "name": row[1], "pattern": row[2],
                "connection": row[3], "query_template": row[4],
                "priority": row[5], "is_active": bool(row[6]),
                "use_llm": bool(row[7]), "llm_description": row[8] or "",
            }
            rules.append(rule)
            hub.rules.register(rule["name"], rule)
    print(f"[Data Hub] DB pronto: {settings.database_url} ({len(rules)} regras carregadas)")

    # Carrega connections do DB
    import json
    from src.core.models import DBConnection, Channel
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id, name, db_type, config FROM db_connections"))
        for row in result:
            cfg = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            hub.adapters.register(row[1], {"id": row[0], "db_type": row[2], "config": cfg})
        result = await conn.execute(text("SELECT id, name, channel_type, config FROM channels"))
        for row in result:
            cfg = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            hub.channels.register(row[1], {"id": row[0], "channel_type": row[2], "config": cfg})

    logger.info("db_ready", extra={"extra_data": {"url": settings.database_url, "rules": len(rules)}})

    # Carregar regras de alerta
    from src.core.alert_scheduler import alert_scheduler
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT id, name, description, connection_name, query, column_name, "
                 "condition, threshold, schedule_type, interval_minutes, cron_expr, "
                 "channels, message_template, is_active, last_checked_at, last_triggered_at, "
                 "last_value, created_at FROM alert_rules WHERE is_active = 1")
        )
        alert_rules = []
        for row in result:
            alert_rules.append({
                "id": row[0], "name": row[1], "description": row[2],
                "connection_name": row[3], "query": row[4], "column_name": row[5],
                "condition": row[6], "threshold": row[7], "schedule_type": row[8],
                "interval_minutes": row[9], "cron_expr": row[10],
                "channels": json.loads(row[11]) if isinstance(row[11], str) else row[11],
                "message_template": row[12], "is_active": bool(row[13]),
                "last_checked_at": row[14], "last_triggered_at": row[15],
                "last_value": row[16],
            })
    alert_scheduler.update_rules(alert_rules)
    await alert_scheduler.start()
    logger.info("alert_scheduler_started", extra={"extra_data": {"rules": len(alert_rules)}})

    # Auto-start Telegram polling se token estiver configurado
    if settings.telegram_bot_token:
        import asyncio
        from src.channels.telegram_receiver import HubTelegramLoop
        state._telegram_loop = HubTelegramLoop(settings.telegram_bot_token, poll_interval=2.0)
        state._telegram_task = asyncio.create_task(state._telegram_loop.start())
        logger.info("telegram_polling_started")

    # Connect to Redis for rate limiting
    _redis_client = None
    try:
        _redis_client = aioredis.from_url(
            settings.redis_url or "redis://redis:6379/0",
            decode_responses=True,
            socket_connect_timeout=3,
        )
        await _redis_client.ping()
        app.state.redis = _redis_client
        logger.info("redis_connected", extra={"extra_data": {"url": settings.redis_url}})
    except Exception as e:
        logger.warning("redis_unavailable", extra={"extra_data": {"error": str(e)}})
        app.state.redis = None

    yield

    # Shutdown
    from src.core.alert_scheduler import alert_scheduler
    alert_scheduler.stop()
    if state._telegram_loop:
        state._telegram_loop.stop()
    if state._telegram_task and not state._telegram_task.done():
        state._telegram_task.cancel()
    if _redis_client:
        await _redis_client.close()
    logger.info("shutdown_complete")


app = FastAPI(
    title="Data Hub",
    version="0.1.0",
    description="Multi-database hub com motor de intencao Regex + LLM",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — Redis client injected via app.state during lifespan
from src.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Request logging
from src.logging_config.request_middleware import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)


# Registra todas as rotas
from src.api import routes_connections, routes_channels, routes_rules, routes_messages, routes_query, routes_auth, routes_alerts, routes_schemas, routes_settings, routes_llm_providers, routes_whatsapp_recipients, routes_whatsapp_status
from src.api.routes_telegram import router as telegram_router
from src.api.routes_whatsapp import router as whatsapp_router

app.include_router(routes_auth.router)
app.include_router(routes_connections.router)
app.include_router(routes_channels.router)
app.include_router(routes_rules.router)
app.include_router(routes_messages.router)
app.include_router(routes_query.router)
app.include_router(routes_alerts.router)
app.include_router(routes_schemas.router)
app.include_router(routes_settings.router)
app.include_router(routes_llm_providers.router)
app.include_router(routes_whatsapp_recipients.router)
app.include_router(routes_whatsapp_status.router)
app.include_router(telegram_router)
app.include_router(whatsapp_router)


@app.get("/health")
async def health():
    """Health check do hub."""
    from src.core.hub import hub
    return {
        "status": "ok",
        "version": "0.1.0",
        "llm_enabled": settings.llm_enabled,
        "llm_model": settings.llm_model,
        "adapters": hub.adapters.list_names(),
        "channels": hub.channels.list_names(),
        "rules": hub.rules.list_names(),
        "telegram_polling": state._telegram_task is not None and not state._telegram_task.done(),
    }


@app.get("/")
async def root():
    """Serve o frontend."""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"name": "Data Hub", "version": "0.1.0", "docs": "/docs"}


@app.get("/about", response_class=FileResponse)
async def about_page():
    """Página de apresentação do projeto."""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    about_path = os.path.join(static_dir, "about.html")
    if os.path.exists(about_path):
        return FileResponse(about_path)
    return {"error": "About page not found"}


# =============================================
# WebSocket Endpoint
# =============================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket para updates em tempo real."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Mantém conexão viva, recebe ping do client
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# Mount static files AFTER routes so API endpoints take priority
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
