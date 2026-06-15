# Aba Contábil — entidade de Vendas materializada + DRE

**Data:** 2026-06-15
**Status:** aprovado no brainstorming (seções 1–7), pronto para plano de implementação.

## 1. Objetivo

Hoje a receita/despesa é **inferida on-the-fly** no dashboard a partir do status do
orçamento (comercial `aprovado`/`produzido`/`entregue` conta como receita). Isso é
frágil: **"finalizado" não quer dizer "vendido"** — produzir/entregar não garante que
entrou dinheiro.

Criar uma aba **Contábil** com:

- uma **entidade de venda** (`sales`) materializada a partir dos orçamentos comerciais,
  onde só o que é **confirmado** vira receita — e o **valor confirmado é a fonte de
  verdade da receita**, inclusive nos cards do dashboard;
- uma **entidade de despesas avulsas** (`expenses`) para custos que não passam pelo
  orçamento (manutenção, peças, ferramentas, mecânicos);
- um **relatório DRE** agregando entradas e saídas no período.

A aba é uma **tabela materializada com CRUD**, mais uma **sub-visão DRE** com o agregado.

## 2. Modelo de dados

### 2.1 `Sale` (tabela `sales`)

Uma linha por orçamento comercial *aprovado+*.

| Campo | Tipo | Papel |
|---|---|---|
| `id` | UUID PK | |
| `quote_id` | UUID FK único (`quotes.id`) | liga ao orçamento de origem |
| **Espelho (atualizado a cada sync)** | | |
| `quote_status` | `String(20)` | status do orçamento no último sync |
| `quote_total` | `Numeric(10,2)` | total calculado (custo×markup, min_charge) |
| `cpv_calc` | `Numeric(10,2)` | custo real de produção puxado (filamento consumido + energia + depreciação + serviços) |
| `client_id` | UUID FK null (`clients.id`) | cliente (espelho) |
| `is_stale` | bool default false | orçamento saiu de aprovado+ (cancelado/voltou a orçado) |
| **Editável (preservado a cada sync)** | | |
| `is_sold` | bool default false | confirmado como vendido → vira receita |
| `confirmed_revenue` | `Numeric(10,2)` null | **valor de fato recebido**; default sugerido = `quote_total`, editável. Fonte de verdade da receita |
| `variable_costs` | `Numeric(10,2)` default 0 | custos invisíveis/variáveis daquela venda |
| `cpv_override` | `Numeric(10,2)` null | sobrescreve `cpv_calc` se o real não bater |
| `sold_at` | `Date` null | data da venda — define o período no DRE/dashboard |
| `notes` | `Text` null | |
| `created_at` / `updated_at` | timestamptz | |

### 2.2 `Expense` (tabela `expenses`)

| Campo | Tipo |
|---|---|
| `id` | UUID PK |
| `category` | `String(20)` (enum `ExpenseCategory`) |
| `description` | `String(255)` |
| `amount` | `Numeric(10,2)` |
| `incurred_at` | `Date` |
| `created_at` / `updated_at` | timestamptz |

### 2.3 `ExpenseCategory` (StrEnum em `core/models.py`)

`maintenance` (Manutenção), `parts` (Peças), `tools` (Ferramentas),
`labor` (Mecânicos/Mão-de-obra), `other` (Outros). Coluna `String(20)` — sem enum no banco,
seguindo o padrão dos demais StrEnum do projeto.

### 2.4 Regras de cálculo (fonte única de verdade)

- **Receita de uma venda** = `confirmed_revenue` — só conta quando `is_sold = true`.
- **Custo de uma venda** = `coalesce(cpv_override, cpv_calc) + variable_costs`.

## 3. Sincronismo — lazy upsert

Função `sync_sales(session)` (em `core/accounting/sync.py`), executada quando a aba
Contábil carrega (via `GET /accounting/sales`) ou no botão **Atualizar**:

1. Busca todo orçamento **comercial** (`kind == commercial`) com status
   `aprovado`, `produzido` ou `entregue`.
2. Upsert em `sales` por `quote_id`:
   - **Sempre atualiza** os campos-espelho: `quote_status`, `quote_total`, `cpv_calc`,
     `client_id`, e zera `is_stale`.
   - **Nunca toca** nos editáveis (`is_sold`, `confirmed_revenue`, `variable_costs`,
     `cpv_override`, `sold_at`, `notes`).
   - Linha nova → cria com `is_sold=false`, `confirmed_revenue=null`, `variable_costs=0`,
     `is_stale=false`.
3. Linha de `sales` cujo `quote_id` **não** está mais no conjunto aprovado+
   (cancelado/voltou a orçado/draft) → marca `is_stale=true` (mantém histórico; sai dos
   candidatos ativos). Não deleta.

O `cpv_calc` é recalculado com a **mesma lógica do dashboard atual**: consumo real de
filamento (`MaterialConsumption.grams_used × unit_cost_snapshot`) + energia
(`printer_power_w × horas × energy_kwh_price`) + depreciação (`horas × dep_rate`) +
serviços (`Σ quantity × rate`). Essa lógica é **extraída do `dashboard.py` para um helper
compartilhado** em `core/accounting/` (ou `core/pricing/`) e reutilizada pelos dois lados,
evitando duplicação.

O primeiro `sync` funciona como **backfill**, materializando todos os orçamentos
comerciais aprovado+ já existentes.

## 4. Relatório DRE (sub-visão agregada)

`GET /accounting/dre?from=&to=` (default: mês corrente). Vendas entram por `sold_at`;
despesas por `incurred_at`.

```
RECEITA BRUTA            Σ confirmed_revenue        (is_sold, sold_at no período)
(−) CPV                  Σ coalesce(cpv_override, cpv_calc)
(−) Custos variáveis     Σ variable_costs
= LUCRO BRUTO
(−) Despesas operacionais
      Manutenção         Σ expenses[maintenance]
      Peças              Σ expenses[parts]
      Ferramentas        Σ expenses[tools]
      Mecânicos          Σ expenses[labor]
      Outros             Σ expenses[other]
= RESULTADO LÍQUIDO
```

Retorna também a **margem líquida (%)** = resultado líquido / receita bruta.

## 5. Impacto no dashboard

A parte financeira do dashboard passa a ler das **vendas confirmadas** (não mais do
status do orçamento):

- **Receita** = Σ `confirmed_revenue` das vendas `is_sold` com `sold_at` no período.
- **Despesa** = Σ custo das vendas (`coalesce(cpv_override, cpv_calc) + variable_costs`)
  **+ despesas operacionais** (`expenses`) do período.
- **Lucro / Margem** recalculam a partir desses dois.
- Gráfico `receita_vs_despesa`: receita por `sold_at`; despesa por `sold_at`
  (custo das vendas) e `incurred_at` (despesas operacionais).
- **Ficam como estão:** `gasto_pessoal`, estoque, funil (continua refletindo status do
  orçamento), listas, e o gráfico orçado×real.

## 6. API

Rotas em `backend/api/routes/accounting.py`; schemas em `api/schemas/accounting.py`.

- `POST   /accounting/sync` → roda o lazy upsert; retorna nº de linhas criadas/atualizadas/stale.
- `GET    /accounting/sales` → chama o sync e lista vendas (filtros: `from`/`to` por `sold_at`,
  `is_sold`, `is_stale`).
- `PATCH  /accounting/sales/{id}` → edita só os campos editáveis (confirma venda, ajusta
  receita/custos/data/notes).
- `GET    /accounting/expenses` / `POST` / `PATCH` / `DELETE` → CRUD de despesas.
- `GET    /accounting/dre?from=&to=` → o agregado da Seção 4.

## 7. Frontend — aba Contábil

Nova rota `/accounting` (label **Contábil** no menu), seguindo os padrões das telas
atuais e a skill `frontend-design`. Três sub-abas:

- **Vendas** — tabela materializada: orçamento, cliente, status, total, CPV,
  receita confirmada (editável inline), custos variáveis (editável), checkbox **Vendido**
  + data da venda. Linhas `stale` esmaecidas e filtráveis. Botão **Atualizar** (chama sync).
- **Despesas** — tabela CRUD: categoria, descrição, valor, data. Botão "Nova despesa".
- **DRE** — o demonstrativo da Seção 4 com seletor de período e a margem líquida.

## 8. Testes

- **Backend (pytest):**
  - `sync_sales`: cria linha nova; atualiza espelho preservando editáveis; marca `stale`
    quando o orçamento sai de aprovado+; backfill de orçamentos existentes.
  - DRE: agregação correta por período (`sold_at`/`incurred_at`), margem líquida.
  - CRUD de despesas.
  - Dashboard: receita/despesa/lucro derivando das vendas confirmadas + despesas.
  - Helper de `cpv_calc` compartilhado (mesmo número do dashboard hoje).
- **Migração Alembic:** tabelas `sales` e `expenses`.

## 9. Fora de escopo (YAGNI)

- Recorrência de despesas (aluguel/assinatura mensal automática).
- Categoria de despesa em texto livre.
- Vendas a partir de orçamentos **pessoais** (consomem estoque, não são receita —
  ver `personal_quotes_consume_stock`).
- Sincronismo por evento / materialized view do Postgres (descartados em favor do lazy upsert).
