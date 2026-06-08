from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from backend.infra.db.base import Base


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    energy_kwh_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0.95"))
    printer_power_w: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=Decimal("150"))
    printer_depreciation_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    business_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Sua Marca")
    business_tagline: Mapped[str | None] = mapped_column(String(200))
    logo_path: Mapped[str | None] = mapped_column(String(255))
    brand_color_primary: Mapped[str] = mapped_column(String(9), nullable=False, default="#111827")
    stalled_quote_alert_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    low_spool_threshold_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("100"))
    printer_hours_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=22)

    # LLM provider configuration (used by the trend radar to generate keyword
    # suggestions). API keys are stored in plaintext on the singleton row —
    # this DB isn't multi-tenant and the keys are needed in plaintext at call
    # time. GET /settings masks them in the response.
    anthropic_api_key: Mapped[str | None] = mapped_column(String(200))
    gemini_api_key: Mapped[str | None] = mapped_column(String(200))
    openai_api_key: Mapped[str | None] = mapped_column(String(200))
    preferred_llm_provider: Mapped[str] = mapped_column(String(20), nullable=False, default="anthropic")
    llm_suggestions_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Mercado Livre OAuth client_credentials (App-Auth). Public API now
    # requires Bearer auth even for read endpoints. User registers an app at
    # https://developers.mercadolivre.com.br/devcenter to get these.
    meli_app_id: Mapped[str | None] = mapped_column(String(80))
    meli_client_secret: Mapped[str | None] = mapped_column(String(200))
    meli_access_token: Mapped[str | None] = mapped_column(String(400))
    meli_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Reddit OAuth client_credentials. Public /search.json was closed off; you
    # need an app registered at https://www.reddit.com/prefs/apps (type=script).
    reddit_client_id: Mapped[str | None] = mapped_column(String(80))
    reddit_client_secret: Mapped[str | None] = mapped_column(String(200))
    reddit_access_token: Mapped[str | None] = mapped_column(String(400))
    reddit_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
