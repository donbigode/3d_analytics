from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://app:app@db:5432/app"
    session_secret: str = "change-me-in-prod"
    watch_dir: str | None = None
    storage_dir: str = "/data/storage"
    cors_origins: str = "http://localhost:5173"
    pwd_argon2_time_cost: int = 2
    pwd_argon2_memory_cost: int = 65536


def get_settings() -> AppSettings:
    return AppSettings()
