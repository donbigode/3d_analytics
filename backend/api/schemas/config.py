from pydantic import BaseModel


class ProvidersOut(BaseModel):
    preferred_llm_provider: str
    llm_suggestions_enabled: bool
    digest_auto_enabled: bool
    anthropic_configured: bool
    anthropic_key_preview: str | None  # masked: sk-…XYZ
    gemini_configured: bool
    gemini_key_preview: str | None
    openai_configured: bool
    openai_key_preview: str | None
    # Mercado Livre OAuth credentials
    meli_configured: bool
    meli_app_id_preview: str | None
    meli_secret_preview: str | None
    meli_token_active: bool  # True if access_token present and not expired
    # Reddit OAuth credentials
    reddit_configured: bool
    reddit_client_id_preview: str | None
    reddit_secret_preview: str | None
    reddit_token_active: bool
    youtube_configured: bool
    youtube_key_preview: str | None


class ProvidersUpdate(BaseModel):
    anthropic_api_key: str | None = None  # full key on save; "" clears
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    preferred_llm_provider: str | None = None
    llm_suggestions_enabled: bool | None = None
    digest_auto_enabled: bool | None = None
    meli_app_id: str | None = None
    meli_client_secret: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    youtube_api_key: str | None = None
