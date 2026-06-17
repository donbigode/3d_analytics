from backend.infra.db.models import (
    Asset, CalibrationInsight, Client, DataSourceRun, Expense, KeywordIdea,
    KeywordObservation, LLMDigest, LLMSuggestion, MaterialConsumption, MaterialVersion,
    ProductionEvent, ProductionSuggestion, Quote, QuoteItem, QuoteService, Sale,
    Service, Spool, User, WatcherInboxFile,
)

# (nome no destino, model, colunas excluídas). Segredos (settings, export_config)
# ficam de fora; users sai sem password_hash.
EXPORT_ENTITIES: list[tuple[str, type, set[str]]] = [
    ("quotes", Quote, set()),
    ("quote_items", QuoteItem, set()),
    ("quote_services", QuoteService, set()),
    ("sales", Sale, set()),
    ("expenses", Expense, set()),
    ("material_versions", MaterialVersion, set()),
    ("material_consumptions", MaterialConsumption, set()),
    ("spools", Spool, set()),
    ("clients", Client, set()),
    ("services", Service, set()),
    ("production_events", ProductionEvent, set()),
    ("production_suggestions", ProductionSuggestion, set()),
    ("calibration_insights", CalibrationInsight, set()),
    ("assets", Asset, set()),
    ("data_source_runs", DataSourceRun, set()),
    ("keyword_ideas", KeywordIdea, set()),
    ("keyword_observations", KeywordObservation, set()),
    ("llm_digests", LLMDigest, set()),
    ("llm_suggestions", LLMSuggestion, set()),
    ("watcher_inbox_files", WatcherInboxFile, set()),
    ("users", User, {"password_hash"}),
]


def columns_for(entry: tuple[str, type, set[str]]) -> list[str]:
    _name, model, excluded = entry
    return [c.name for c in model.__table__.columns if c.name not in excluded]
