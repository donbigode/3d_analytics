from pydantic import BaseModel


class ProvidersOut(BaseModel):
    preferred_llm_provider: str
    llm_suggestions_enabled: bool
    anthropic_configured: bool
    anthropic_key_preview: str | None  # masked: sk-…XYZ
    gemini_configured: bool
    gemini_key_preview: str | None
    # Mercado Livre OAuth credentials
    meli_configured: bool
    meli_app_id_preview: str | None
    meli_secret_preview: str | None
    meli_token_active: bool  # True if access_token present and not expired


class ProvidersUpdate(BaseModel):
    anthropic_api_key: str | None = None  # full key on save; "" clears
    gemini_api_key: str | None = None
    preferred_llm_provider: str | None = None
    llm_suggestions_enabled: bool | None = None
    meli_app_id: str | None = None
    meli_client_secret: str | None = None
