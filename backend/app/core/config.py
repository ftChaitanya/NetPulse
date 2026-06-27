from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./netpulse.db"
    redis_url: str = "redis://localhost:6379/0"
    app_name: str = "NetPulse Campus Backend"

    model_config = {
        "env_file": ".env",
    }


settings = Settings()
