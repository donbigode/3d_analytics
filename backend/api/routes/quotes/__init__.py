"""Rotas de orçamento.

Dividido em módulos por responsabilidade. A ORDEM de inclusão abaixo
importa: o FastAPI resolve rotas na ordem de registro, e `photos.py`
declara `/photos/{photo_id}/raw`, que é literal e precisa vir antes de
qualquer paramétrica `/{quote_id}` de `crud.py`.
"""
from fastapi import APIRouter

from backend.api.routes.quotes import crud, items, pdf, people, photos, services, transitions
from backend.api.routes.quotes._shared import _quote_out  # noqa: F401  (usado por testes)
from backend.api.routes.quotes.transitions import apply_production  # noqa: F401  (usado por printer.py)

router = APIRouter()
router.include_router(photos.router, prefix="/quotes")      # literais primeiro
router.include_router(crud.router, prefix="/quotes")
router.include_router(items.router, prefix="/quotes")
router.include_router(services.router, prefix="/quotes")
router.include_router(transitions.router, prefix="/quotes")
router.include_router(people.router, prefix="/quotes")
router.include_router(pdf.router, prefix="/quotes")

__all__ = ["router", "apply_production", "_quote_out"]
