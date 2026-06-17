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


class ExportConfigOut(BaseModel):
    enabled: bool
    destination: str
    s3_bucket: str | None
    s3_region: str | None
    s3_prefix: str | None
    s3_access_key_id: str | None
    s3_secret_configured: bool
    s3_secret_access_key_preview: str | None
    databricks_host: str | None
    databricks_volume_path: str | None
    databricks_token_configured: bool
    databricks_token_preview: str | None
    last_run_at: str | None
    last_run_status: str | None
    last_run_detail: str | None


class ExportConfigUpdate(BaseModel):
    enabled: bool | None = None
    destination: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_prefix: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    databricks_host: str | None = None
    databricks_token: str | None = None
    databricks_volume_path: str | None = None
