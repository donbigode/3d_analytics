# Contábil v2 — DRE/modelo (pessoais, custo de estoque, recorrentes, imposto)

**Data:** 2026-06-16
**Status:** aprovado no brainstorming, pronto para plano de implementação.
**Depende de:** Contábil v1 (`2026-06-15-contabil-vendas-dre-design.md`), em produção.
**Par:** `2026-06-16-contabil-v2-relatorios-design.md` (DRE mensal, XLSX, lucratividade).

## 1. Objetivo

Tornar o DRE fiel à operação real: pessoais podem ser vendidos (viram receita com markup),
produção não vendida consome estoque (vira custo), compra de máquina e despesas fixas
recorrentes entram como despesa, e imposto sobre a receita é descontado. Também higieniza a
v1 excluindo vendas `stale` do DRE.

## 2. Pessoais como venda

- `sync_sales` materializa **pessoais também** (kind PERSONAL), mesmo filtro de status
  (aprovado/produzido/entregue) usado pro comercial.
- `Sale` ganha campo-espelho **`quote_kind`** (String(20)), reescrito no sync junto dos demais
  espelhos. Migração: 1 coluna + backfill no próximo sync.
- Pessoal confirmado vendido → entra na **receita** com `confirmed_revenue` (default =
  `quote_total` = custo × markup → "reverte o markup em receita").
- Pessoal **não** vendido → não entra em receita; custo via **custo de estoque** (§4).
- **Dashboard `gasto_pessoal`** segue como card informativo, sem influenciar receita/despesa.
- **Aba Vendas:** coluna/filtro por **tipo** via `quote_kind`.

## 3. Excluir vendas stale do DRE

- `compute_dre` e as queries financeiras do dashboard passam a filtrar `Sale.is_stale == False`
  além de `is_sold == True`. Orçamento que voltou atrás (stale) não conta mais como receita.
- Coerência: o consumo de uma venda stale volta a contar no **custo de estoque** (§4), já que
  ela não é mais uma venda confirmada ativa.

## 4. Custo de estoque (consumo não vendido)

- **Fonte:** `MaterialConsumption` (`grams_used × unit_cost_snapshot`), gerada ao produzir
  comercial **e** pessoal.
- **Cálculo (período por `consumed_at`):** `custo_estoque = Σ consumo cujas quotes NÃO têm
  venda confirmada ativa` (i.e. sem `Sale` com `is_sold=True AND is_stale=False`). O consumo de
  vendas confirmadas já está no CPV (`cpv_calc` usa o mesmo `MaterialConsumption`) → exclusão
  evita dupla contagem.
- **Lugar:** linha "Custo de estoque (não vendido)" no bloco de despesas, somando em
  `total_despesas` e reduzindo o resultado.
- **Nota:** atribuído por `consumed_at`; venda posterior move o consumo pro CPV no recálculo
  (on-demand). Sem dupla contagem na visão atual.

## 5. Categoria de despesa: Máquinas/Equipamentos

- `ExpenseCategory` ganha **`equipment`** (rótulo "Máquinas/Equipamentos"), além de
  maintenance/parts/tools/labor/other. O DRE já soma todas as categorias → linha automática.
- **Nota contábil (não bloqueia):** o app tem depreciação por hora da impressora (entra no
  CPV). Lançar a compra cheia como despesa **e** usar depreciação por hora conta duas vezes —
  recomenda-se um dos dois (caixa simples: lançar a compra, depreciação por hora em zero).

## 6. Despesas recorrentes (mensais fixas)

- `Expense` ganha **`is_recurring: bool`** (default false). Migração: 1 coluna.
- **Regra:** uma despesa não-recorrente conta se `incurred_at` cai no período (como hoje). Uma
  recorrente conta **uma vez por mês** do período cujo mês seja `>=` o mês de `incurred_at`
  (recorrência **indefinida** — para parar, o usuário apaga/edita a despesa).
- Uma recorrente é contada **apenas** pela regra de recorrência (não também como lançamento
  avulso no mês de início) — o mês de início já é a primeira ocorrência. Sem dupla contagem.
- Aplica tanto no DRE de período quanto no mensal (a soma da categoria já reflete as ocorrências
  replicadas).
- CRUD de despesas ganha o checkbox "recorrente (mensal)".

## 7. Imposto sobre a receita

- `Settings` ganha **`revenue_tax_pct: Numeric(5,2)`** (default 0).
- DRE deduz `impostos = receita_bruta × revenue_tax_pct / 100` logo após a receita:

```
RECEITA BRUTA
(−) Impostos sobre a receita          ← receita_bruta × revenue_tax_pct
= RECEITA LÍQUIDA
(−) CPV
(−) Custos variáveis
= LUCRO BRUTO
(−) Despesas operacionais
      Manutenção / Peças / Ferramentas / Mecânicos / Máquinas / Outros
      Custo de estoque (não vendido)
= RESULTADO LÍQUIDO
```

- A configuração do `%` entra na tela de Ajustes (Settings) existente.

## 8. Estrutura do `compute_dre` (retorno)

Campos retornados (Decimals quantizados a 2 casas):
`receita_bruta`, `impostos`, `receita_liquida`, `cpv`, `custos_variaveis`, `lucro_bruto`
(= receita_liquida − cpv − custos_variaveis), `despesas` (dict por categoria),
`custo_estoque`, `total_despesas` (= Σ despesas + custo_estoque), `resultado_liquido`
(= lucro_bruto − total_despesas), `margem_liquida_pct` (= resultado_liquido / receita_bruta).

## 9. Consistência dashboard ↔ DRE

O dashboard mantém o invariante da v1 (parte financeira = DRE). Passa a:
- excluir vendas stale;
- somar **custo de estoque** na despesa;
- descontar **impostos** (uma fonte só: `revenue_tax_pct` em Settings) para `lucro` =
  `resultado_liquido` do DRE.

## 10. Migração Alembic

Uma migração adiciona: `sales.quote_kind` (String(20)), `expenses.is_recurring` (bool default
false), `settings.revenue_tax_pct` (Numeric(5,2) default 0). `quote_kind` é backfillado no
próximo `sync_sales`.

## 11. Testes

- **Backend:**
  - `sync_sales` inclui pessoais (aprovado+) e grava `quote_kind`; comercial intacto.
  - `compute_dre`: linha `custo_estoque` (consumo não vendido, exclui vendas confirmadas
    ativas, por `consumed_at`); `impostos`/`receita_liquida` corretos; recorrente replicada por
    mês; stale fora da receita; categoria `equipment` somada.
  - Dashboard: despesa inclui custo de estoque; lucro desconta imposto; stale fora;
    `gasto_pessoal` informativo.
- **Migração:** colunas novas + backfill de `quote_kind`.
- **Frontend:** `npm run check`.

## 12. Fora de escopo (YAGNI)

- Depreciação/capitalização contábil da máquina (caixa simples + nota).
- Fim de recorrência por data (escolhemos indefinida-até-apagar).
- Provisão de consumo entre períodos (atribuição por `consumed_at`, on-demand).
