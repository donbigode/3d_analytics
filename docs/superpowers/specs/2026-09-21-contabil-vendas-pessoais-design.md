# Spec 2 — Contábil: pessoal separado, data de venda, busca e performance

**Data:** 2026-09-21
**Status:** aprovado no brainstorming, aguardando revisão da spec
**Depende de:** Spec 0 (helpers, estilos) e Spec 1 (`#0042`, `SearchBar`, `Table`)
**Atende aos pedidos:** #1 (pessoal fora da lista de venda), #2 (data de venda), #3 (busca)

## 1. Contexto

A aba Vendas do Contábil mistura orçamentos comerciais e de uso pessoal numa
lista só, oferecendo a ambos o mesmo checkbox "Vendido". Três problemas
decorrem disso e um quarto foi encontrado no review:

1. Item pessoal não é candidato a venda — polui a lista que serve para
   "conferir o que tem pra faturar".
2. O checkbox grava `date.today()` silenciosamente
   (`backend/api/routes/accounting.py:85`). Não há como registrar uma venda
   ocorrida em outra data, e a data cai no mês errado do DRE.
3. Não há busca em nenhuma das listas.
4. `GET /accounting/sales` executa `sync_sales()` **com commit** — um GET que
   escreve. Cada marcação de "vendido" recarrega a lista, o que recalcula o custo
   de todos os orçamentos aprovados e ainda faz N+1 (`sale_items_label` e
   `_client_name` por linha).

## 2. Escopo

**Dentro:** filtro por tipo em `GET /accounting/sales`; sub-aba "Uso pessoal";
fluxo explícito de registro de venda com data; busca e filtros nas três listas;
correções de performance e do estado fantasma; backfill de `sales.quote_kind`.

**Fora:** mudar a regra de DRE (uso pessoal não vendido continua sendo perda
operacional pelo CPV cheio); despesas recorrentes; relatórios novos.

## 3. Pessoal fora da lista de venda — pedido #1

### 3.1 Decisão

O pessoal **não sai do Contábil** — ele sai da *lista de venda* e ganha lugar
próprio. Tirá-lo do módulo inteiro (não criar linha `Sale` para pessoal) exigiria
reescrever `_perda_operacional`, que hoje lê `Sale`, e eliminaria a possibilidade
de registrar um pessoal que acabou vendido — contra a regra em vigor.

### 3.2 Aba Vendas

`GET /accounting/sales` ganha `?kind=commercial|personal`. A aba Vendas passa a
pedir `kind=commercial`. Fim do pedido.

### 3.3 Nova sub-aba "Uso pessoal"

Posição: entre Vendas e Despesas. Numeração das sub-abas (`01`, `02`…) se desloca.

Colunas: `#`, Itens, Pessoas, Produzido em, CPV, Estado.

Rodapé com o **total de CPV do período**, que deve bater com a linha
`perda_operacional` do DRE no mesmo período. Para que batam, a aba usa o mesmo
par de datas do DRE (estado compartilhado na página) e atribui cada linha pela
**data de produção** — o menor `consumed_at` das baixas do orçamento, com
`sale.created_at` como fallback —, exatamente o critério de
`_perda_operacional` em `backend/core/accounting/dre.py`. Divergência entre o
rodapé e o DRE é bug.

Isso exige que `SaleOut` exponha a data de produção: campo novo
`produced_on: date | None`, calculado no mesmo lote (uma query agregada para
todas as linhas, não uma por linha).

Ação por linha: **"registrar como vendido"**, abrindo o mesmo editor da aba
Vendas (seção 4). Ao registrar, o item **permanece na aba Uso pessoal**, com
badge "vendido" e o CPV fora do total de perda. Não pula para Vendas: item que
troca de aba sozinho confunde mais do que ajuda, e a origem pessoal continua
sendo a informação relevante.

Contador do cabeçalho da sub-aba: valor da perda no período, não contagem de
linhas — é o número que importa ali.

### 3.4 Backfill — `0033_sales_quote_kind_backfill`

`sales.quote_kind` nasceu com `server_default='commercial'` e só é reescrito por
`sync_sales()`, que ignora linhas cujo orçamento saiu dos status ativos. Logo,
**orçamentos pessoais arquivados** (`is_stale=true`) criados antes daquela coluna
estão marcados como comerciais e apareceriam na aba errada.

```sql
UPDATE sales s
   SET quote_kind = q.kind
  FROM quotes q
 WHERE q.id = s.quote_id
   AND s.quote_kind IS DISTINCT FROM q.kind;
```

Migração só de dados. `downgrade()` é no-op — não há como saber quais linhas
foram tocadas, e reverter para um valor sabidamente errado não serve a ninguém.
Idempotente: rodar de novo não faz nada.

## 4. Data de venda — pedido #2

### 4.1 Backend

`PATCH /accounting/sales/{id}` muda em três pontos:

1. **Sai o auto-preenchimento silencioso.** Marcar `is_sold=true` sem `sold_at`
   (nem já gravado, nem no payload) retorna **422** com mensagem explícita:
   `"informe a data da venda"`. `confirmed_revenue` mantém o default atual
   (`quote_total`) — o valor tem palpite óbvio, a data não.
2. **Desmarcar limpa.** `is_sold=false` zera `sold_at` e `confirmed_revenue`.
   Hoje os valores ficam, e remarcar depois ressuscita a data velha sem aviso —
   o item entra no mês errado do DRE e nada na tela denuncia.
3. **Resposta completa.** `update_sale` passa a devolver `itens_label`,
   `client_name` e `quote_seq`, hoje omitidos. Sem isso a atualização otimista da
   seção 6 esvaziaria as colunas da linha.

`sold_at` já existe como `Date` no modelo e já é aceito pelo `SaleUpdate` —
**nenhuma migração** para este pedido.

### 4.2 Frontend

O checkbox solto some. No lugar:

```
não vendido   →  [ registrar venda ]
                        │  abre popover inline:
                        │    Data da venda      [21/09/2026]  ← hoje, editável
                        │    Receita confirmada [R$ 340,00 ]  ← total, editável
                        │    [cancelar] [salvar]
                        ▼
vendido       →  21/09/2026  ·  R$ 340,00   [ editar ]  [ desfazer ]
```

- A data vem pré-preenchida com hoje, mas é um campo — não um efeito colateral.
- Item já vendido: data e receita viram botão que reabre o mesmo popover.
- "desfazer venda" é explícito e avisa que data e receita serão apagadas.
- Enquanto salva, `$saveSale.pending` (Spec 0) desabilita e rotula o botão.

### 4.3 Efeito no DRE

Retroagir a data move a venda de mês — que é o objetivo. `compute_dre` e
`compute_dre_monthly` já filtram por `sold_at`; nenhuma mudança no cálculo.

Vale registrar a consequência: editar a data de uma venda antiga **altera um DRE
já fechado**. É o comportamento pedido e correto para uma operação deste porte,
mas a tela deve dizê-lo — aviso no popover ao editar uma venda cuja data cai em
mês anterior ao corrente.

## 5. Busca e filtros — pedido #3

`SearchBar` + `Table` da Spec 1 nas três listas.

| Lista | Busca em | Filtros |
|---|---|---|
| Vendas | `#`, cliente, itens, notas, estado | período; chips de status |
| Uso pessoal | `#`, itens, pessoas, notas | período (compartilhado com o DRE) |
| Despesas | descrição, categoria | período; categoria |

**Chips de status** em Vendas — `todos · a confirmar · vendidos · arquivados` —
substituem o checkbox "mostrar arquivadas", que é um controle de duas posições
fazendo o trabalho de quatro.

**Filtro de período em Vendas**: hoje só o DRE tem. Reaproveita o par de datas já
existente na página, elevado a estado compartilhado entre as sub-abas.

Tudo client-side sobre a lista carregada (Spec 1, seção 4.3), exceto `kind`, que
é parâmetro de API porque separa as abas.

## 6. Performance e estado — correções do review

### 6.1 GET deixa de escrever

`GET /accounting/sales` **não chama mais** `sync_sales()`. O endpoint
`POST /accounting/sync` já existe e não era usado por ninguém.

Novo fluxo da página:

```
mount        → POST /accounting/sync  →  GET /accounting/sales?kind=…
"Atualizar"  → POST /accounting/sync  →  GET /accounting/sales?kind=…
troca de aba → GET /accounting/sales?kind=…          (sem sync)
PATCH        → usa a resposta do PATCH                (sem GET, sem sync)
```

Hoje cada clique em "vendido" dispara `sync_sales()`, que recalcula
`compute_quote_costs` de **todo** orçamento aprovado.

### 6.2 Fim do N+1

`sale_items_label` e `_client_name` fazem hoje uma query por linha. Passam a
carregar em lote: um join para clientes, uma query agregada para os rótulos de
itens, uma para as datas de produção (seção 3.3). A listagem vira número
constante de queries, independente do tamanho da lista.

### 6.3 Atualização otimista

`patchSale` para de chamar `loadSales()`. Usa a `SaleOut` devolvida pelo PATCH
(agora completa, 4.1) para substituir a linha no array. Com `action()` da Spec 0,
o estado "salvando" sai de graça.

## 7. Testes

**Backend**
- `?kind=commercial` não devolve pessoal; `?kind=personal` não devolve comercial;
  sem o parâmetro, devolve ambos (compatibilidade).
- `is_sold=true` sem `sold_at` → 422 com a mensagem esperada.
- `is_sold=true` com `sold_at` → grava a data informada, não a de hoje.
- `is_sold=false` → zera `sold_at` e `confirmed_revenue`; remarcar depois exige
  data de novo (regressão do fantasma).
- Resposta do PATCH traz `itens_label`, `client_name` e `quote_seq`.
- `GET /sales` não altera o banco: contagem e `updated_at` inalterados após o GET.
- Contagem de queries da listagem não cresce com o número de linhas.
- Total de CPV do período na aba pessoal == `perda_operacional` do DRE no mesmo
  período (teste de consistência, com um caso de venda pessoal marcada como
  vendida saindo da perda).
- Migração de backfill: linha `is_stale` com `quote_kind` errado é corrigida;
  rodar duas vezes não muda nada.

**Frontend**
- Popover: abre com hoje, salva a data escolhida, cancela sem gravar.
- Desfazer pede confirmação e limpa a linha.
- Chips e período filtram como esperado; busca casa em itens e notas.

**E2E**
- Registrar uma venda com data retroativa e conferir que ela aparece no DRE do
  mês correspondente, não no corrente.

## 8. Riscos

| Risco | Mitigação |
|---|---|
| Limpar `confirmed_revenue` ao desmarcar frustra um clique errado | Confirmação explícita no "desfazer", dizendo o que será apagado |
| Tirar o sync do GET deixa a lista desatualizada após mudar um orçamento | Sync no mount e no "Atualizar"; o botão fica visível e rotulado |
| Rodapé da aba pessoal divergir do DRE | Mesmo critério de data e mesma fonte; teste de consistência cobre |
| Editar data de venda antiga altera DRE já fechado | Comportamento pedido; aviso na tela quando a data cai em mês anterior |
| Backfill marca errado se `quotes.kind` estiver inconsistente | `sync_sales` é a única fonte de `quote_kind`, e `quotes.kind` é imutável após criação |

## 9. Critério de pronto

- `make test`, `make lint` e `make e2e` verdes.
- Aba Vendas não mostra nenhum orçamento pessoal.
- Nenhuma venda é registrada sem data escolhida por uma pessoa.
- As três listas têm busca; Vendas tem período e chips de status.
- `GET /accounting/sales` não produz escrita, verificado por teste.
- Total da aba Uso pessoal bate com `perda_operacional` do DRE.
