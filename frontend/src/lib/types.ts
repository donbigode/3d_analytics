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

export type QuoteKind = "commercial" | "personal";
export type QuoteStatus =
  | "draft"
  | "orcado"
  | "aprovado"
  | "produzido"
  | "entregue"
  | "cancelado";

export type QuoteItem = {
  id: string;
  name: string;
  filename: string;
  gcode_meta: {
    time_s?: number | null;
    filament_m?: number | null;
    material?: string | null;
    machine?: string | null;
  };
  quantity: number;
  subtotal: number | string;
  material_pending?: boolean;
  pending_material_code?: string | null;
};

export type QuoteServiceLine = {
  id: string;
  service_id: string;
  quantity: number | string;
  rate: number | string;
  subtotal: number | string;
};

export type Quote = {
  id: string;
  kind: QuoteKind;
  client_id: string | null;
  status: QuoteStatus;
  markup_pct: number | string;
  min_charge: number | string;
  notes: string | null;
  items: QuoteItem[];
  services: QuoteServiceLine[];
  cost: number | string;
  total: number | string;
  pending_items?: number;
  created_at: string;
  finalized_at: string | null;
  approved_at: string | null;
  produced_at: string | null;
  delivered_at: string | null;
};

export type InboxItem = {
  id: string;
  original_path: string;
  parsed_meta: {
    time_s?: number | null;
    filament_m?: number | null;
    material?: string | null;
    machine?: string | null;
  } | null;
  created_at: string | null;
};

export type DashboardOut = {
  cards: {
    receita: number | string;
    despesa: number | string;
    lucro: number | string;
    margem_pct: number | string;
    gasto_pessoal: number | string;
    orcamentos_por_estado: Record<string, number>;
    taxa_conversao_pct: number | string;
    estoque: {
      total_grams: number | string;
      estimated_value: number | string;
    };
  };
  charts: {
    receita_vs_despesa: Array<{ period?: string; receita?: number; despesa?: number }>;
    funil: { orcado: number; aprovado: number; produzido: number; entregue: number };
    despesa_categorias: Record<string, number>;
    orcado_vs_real: Array<{ quote_id: string; orcado: number; real: number; variancia_pct: number }>;
  };
  lists: {
    ultimos_orcamentos: Array<{ id: string; kind: string; status: string; created_at: string | null }>;
    parados: Array<{ id: string; approved_at: string | null }>;
    spools_baixos: Array<{ id: string; material_code: string; remaining_grams: number }>;
    inbox: Array<{ id: string; original_path: string; parsed_meta: unknown }>;
  };
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
