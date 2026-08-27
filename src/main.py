from fastapi import FastAPI
from contextlib import asynccontextmanager
from src.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    import os
    # Cria diretório de dados se não existir
    os.makedirs("data", exist_ok=True)

    # Inicializa DB interno (SQLite)
    from sqlalchemy.ext.asyncio import create_async_engine
    from src.core.models import Base
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print(f"[Data Hub] DB interno pronto: {settings.database_url}")
    yield
    print("[Data Hub] Shutting down...")


app = FastAPI(
    title="Data Hub",
    version="0.1.0",
    description="Multi-database hub com motor de intenção Regex + LLM",
    lifespan=lifespan,
)


# Registra todas as rotas
from src.api import routes_connections, routes_channels, routes_rules, routes_messages, routes_query

app.include_router(routes_connections.router)
app.include_router(routes_channels.router)
app.include_router(routes_rules.router)
app.include_router(routes_messages.router)
app.include_router(routes_query.router)


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
    }


@app.get("/")
async def root():
    """Info básica do hub."""
    return {
        "name": "Data Hub",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
