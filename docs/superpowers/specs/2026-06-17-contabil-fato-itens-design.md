# Contábil — tabela fato por item (nomes, quantidade, cor)

**Data:** 2026-06-17
**Status:** aprovado no brainstorming, pronto para plano de implementação.
**Depende de:** Contábil v2 (`2026-06-16-contabil-v2-design.md` / `-relatorios-design.md`), em produção.

## 1. Objetivo

Expor os dados da Contábil a **nível de item** numa **tabela fato** (uma linha por
venda × item do orçamento), pronta para `select *` e export pro Databricks — incluindo
nome do item, quantidade, cor da bobina consumida, material, gramas e custo. Também
mostrar os nomes dos itens (com quantidade/cor) na aba Vendas, hoje só a nível de venda.

Decisão de modelagem registrada no brainstorming: **compra de bobina NÃO entra como
despesa** (regime de competência puro — bobina é estoque/ativo, vira custo só quando
consumida via CPV + custo de estoque). Nenhuma mudança no DRE.

## 2. Tabela fato por item (view computada)

Endpoint `GET /accounting/facts?from=&to=` → uma linha por **(venda confirmada ativa ×
item do orçamento)** no período. Mesma base do DRE: `Sale.is_sold` e `not is_stale`,
`sold_at` no período. Sem tabela nova — computada na leitura (sempre fresca), como o
resto da Contábil.

### 2.1 Colunas

**Nível venda (repetidas em cada linha de item):**
`sale_id`, `quote_id`, `quote_kind` (commercial/personal), `cliente` (nome ou `—`),
`status` (quote_status), `sold_at`, `is_sold`, `receita_venda` (confirmed_revenue),
`custos_variaveis_venda` (variable_costs), `cpv_venda` (coalesce(cpv_override, cpv_calc)).

**Nível item:**
`item_id`, `nome`, `quantidade`, `material_type`, `cor_material`
(`MaterialVersion.color` do material atribuído), `cor_bobina` (pipe-join das cores
distintas das bobinas consumidas via `MaterialConsumption → Spool.color`; `null` se o
item não foi produzido), `filament_m` (por peça), `filament_g` (override por peça, ou
`null`), `gramas_total` (gramas efetivas por peça × quantidade, regra de
`effective_grams_per_unit` com `waste_pct=0`), `custo_filamento_item` (catálogo:
`filament_cost(gramas_total, price_per_kg_ref)`), `receita_item`.

### 2.2 `receita_item` (rateio)
Rateia a `receita_venda` entre os itens da venda proporcional ao
`custo_filamento_item` (mesma regra da lucratividade por material). Quando o total de
custo de filamento da venda é 0, divide igualmente entre os itens. A soma dos
`receita_item` de uma venda reconstrói `receita_venda`.

### 2.3 Notas de granularidade
- Medidas de **venda** (`receita_venda`, `cpv_venda`, `custos_variaveis_venda`) repetem
  em cada item — somar direto dá dupla contagem; dedup por `sale_id`. Documentado na
  resposta da API e no cabeçalho da aba XLSX.
- Medidas de **item** (`quantidade`, `gramas_total`, `custo_filamento_item`,
  `receita_item`) somam direto.
- Item sem material resolvido: `material_type`/`cor_material` ficam `—`/`null`,
  `custo_filamento_item=0`.

## 3. Aba Vendas — nomes dos itens (pipe)

Na tabela de Vendas da Contábil, nova coluna **Itens**: nomes concatenados com pipe,
com quantidade e cor quando houver — ex.: `Vaso ×2 (Azul) | Suporte ×1 (Preto)`. A cor
preferida é a `cor_bobina`; se nula, usa `cor_material`; se ambas nulas, omite a cor.
Vem do mesmo join da Seção 2, agregado por venda. Granularidade da aba inalterada (uma
linha por venda). O `SaleOut` ganha um campo `itens_label: str` (montado no backend) pra
a UI não precisar de outra chamada.

## 4. XLSX — aba `Fato (itens)`

Adicionar uma aba **`Fato (itens)`** ao export (`build_dre_xlsx`), com exatamente as
colunas da Seção 2.1 (uma linha por item). Primeira linha = cabeçalho; demais = as linhas
do fato no período. As abas atuais (DRE mensal, Vendas, Despesas, Custo de estoque,
Lucratividade) permanecem.

## 5. Arquitetura

- `backend/core/accounting/facts.py` — `compute_facts(session, from, to) -> list[dict]`
  (o builder por item). Reusa `sale_cpv` (dre.py), `effective_grams_per_unit`
  (quote_service.py), `filament_cost`/`grams_from_meters` (pricing/cost.py).
- Helper `sale_items_label(facts_da_venda) -> str` para a coluna Itens — derivado das
  linhas do fato, sem segunda query.
- `compute_facts` é a fonte única: alimenta o endpoint `/accounting/facts`, o
  `itens_label` no `SaleOut` (via `list_sales`), e a aba `Fato (itens)` do XLSX.

## 6. Testes

- **Backend:**
  - `compute_facts`: uma linha por item; campos de venda repetidos; `gramas_total` e
    `custo_filamento_item` corretos (override de gramas respeitado); `receita_item`
    rateada soma de volta à `receita_venda`; `cor_bobina` vem da consumo (pipe-join de
    cores distintas); item não produzido → `cor_bobina` nula.
  - `GET /accounting/facts`: shape e filtro por período.
  - `list_sales` retorna `itens_label` no formato pipe com quantidade/cor.
  - XLSX: aba `Fato (itens)` presente com as colunas esperadas.
- **Frontend:** coluna Itens na aba Vendas; `npm run check`.

## 7. Fora de escopo (YAGNI)

- Compra de material como despesa (descartado — competência puro).
- Materializar o fato numa tabela física (view computada basta; o export é on-demand).
- Cor por item digitada à mão no orçamento (escolhemos a cor real da bobina consumida).
