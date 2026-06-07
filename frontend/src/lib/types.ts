// API response types — mirror backend pydantic schemas, treating decimals as strings/numbers.

export type Client = {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  notes: string | null;
};

export type Material = {
  id: string;
  material_code: string;
  name: string;
  density_g_cm3: number | string;
  price_per_kg_ref: number | string;
  failure_rate_pct: number | string;
  is_current: boolean;
  effective_from: string;
  effective_to: string | null;
};

export type ServiceKind = "labor" | "purge" | "other";
export type ServiceUnit = "min" | "hour" | "g";

export type Service = {
  id: string;
  name: string;
  unit: ServiceUnit;
  default_rate: number | string;
  kind: ServiceKind;
  is_active: boolean;
};

export type SpoolStatus = "open" | "empty" | "discarded";

export type Spool = {
  id: string;
  material_code: string;
  supplier: string | null;
  batch_code: string | null;
  purchased_at: string;
  purchased_price: number | string;
  initial_grams: number | string;
  remaining_grams: number | string;
  status: SpoolStatus;
  notes: string | null;
};

export type Settings = {
  energy_kwh_price: number | string;
  printer_power_w: number | string;
  printer_depreciation_per_hour: number | string;
  currency: string;
  business_name: string;
  business_tagline: string | null;
  logo_path: string | null;
  brand_color_primary: string;
  stalled_quote_alert_days: number;
  low_spool_threshold_g: number | string;
};
