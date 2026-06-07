from decimal import Decimal
from pydantic import BaseModel


class SettingsIn(BaseModel):
    energy_kwh_price: Decimal | None = None
    printer_power_w: Decimal | None = None
    printer_depreciation_per_hour: Decimal | None = None
    currency: str | None = None
    business_name: str | None = None
    business_tagline: str | None = None
    brand_color_primary: str | None = None
    stalled_quote_alert_days: int | None = None
    low_spool_threshold_g: Decimal | None = None
    printer_hours_per_day: int | None = None


class SettingsOut(BaseModel):
    energy_kwh_price: Decimal
    printer_power_w: Decimal
    printer_depreciation_per_hour: Decimal
    currency: str
    business_name: str
    business_tagline: str | None
    logo_path: str | None
    brand_color_primary: str
    stalled_quote_alert_days: int
    low_spool_threshold_g: Decimal
    printer_hours_per_day: int
