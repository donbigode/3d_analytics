from enum import StrEnum


class QuoteKind(StrEnum):
    COMMERCIAL = "commercial"
    PERSONAL = "personal"


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    ORCADO = "orcado"
    APROVADO = "aprovado"
    PRODUZIDO = "produzido"
    ENTREGUE = "entregue"
    CANCELADO = "cancelado"


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
