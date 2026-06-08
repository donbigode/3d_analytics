"""Suggest a human-friendly Portuguese name for an inbox gcode."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import call_json
from backend.infra.db.models import WatcherInboxFile


SYSTEM = (
    "Você dá nomes curtos e descritivos em português a peças impressas em 3D. "
    "Recebe o nome do arquivo gcode + metadados (tempo, filamento, material, "
    "impressora) e devolve um título de 2 a 6 palavras que um cliente entenderia. "
    "Responda APENAS em JSON: {\"name\": \"<título>\", \"confidence\": 0..1, \"why\": \"<motivo curto>\"}"
)


async def suggest_name(session: AsyncSession, item: WatcherInboxFile) -> dict:
    meta = item.parsed_meta or {}
    user_prompt = (
        f"Nome do arquivo: {item.original_path.split('/')[-1]}\n"
        f"Material: {meta.get('material') or '?'}\n"
        f"Filamento (m): {meta.get('filament_m') or '?'}\n"
        f"Tempo (s): {meta.get('time_s') or '?'}\n"
        f"Impressora: {meta.get('machine') or '?'}\n\n"
        "Proponha um nome em português."
    )
    return await call_json(session, system=SYSTEM, user=user_prompt, max_tokens=200)
