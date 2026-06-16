# Contábil v2 — pessoais como venda, custo de estoque, DRE mensal + export XLSX

**Data:** 2026-06-16
**Status:** aprovado no brainstorming, pronto para plano de implementação.
**Depende de:** a aba Contábil v1 (`2026-06-15-contabil-vendas-dre-design.md`), já em produção.

## 1. Objetivo

Evoluir a Contábil para refletir melhor a operação real:

- **pessoais podem ser vendidos** e, quando são, viram receita (com markup);
- a **produção não vendida consome estoque** — esse custo precisa aparecer no DRE;
- a **compra de máquina** entra como despesa;
- um **DRE mês a mês** (visão planilhada) e **exportação XLSX** com os dados brutos.

## 2. Pessoais como venda (2a)

- `sync_sales` passa a materializar **pessoais também** (kind PERSONAL), não só comercial,
  com o mesmo filtro de status (aprovado/produzido/entregue).
- A `Sale` ganha um campo-espelho **`quote_kind`** (String(20)) — migração de 1 coluna,
  reescrito no sync junto dos demais espelhos.
- Pessoal confirmado como vendido → entra na **receita** com `confirmed_revenue` (default =
  `quote_total`, que é custo × markup → "reverte o markup em receita").
- Pessoal **não** vendido → não entra em receita; seu custo aparece via **custo de estoque**
  (Seção 3).
- **Dashboard `gasto_pessoal`:** segue como card informativo (consumo pessoal), mas **não**
  influencia receita/despesa (essas vêm de vendas + despesas + custo de estoque) — evita
  dupla contagem.
- **Aba Vendas:** coluna/filtro por **tipo** (comercial/pessoal) usando `quote_kind`.

## 3. Custo de estoque no DRE (2b)

- **Fonte:** `MaterialConsumption` (baixa real: `grams_used × unit_cost_snapshot`), gerada ao
  produzir tanto comercial quanto pessoal.
- **Cálculo (período por `consumed_at`):**
  `custo_estoque = Σ consumo cujas quotes NÃO têm venda confirmada (is_sold=true)`.
  O consumo de quotes vendidas já está no CPV (`cpv_calc` usa o mesmo `MaterialConsumption`),
  então excluí-las evita dupla contagem.
- **Lugar no DRE:** linha **dentro do bloco de despesas** — "Custo de estoque (não vendido)" —
  somando em `total_despesas` e reduzindo o resultado líquido. Lucro bruto permanece limpo
  (margem das vendas).

```
RECEITA BRUTA
(−) CPV
(−) Custos variáveis
= LUCRO BRUTO
(−) Despesas operacionais
      Manutenção / Peças / Ferramentas / Mecânicos / Máquinas / Outros
      Custo de estoque (não vendido)        ← calculado
= RESULTADO LÍQUIDO
```

- **Consistência dashboard↔DRE:** o card `despesa` do dashboard também passa a somar o custo
  de estoque, pra continuar batendo com o resultado do DRE.
- **Nota de simplificação:** atribuído por `consumed_at`; se a quote for vendida depois, o
  consumo sai do custo de estoque e passa pro CPV no recálculo (relatório é on-demand). Sem
  dupla contagem na visão atual.

`compute_dre` retorna o número novo (`custo_estoque`) e o inclui em `total_despesas` e
`resultado_liquido`.

## 4. Compra de máquina — nova categoria de despesa

- `ExpenseCategory` ganha **`equipment`** (rótulo "Máquinas/Equipamentos"), além de
  maintenance/parts/tools/labor/other. O DRE já soma todas as categorias, então a linha
  aparece automaticamente; o CRUD de despesas a oferece no select.
- **Nota contábil (no spec, não bloqueia):** o app tem depreciação por hora da impressora que,
  se preenchida, entra no CPV. Lançar a **compra cheia** como despesa **e** usar depreciação
  por hora conta duas vezes — recomendação: usar só um dos dois (para caixa simples, lançar a
  compra e manter depreciação por hora em zero).

## 5. DRE mensal + exportação XLSX (2c)

### 5.1 DRE mensal (visão planilhada)
- Endpoint `GET /accounting/dre/monthly?from=&to=` → array com **um DRE por mês** do intervalo.
  Reusa `compute_dre` por mês (mesma estrutura), sem lógica de cálculo nova.
- **UI:** toggle na aba DRE entre **"Período"** (demonstrativo atual) e **"Mensal"** — grade
  estilo planilha: **linhas = contas do DRE, colunas = meses** (+ coluna Total), valores
  alinhados à direita, resultado destacado.

### 5.2 Exportação XLSX
- Botão "Exportar XLSX" → `GET /accounting/dre/export.xlsx?from=&to=` devolve o arquivo via
  **`openpyxl`** (nova dependência backend), com `StreamingResponse` e content-type
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- **Abas:**
  - `DRE mensal` — a grade linhas × meses (+ Total).
  - `Vendas` — vendas confirmadas no período (orçamento, tipo, cliente, status, total, CPV,
    receita, variáveis, data).
  - `Despesas` — lançamentos de despesa do período (categoria, descrição, valor, data).
  - `Custo de estoque` — linhas de `MaterialConsumption` contadas (gramas, custo unitário,
    total, data, orçamento) — o dado bruto por trás do número.

## 6. Testes

- **Backend:**
  - `sync_sales` inclui pessoais (aprovado+), grava `quote_kind`; comercial segue funcionando.
  - `compute_dre`: linha `custo_estoque` = consumo não vendido (exclui quotes vendidas), por
    `consumed_at`; entra em `total_despesas`/`resultado`.
  - Categoria `equipment` aceita no CRUD e somada no DRE.
  - `dre/monthly`: um resultado por mês, agregação correta por mês.
  - Export XLSX: status 200, content-type correto, abas esperadas presentes (abrir com
    `openpyxl` e checar nomes das abas + algumas células).
  - Dashboard: `despesa` passa a incluir custo de estoque; `gasto_pessoal` informativo.
- **Migração Alembic:** coluna `quote_kind` em `sales` (backfill no próximo sync).
- **Frontend:** `npm run check`.

## 7. Fora de escopo (YAGNI)

- Capitalização/depreciação contábil da máquina (escolhemos caixa simples + nota).
- Provisionar consumo entre períodos (mantemos atribuição por `consumed_at`, on-demand).
- Export em PDF do DRE (só XLSX nesta rodada).
