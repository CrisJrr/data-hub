from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Configurações do Data Hub carregadas de variáveis de ambiente / .env"""

    # Hub internals
    database_url: str = Field(default="sqlite+aiosqlite:///./data/hub.db")
    redis_url: str = Field(default="redis://localhost:6379/0")

    # LLM (LiteLLM)
    llm_model: str = Field(default="openai/gpt-4o-mini")
    llm_enabled: bool = Field(default=True)
    llm_api_base: str = Field(default="")
    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")

    # Telegram
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: int = Field(default=0)

    # WhatsApp (Evolution API)
    whatsapp_api_url: str = Field(default="http://localhost:8080")
    whatsapp_api_key: str = Field(default="")
    whatsapp_instance: str = Field(default="hub")

    # JWT Auth
    jwt_secret_key: str = Field(default="data-hub-super-secret-change-in-production-2024")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=1440)  # 24 hours

    # Logging
    log_level: str = Field(default="INFO")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
