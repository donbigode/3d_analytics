from enum import StrEnum


class QuoteKind(StrEnum):
    COMMERCIAL = "commercial"
    PERSONAL = "personal"


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    ORCADO = "orcado"
    APROVADO = "aprovado"
    EM_PRODUCAO = "em_producao"
    PRODUZIDO = "produzido"
    ENTREGUE = "entregue"
    FALHOU = "falhou"
    CANCELADO = "cancelado"


class ProductionOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class ServiceKind(StrEnum):
    LABOR = "labor"
    PURGE = "purge"
    OTHER = "other"


class ServiceUnit(StrEnum):
    MINUTE = "min"
    HOUR = "hour"
    GRAM = "g"


class SpoolStatus(StrEnum):
    OPEN = "open"
    EMPTY = "empty"
    DISCARDED = "discarded"


class WatcherInboxStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    DISCARDED = "discarded"


class ExpenseCategory(StrEnum):
    MAINTENANCE = "maintenance"
    PARTS = "parts"
    TOOLS = "tools"
    LABOR = "labor"
    OTHER = "other"
