from pydantic import BaseModel

from backend.core.models import QuoteKind


class InboxPromote(BaseModel):
    kind: QuoteKind = QuoteKind.COMMERCIAL
    client_id: str | None = None
    name: str | None = None
