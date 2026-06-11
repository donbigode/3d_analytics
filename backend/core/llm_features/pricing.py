"""Suggest a sale price by letting the LLM RESEARCH the web for market prices.

Different from the markup feature: markup answers "what % over cost?" and
mostly stays anchored on history + a single ML API call. Pricing here is
a **research-mode** feature — when Anthropic is configured we let Claude
hit the web_search tool to look up similar pieces on Mercado Livre,
Shopee, Amazon BR, Elo7, AliExpress and any other store it finds. The
ML OAuth data we already collect is passed as a seed so the LLM has a
known-good number to compare against the open-web results.

When no Anthropic key is configured we degrade to the same shape but the
``market_status`` flag tells the UI the suggestion is unanchored.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features._market import gather_market_prices
from backend.core.llm_features.runner import (
    LLMUnavailable,
    call_json_with_research,
)
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db.models import Quote, QuoteItem


SYSTEM = (
    "Você é um analista de precificação para impressão 3D no Brasil. "
    "Recomende o PREÇO DE VENDA em reais com base em pesquisa REAL de mercado "
    "— NÃO em múltiplos do custo.\n\n"
    "USE A FERRAMENTA web_search para procurar peças similares à descrita "
    "no orçamento em: mercadolivre.com.br, shopee.com.br, amazon.com.br, "
    "elo7.com.br e aliexpress.com (preferencialmente em português). Faça "
    "buscas específicas com o nome da peça (em português) e, quando útil, "
    "adicione \"3d print\", \"impressão 3d\" ou o material. Compare ao menos "
    "3 anúncios reais de fontes diferentes.\n\n"
    "Regras:\n"
    "  - suggested_price deve estar dentro da faixa observada nos anúncios\n"
    "  - NUNCA recomende abaixo do custo de produção fornecido (é o piso)\n"
    "  - quando houver dispersão grande, posicione na mediana (a menos que a "
    "qualidade do produto justifique premium)\n"
    "  - cite no rationale 2-3 anúncios reais que sustentam a recomendação\n\n"
    "Responda APENAS em JSON: {\n"
    "  \"suggested_price\": <number>,\n"
    "  \"floor\": <number>,\n"
    "  \"ceiling\": <number>,\n"
    "  \"market_price_ref\": <number-or-null>,\n"
    "  \"market_status\": \"observado|estimado\",\n"
    "  \"rationale\": \"<2-3 frases citando os achados>\"\n"
    "}\n"
)


async def suggest_price(
    session: AsyncSession,
    quote: Quote,
    *,
    orcado_cost: Decimal,
) -> tuple[dict, list[dict]]:
    """Return ``(parsed_json, citations)``. Citations are the URLs the LLM
    consulted via web_search — surfaced in the UI so the user can audit."""
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    ).scalars().all()

    # Seed: live ML API lookup. The LLM treats this as a starting reference
    # but is asked to expand the picture via web_search.
    market_obs, market_total = await gather_market_prices(session, items)

    if market_obs:
        seed_lines = "\n".join(
            f"  - \"{o['term']}\": "
            f"mín R$ {float(o['min_price']):.2f}  ·  médio R$ {float(o['avg_price']):.2f}  ·  "
            f"máx R$ {float(o['max_price']):.2f}  ({o['sample']} anúncios via API)"
            for o in market_obs
        )
        seed_block = (
            "DADOS SEED DO MERCADO LIVRE (via OAuth — use como ancoragem, mas "
            f"valide e expanda com web_search):\n{seed_lines}\n"
            f"Total estimado seed: R$ {float(market_total):.2f}\n\n"
        )
    else:
        seed_block = (
            "Mercado Livre OAuth não retornou dados — use web_search livremente "
            "pra encontrar os preços de mercado.\n\n"
        )

    # Historical context — só pro LLM ter noção do padrão, NÃO derivar dali.
    history = (
        await session.execute(
            select(Quote.markup_pct).where(
                Quote.kind == QuoteKind.COMMERCIAL.value,
                Quote.status.in_(
                    [
                        QuoteStatus.APROVADO.value,
                        QuoteStatus.PRODUZIDO.value,
                        QuoteStatus.ENTREGUE.value,
                    ]
                ),
            )
        )
    ).scalars().all()
    markups = sorted(float(m) for m in history if m is not None)
    median_markup = markups[len(markups) // 2] if markups else None

    items_summary = ", ".join(
        f"{it.name} (qtd {it.quantity}"
        + (
            f", multicolor"
            if it.is_multi_color
            else ""
        )
        + ")"
        for it in items[:6]
    ) or "(sem peças)"

    user_prompt = (
        f"Peças do orçamento: {items_summary}\n"
        f"Custo interno calculado (piso de segurança): R$ {float(orcado_cost):.2f}\n"
        + (
            f"Markup mediano histórico do dono (contexto, não derivar): {median_markup:.0f}%\n"
            if median_markup is not None
            else ""
        )
        + "\n"
        + seed_block
        + "Agora pesquise na web preços reais de peças similares e recomende. "
        "Inclua market_status=\"observado\" se conseguiu validar com pelo menos "
        "3 anúncios reais; caso contrário \"estimado\". NUNCA suggested_price < custo."
    )

    try:
        return await call_json_with_research(
            session, system=SYSTEM, user=user_prompt, max_tokens=2000, max_searches=3
        )
    except LLMUnavailable:
        raise
