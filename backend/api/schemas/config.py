from pydantic import BaseModel


class ProvidersOut(BaseModel):
    preferred_llm_provider: str
    llm_suggestions_enabled: bool
    anthropic_configured: bool
    anthropic_key_preview: str | None  # masked: sk-…XYZ
    gemini_configured: bool
    gemini_key_preview: str | None


class ProvidersUpdate(BaseModel):
    anthropic_api_key: str | None = None  # full key on save; "" clears
    gemini_api_key: str | None = None
    preferred_llm_provider: str | None = None
    llm_suggestions_enabled: bool | None = None
