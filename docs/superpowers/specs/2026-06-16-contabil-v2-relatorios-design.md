# Contábil v2 — relatórios (DRE mensal, export XLSX, lucratividade)

**Data:** 2026-06-16
**Status:** aprovado no brainstorming, pronto para plano de implementação.
**Depende de:** `2026-06-16-contabil-v2-design.md` (DRE/modelo) — usa o `compute_dre` v2.

## 1. Objetivo

Camada de **relatórios** sobre o DRE v2: ver o DRE **mês a mês** (visão planilhada),
**exportar em XLSX** com os dados brutos, e analisar **lucratividade por cliente e por
material**.

## 2. DRE mensal (visão planilhada)

- Endpoint `GET /accounting/dre/monthly?from=&to=` → array com **um DRE por mês** do intervalo,
  reusando `compute_dre` por mês (mesma estrutura da v2: receita_bruta, impostos,
  receita_liquida, cpv, custos_variaveis, lucro_bruto, despesas, custo_estoque, total_despesas,
  resultado_liquido, margem). Cada elemento traz `{ "month": "YYYY-MM", ...dre }`.
- **UI:** toggle na aba DRE entre **"Período"** (demonstrativo da v2) e **"Mensal"** — grade
  estilo planilha: **linhas = contas do DRE, colunas = meses** (+ coluna Total), valores
  alinhados à direita, resultado destacado.

## 3. Lucratividade por cliente / material

- Endpoint `GET /accounting/profitability?from=&to=` → dois rankings das vendas confirmadas
  ativas (is_sold, não stale, sold_at no período):
  - **por cliente:** agrupa por `client_id` (e nome) → `receita`, `custo` (cpv + variáveis),
    `margem`, `margem_pct`.
  - **por material:** rateia a `receita` e o `custo` de cada venda entre os **tipos de material**
    dos itens do orçamento, proporcional ao **custo de filamento de cada item** (item sem
    material resolvido entra em "—"). Agrega por `material_type` → `receita`, `custo`, `margem`,
    `margem_pct`.
- **UI:** nova sub-aba (ou seção) "Lucratividade" na Contábil com as duas tabelas ordenadas por
  margem desc.

### 3.1 Rateio por material (regra)
Para cada venda confirmada: `share_i = custo_filamento_item_i / Σ custo_filamento_itens`.
`receita_material += confirmed_revenue × share_i`; `custo_material += (cpv+variáveis) × share_i`.
Quando `Σ custo_filamento = 0` (sem itens com filamento), a venda inteira vai para "—".

## 4. Exportação XLSX

- Botão "Exportar XLSX" na aba DRE → `GET /accounting/dre/export.xlsx?from=&to=` devolve o
  arquivo via **`openpyxl`** (nova dependência backend), `StreamingResponse`, content-type
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, com `Content-Disposition`
  de download.
- **Abas:**
  - `DRE mensal` — a grade da §2 (linhas × meses + Total).
  - `Vendas` — vendas confirmadas ativas no período (orçamento, tipo `quote_kind`, cliente,
    status, total, CPV, receita, variáveis, data).
  - `Despesas` — lançamentos do período (categoria, descrição, valor, recorrente, data).
  - `Custo de estoque` — linhas de `MaterialConsumption` contadas (gramas, custo unitário,
    total, data, orçamento).
  - `Lucratividade` — os dois rankings da §3 (cliente e material).

## 5. Testes

- **Backend:**
  - `dre/monthly`: um resultado por mês no intervalo; agregação por mês correta; meses sem
    movimento retornam zeros.
  - `profitability`: ranking por cliente (soma bate com o DRE do período); rateio por material
    soma de volta ao total da venda; venda sem filamento cai em "—".
  - Export XLSX: status 200, content-type e `Content-Disposition` corretos; abrir o arquivo com
    `openpyxl` e checar nomes das abas + algumas células-chave (ex.: resultado do mês, total de
    uma venda).
- **Frontend:** `npm run check`; render da grade mensal e das tabelas de lucratividade.

## 6. Fora de escopo (YAGNI)

- Export em PDF (só XLSX nesta rodada).
- Gráficos de tendência do resultado (a grade mensal já cobre a leitura).
- Lucratividade por item-nome ou por categoria custom (escolhemos por material).
