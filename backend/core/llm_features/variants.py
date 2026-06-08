"""Suggest derivative SKUs (material/colour/size) for a given quote item."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_json
from backend.infra.db.models import MaterialVersion, QuoteItem


SYSTEM = (
    "Você sugere variações de produto (cores, materiais, tamanhos, kits) para "
    "uma peça impressa em 3D, com foco em ampliar nicho sem retrabalho grande. "
    "Use apenas materiais que o dono já cadastrou (lista fornecida). "
    "Responda APENAS em JSON: "
    "{\"variants\": [{\"name\": \"<título curto>\", \"material\": \"<code>\", "
    "\"angle\": \"<por que vende: público / contexto / ocasião>\"} , ... ]}"
)


async def suggest_variants(session: AsyncSession, item: QuoteItem) -> dict:
    available_materials = (
        await session.execute(
            select(MaterialVersion).where(MaterialVersion.is_current.is_(True))
        )
    ).scalars().all()
    material_codes = sorted({m.material_type for m in available_materials})

    user_prompt = (
        f"Peça base: {item.name}\n"
        f"Material atual: {(item.gcode_meta or {}).get('material') or '?'}\n"
        f"Tempo: {((item.gcode_meta or {}).get('time_s') or 0)/3600:.1f}h\n"
        f"Filamento: {(item.gcode_meta or {}).get('filament_m') or 0} m\n\n"
        f"Materiais disponíveis: {', '.join(material_codes) or 'PLA'}\n\n"
        "Proponha 4-6 variações com ângulo de venda diferente cada uma."
    )
    return await call_json(session, system=SYSTEM, user=user_prompt, max_tokens=700)
