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
  material_type: string;         // PLA, PETG, ABS, ASA, PLA-CF, TPU, …
  name: string;
  manufacturer: string | null;
  color: string | null;
  density_g_cm3: number | string;
  price_per_kg_ref: number | string;
  failure_rate_pct: number | string;
  single_color_waste_pct: number | string;
  multi_color_waste_pct: number | string;
  is_current: boolean;
  effective_from: string;
  effective_to: string | null;
};

// Canonical list — surfaces in the materials form's select.
export const MATERIAL_TYPES = [
  "PLA",
  "HYPER-PLA",
  "PLA-CF",
  "PETG",
  "PETG-CF",
  "ABS",
  "ASA",
  "TPU",
  "Nylon",
  "Resina",
  "Outro",
] as const;

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
  material_type: string;
  color: string | null;
  manufacturer: string | null;
  purchased_from: string | null;
  purchase_url: string | null;
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
  | "em_producao"
  | "produzido"
  | "entregue"
  | "falhou"
  | "cancelado";

export type InProductionJob = {
  quote_id: string;
  name: string;
  kind: string;
  hours: number | string;
  entered_at: string | null;
};
export type InProductionOut = { jobs: InProductionJob[] };
export type FailureRateRow = {
  material_type: string;
  failures: number;
  total: number;
  failure_rate: number;
};
export type ProductionSuggestion = { material_type: string; advice: string };
export type ProductionSuggestionsOut = {
  suggestions: ProductionSuggestion[];
  generated_at: string | null;
  source_count: number;
  current_failures: number;
  stale: boolean;
};

export type QuoteItem = {
  id: string;
  name: string;
  filename: string | null;
  gcode_meta: {
    time_s?: number | null;
    filament_m?: number | null;
    material?: string | null;
    machine?: string | null;
  };
  quantity: number;
  subtotal: number | string;
  material_id?: string | null;
  is_multi_color?: boolean;
  material_pending?: boolean;
  pending_material_code?: string | null;
  model_source_url?: string | null;
  model_source_author?: string | null;
  model_source_license?: string | null;
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
  retail_mode?: boolean;
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
    receita_vs_despesa: Array<{ period: string; receita: number; despesa: number }>;
    funil: { orcado: number; aprovado: number; produzido: number; entregue: number };
    despesa_categorias: Record<string, number>;
    orcado_vs_real: Array<{ quote_id: string; orcado: number; real: number; variancia_pct: number }>;
  };
  lists: {
    ultimos_orcamentos: Array<{ id: string; kind: string; status: string; created_at: string | null }>;
    parados: Array<{ id: string; approved_at: string | null }>;
    spools_baixos: Array<{ id: string; material_type: string; remaining_grams: number }>;
    inbox: Array<{ id: string; original_path: string; parsed_meta: unknown }>;
  };
};

export type CalibrationScopeKind = "material_failure" | "material_price";
export type CalibrationInsightStatus = "open" | "applied" | "dismissed";

export type CalibrationInsight = {
  id: string;
  scope_kind: CalibrationScopeKind;
  scope_ref: string;
  observed_value: number | string;
  current_value: number | string;
  suggested_value: number | string;
  delta_pct: number | string;
  sample_size: number;
  status: CalibrationInsightStatus;
  computed_at: string;
};

export type CalibrationInsightApplyResult = {
  id: string;
  status: CalibrationInsightStatus;
  material_code: string;
  field: string;
  previous_value: number | string;
  new_value: number | string;
};

export type Settings = {
  energy_kwh_price: number | string;
  printer_power_w: number | string;
  printer_purchase_price: number | string;
  printer_useful_life_hours: number;
  printer_depreciation_per_hour: number | string;
  printer_maintenance_per_hour: number | string;
  currency: string;
  business_name: string;
  business_tagline: string | null;
  logo_path: string | null;
  brand_color_primary: string;
  stalled_quote_alert_days: number;
  low_spool_threshold_g: number | string;
  printer_hours_per_day?: number;
};

export type ForecastJob = {
  quote_id: string;
  name: string;
  hours: number | string;
  eta: string;
};

export type ForecastOut = {
  hours_per_day: number | string;
  queue_hours: number | string;
  queue_jobs: number;
  days_until_clear: number;
  next_available_at: string;
  jobs: ForecastJob[];
};

export type QuoteEtaOut = {
  quote_id: string;
  in_queue: boolean;
  position: number | null;
  hours: number | string;
  eta: string | null;
  next_available_at: string;
};

export type KeywordIdea = {
  id: string;
  term: string;
  notes: string | null;
  created_at: string;
};

export type SparkPoint = {
  taken_at: string;
  value: number | string;
};

export type TopListing = {
  title: string;
  price: number | null;
  sold: number;
  permalink: string | null;
};

export type TopRedditPost = {
  title: string;
  subreddit: string;
  score: number;
  comments: number;
  permalink: string | null;
};

export type LLMSuggestion = {
  id: string;
  term: string;
  rationale: string | null;
  provider: "anthropic" | "gemini" | "openai";
  recurrence_score: number | string;
  status: "pending" | "promoted" | "auto_promoted" | "dismissed" | "expired";
  promoted_keyword_id: string | null;
  suggested_at: string;
  temporal_window?: "day" | "week" | "month";
};

export type SourceMetric = {
  source: string;
  enabled: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  runs_24h: number;
  items_created_24h: number;
  errors_7d: number;
  avg_duration_ms_7d: number | null;
};

export type SourceMetricsOut = { sources: SourceMetric[] };

export type DigestOut = {
  date: string;
  provider: string;
  body: string;
  cached: boolean;
  created_at: string;
};

export type AutoNameOut = {
  inbox_id: string;
  name: string;
  confidence: number | null;
  why: string | null;
};

export type MarkupSuggestionOut = {
  quote_id: string;
  suggested_markup_pct: number | string;
  complexity: string | null;
  rationale: string | null;
  market_price_ref: number | string | null;
};

export type VarianceOut = {
  quote_id: string;
  orcado: number | string;
  real: number | string;
  variance_pct: number | string;
  explanation: string;
};

export type PricingCitation = {
  url: string;
  title: string | null;
};

export type PricingOut = {
  quote_id: string;
  cost: number | string;
  suggested_price: number | string;
  floor: number | string;
  ceiling: number | string;
  market_price_ref: number | string | null;
  market_status: "observado" | "estimado";
  rationale: string | null;
  sources: PricingCitation[];
};

export type VariantSuggestion = {
  name: string;
  material: string | null;
  angle: string | null;
};

export type VariantsOut = {
  item_id: string;
  variants: VariantSuggestion[];
};

export type RankingRow = {
  id: string;
  term: string;
  score: number | string;
  interest: number | string | null;
  wiki_views?: number | string | null;
  ml_volume: number | string | null;
  ml_avg_price: number | string | null;
  reddit_score?: number | string | null;
  reddit_comments?: number | string | null;
  sparkline: SparkPoint[];
  top_listings: TopListing[];
  top_reddit_posts?: TopRedditPost[];
  temporal_window: "day" | "week" | "month";
  source_provider: "anthropic" | "gemini" | "openai" | null;
};
