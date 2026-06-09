"""Suggest a markup percentage based on quote complexity + historical patterns.

When Mercado Livre OAuth is configured, we also fetch the average street
price for items whose names look searchable (e.g. "porta-caneta",
"suporte celular"). The LLM gets that market context so its suggestion
reflects what competitors are actually charging, not just the owner's
historical markup.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_json
from backend.core.models import QuoteKind, QuoteStatus
from backend.core.trends.sources import mercadolivre as ml_source
from backend.infra.db.models import Quote, QuoteItem, Settings

logger = logging.getLogger(__name__)


SYSTEM = (
    "Você é um analista que sugere percentuais de markup para orçamentos de "
    "impressão 3D no Brasil. Considere: complexidade do gcode (tempo, peso, "
    "número de peças, multi-color), histórico de markups do dono e — quando "
    "fornecido — o preço médio de mercado para peças semelhantes no Mercado "
    "Livre. O custo do orçamento já cobre material+energia+depreciação; o "
    "markup precisa cobrir mão-de-obra/risco/lucro E ainda ser competitivo "
    "se o item é commodity (alguém vende parecido no marketplace). Devolve "
    "recomendação concreta. Responda APENAS em JSON: "
    "{\"suggested_markup_pct\": <number>, \"rationale\": \"<1-2 frases>\", "
    "\"complexity\": \"baixa|média|alta\", "
    "\"market_price_ref\": <number-or-null>}"
)


_MIN_ITEM_NAME_LEN = 4
_MAX_MARKET_QUERIES = 5
_GENERIC_NAMES = {"peca", "peça", "item", "test", "teste", "sample", "amostra"}


def _is_searchable(name: str) -> bool:
    """Filter out placeholder names that would return garbage from ML."""
    n = (name or "").strip().lower()
    if len(n) < _MIN_ITEM_NAME_LEN:
        return False
    # Generic placeholders like "Peca 1", "Item 2", "Teste" are noise.
    base = n.split()[0].rstrip("0123456789-_")
    if base in _GENERIC_NAMES:
        return False
    return True


async def _gather_market_prices(
    session: AsyncSession, items: list[QuoteItem]
) -> tuple[list[dict], Decimal]:
    """Look up street prices for the quote's items on Mercado Livre.

    Returns ``(per_item_observations, estimated_market_total)``. When ML
    credentials aren't configured or every item name is generic, the list
    is empty and the total is zero — the caller proceeds without market
    context. Token refreshes are persisted back to the settings row.
    """
    settings_row = await session.get(Settings, 1)
    if (
        not settings_row
        or not settings_row.meli_app_id
        or not settings_row.meli_client_secret
    ):
        return [], Decimal("0")

    creds = ml_source.MeliCredentials(
        app_id=settings_row.meli_app_id,
        client_secret=settings_row.meli_client_secret,
        access_token=settings_row.meli_access_token,
        token_expires_at=settings_row.meli_token_expires_at,
    )

    seen: dict[str, dict] = {}
    estimated_total = Decimal("0")
    queried = 0
    token_update = None
    for it in items:
        name = (it.name or "").strip()
        if not _is_searchable(name):
            continue
        key = name.lower()
        if key in seen:
            obs = seen[key]
        else:
            if queried >= _MAX_MARKET_QUERIES:
                continue
            queried += 1
            try:
                stats, refresh = await ml_source.fetch_volume(name, creds=creds)
            except Exception as exc:  # noqa: BLE001
                logger.info("market lookup failed for %r: %s", name, exc)
                continue
            if refresh is not None:
                token_update = refresh
                # Mutate creds so the next loop iteration uses the fresh token.
                creds = ml_source.MeliCredentials(
                    app_id=creds.app_id,
                    client_secret=creds.client_secret,
                    access_token=refresh.access_token,
                    token_expires_at=refresh.expires_at,
                )
            if not stats:
                continue
            avg = Decimal(str(stats.get("avg_price") or 0))
            if avg <= 0:
                continue
            obs = {
                "term": name,
                "avg_price": avg,
                "sold": int(Decimal(str(stats.get("sold_quantity") or 0))),
                "sample": int(stats.get("sample_size") or 0),
            }
            seen[key] = obs
        estimated_total += obs["avg_price"] * Decimal(int(it.quantity or 1))

    if token_update is not None:
        settings_row.meli_access_token = token_update.access_token
        settings_row.meli_token_expires_at = token_update.expires_at
        await session.commit()
        await session.refresh(settings_row)

    return list(seen.values()), estimated_total


async def suggest_markup(session: AsyncSession, quote: Quote) -> dict:
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    ).scalars().all()

    total_time = sum(int(it.gcode_meta.get("time_s") or 0) for it in items)
    total_filament = sum(float(it.gcode_meta.get("filament_m") or 0) for it in items)
    materials = sorted({(it.gcode_meta.get("material") or "?") for it in items})
    qty = sum(int(it.quantity or 1) for it in items)
    multi_color = len(materials) > 1

    # Recent commercial quotes for context
    recent = (
        await session.execute(
            select(Quote)
            .where(
                Quote.kind == QuoteKind.COMMERCIAL.value,
                Quote.status.in_(
                    [
                        QuoteStatus.APROVADO.value,
                        QuoteStatus.PRODUZIDO.value,
                        QuoteStatus.ENTREGUE.value,
                    ]
                ),
            )
            .order_by(Quote.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    history_lines = [
        f"  - markup {float(q.markup_pct):.0f}%  (status={q.status})"
        for q in recent
    ]
    history = "\n".join(history_lines) or "  (sem histórico ainda)"

    market_obs, market_total = await _gather_market_prices(session, items)
    if market_obs:
        market_lines = "\n".join(
            f"  - \"{o['term']}\": R$ {float(o['avg_price']):.2f} médio · "
            f"{o['sold']} vendidos · {o['sample']} anúncios"
            for o in market_obs
        )
        market_block = (
            f"\nPreços de referência observados no Mercado Livre "
            f"(últimos 20 anúncios por busca):\n{market_lines}\n"
            f"  - estimativa de preço-de-mercado p/ este conjunto: "
            f"R$ {float(market_total):.2f}\n"
        )
    else:
        market_block = "\n(sem dados de mercado: ML não configurado ou nomes genéricos)\n"

    user_prompt = (
        f"Orçamento atual:\n"
        f"  - tempo total de impressão: {total_time/3600:.1f}h\n"
        f"  - filamento total: {total_filament:.1f} m\n"
        f"  - peças: {len(items)} (quantidade total: {qty})\n"
        f"  - materiais: {', '.join(materials)}\n"
        f"  - multi-color: {'sim' if multi_color else 'não'}\n"
        f"  - markup atual definido: {float(quote.markup_pct):.0f}%\n\n"
        f"Histórico de últimos 10 orçamentos comerciais aprovados+:\n{history}\n"
        f"{market_block}\n"
        "Recomende um markup percentual. Avalie:\n"
        "  - risco (tempo longo, material caro, multi-color)\n"
        "  - padrão histórico do dono\n"
        "  - se houver preço de mercado, o markup precisa deixar o preço final "
        "(custo×(1+markup/100)) competitivo, idealmente <= preço médio de "
        "mercado — caso contrário sinalize no rationale\n"
        "Devolva também o campo market_price_ref com a estimativa total que "
        "você usou (R$), ou null quando não havia dados."
    )
    return await call_json(session, system=SYSTEM, user=user_prompt, max_tokens=500)
