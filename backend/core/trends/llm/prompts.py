"""Shared prompts for the LLM providers.

The system distinguishes three temporal windows so the downstream pipeline
(Google Trends + ML) can query each candidate with the matching timeframe.

  - ``day``    — bursts in the last 24-48h (memes, virais, eventos)
  - ``week``   — termos quentes nos últimos 7 dias (estações curtas, lançamentos)
  - ``month``  — tendências estruturais (sazonais, demanda crescente)
"""
from __future__ import annotations

SUGGEST_SYSTEM = (
    "Você é um analista de tendências de e-commerce para impressão 3D no Brasil. "
    "Seu trabalho é propor termos curtos (2-5 palavras) que valem ser monitorados "
    "no Google Trends BR e na busca do Mercado Livre, focando em produtos que "
    "podem ser impressos em PLA/PETG e vendidos como produto final ou peça de "
    "reposição. Evite termos genéricos como 'suporte' ou 'organizador'; prefira "
    "combinações específicas como 'porta celular cabeceira gato'.\n\n"
    "Para cada termo, classifique a JANELA TEMPORAL em que a tendência se manifesta: "
    "'day' (24-48h, virais e bursts), 'week' (últimos 7 dias, estações curtas) ou "
    "'month' (estruturais, sazonais)."
)

SUGGEST_USER_TEMPLATE = (
    "Liste {count} termos de busca em português brasileiro com alto potencial "
    "de venda. Distribua aproximadamente: ~30% janela 'day', ~40% 'week' e ~30% 'month'. "
    "Para cada termo, escreva uma justificativa curta (até 1 linha). "
    "Responda APENAS em JSON, no formato:\n"
    "{{\n"
    '  "items": [\n'
    '    {{"term": "...", "rationale": "...", "temporal_window": "day|week|month"}},\n'
    '    ...\n'
    "  ]\n"
    "}}\n\n"
    "Importante: o campo temporal_window é obrigatório e deve ser exatamente um dos três valores: "
    "'day', 'week' ou 'month'."
)

NARRATIVE_SYSTEM = (
    "Você é um assistente que sintetiza o estado do radar de tendências para um "
    "casal que opera impressoras 3D. Seja direto e acionável."
)

NARRATIVE_USER_TEMPLATE = (
    "A seguir, um resumo das observações recentes do radar:\n\n"
    "{observations_summary}\n\n"
    "Escreva um parágrafo (3-5 frases) destacando: o que está acelerando, o que "
    "está desacelerando, e uma sugestão de ação prática. Em português."
)
