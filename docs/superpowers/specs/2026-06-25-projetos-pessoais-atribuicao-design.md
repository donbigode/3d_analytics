# Atribuição de projetos pessoais (Otávio / Ana / Ambos) — Design

**Data:** 2026-06-25
**Branch:** `feat/projetos-pessoais-atribuicao`

## Objetivo

Permitir marcar **de quem é** cada projeto pessoal — uma ou mais pessoas de uma lista configurável (ex.: Otávio, Ana; ambos = as duas marcadas) — editável **em qualquer status** (inclusive finalizados). A atribuição alimenta:
1. O **export pro Databricks** (camada analítica — "quem sobe mais projeto pessoal").
2. Um **dashboard na aba Insights** (contagem, gramas, custo e evolução mensal por pessoa).

## Decisões

- **Muitos-para-muitos**: um projeto pessoal pode pertencer a 1+ pessoas (marcar Otávio **e** Ana = "ambos"). Generaliza pra um 3º membro.
- **Lista configurável** de pessoas (não enum), gerenciada em **Configurações**.
- Atribuição **só pra `kind=personal`**; ignorada/oculta em comercial.
- Edição **sem gate de status** (endpoint próprio).

## Modelo de dados

Duas tabelas novas (migração `0029_people_quote_people`):

`people`:
| coluna | tipo | nota |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(80), NOT NULL, unique | nome da pessoa |
| `active` | Boolean, default true | inativar sem apagar histórico |
| `sort_order` | Integer, default 0 | ordem na UI |
| `created_at` | DateTime(tz) | |

`quote_people` (join):
| coluna | tipo | nota |
|---|---|---|
| `quote_id` | UUID FK→quotes `ON DELETE CASCADE`, NOT NULL | |
| `person_id` | UUID FK→people `ON DELETE CASCADE`, NOT NULL | |
| PK composta | (`quote_id`, `person_id`) | evita duplicata |

Models exportados em `backend/infra/db/models/__init__.py`. Cleanup nas duas tabelas no `backend/tests/api/conftest.py` (join antes das parents).

## API

**Pessoas (CRUD) — novo router `backend/api/routes/people.py` montado em `/people`:**
- `GET /people` → lista (ordenada por `sort_order, name`).
- `POST /people` `{name}` → cria.
- `PUT /people/{id}` `{name?, active?, sort_order?}` → edita.
- `DELETE /people/{id}` → apaga (cascade no join solta as atribuições).

**Atribuição — em `backend/api/routes/quotes.py`:**
- `PUT /quotes/{id}/people` `{person_ids: [uuid]}` → substitui o conjunto de pessoas do orçamento. **Sem gate de status.** Valida que o orçamento é `personal` (400 se commercial). Reescreve as linhas de `quote_people`.
- `QuoteOut` ganha `person_ids: list[str]` (ids das pessoas atribuídas).

**Schemas:** `PersonOut`, `PersonCreate`, `PersonUpdate`, `QuotePeopleUpdate` em `backend/api/schemas/`.

## Insights — dashboard

Novo endpoint `GET /insights/personal-projects?period_from=&period_to=` em `backend/api/routes/insights.py`, retornando, **por pessoa** (entre as ativas + as que tenham histórico):
- `count` — nº de projetos pessoais atribuídos (no período, por `created_at` do orçamento).
- `grams` — soma de `MaterialConsumption.grams_used` dos itens dos projetos pessoais da pessoa.
- `cpv` — soma do CPV (via `Sale.cpv_calc`/`cpv_override` quando houver venda; senão material × custo) dos projetos da pessoa.
- `monthly` — lista `{month, count}` pra evolução.
- Mais um total `shared_count` (projetos com 2+ pessoas).

**Regra de compartilhado:** projeto marcado pra N pessoas conta **para cada uma** (responde "quem sobe mais"); `shared_count` mostra quantos são compartilhados, pra leitura honesta.

Cálculo num módulo `backend/core/insights/personal_projects.py` (testável isolado), consumido pelo route.

Frontend: painel "Projetos pessoais" em `frontend/src/routes/insights/+page.svelte` — tabela por pessoa (contagem/gramas/custo) + mini-gráfico/série mensal, no estilo dos painéis existentes.

## Onde marcar (frontend)

- **Página do orçamento** (`quotes/[id]/+page.svelte`): bloco "Projeto pessoal de" com **checkboxes** das pessoas ativas, só quando `kind === "personal"`. Salva via `PUT /quotes/{id}/people` (qualquer status). Mostra as marcadas mesmo em finalizado.
- **Lista `/quotes`** (`quotes/+page.svelte`): seletor inline (multi, ex.: dropdown de checkboxes) na linha dos orçamentos pessoais, pra marcar o backlog rápido. Reusa `PUT /quotes/{id}/people`.
- **Configurações** (`settings/+page.svelte`): seção "Pessoas (projetos pessoais)" — listar/adicionar/inativar/reordenar via API `/people`.

**Tipos** em `frontend/src/lib/types.ts`: `Person`, `person_ids` em `Quote`.

## Export / Databricks

Adicionar ao registry `backend/core/export/entities.py`:
- `("people", Person, set())`
- `("quote_people", QuotePerson, set())`

Assim a atribuição (e a lista de pessoas) flui pro data lake no próximo export — base pra análise de "quem sobe mais projeto pessoal".

## Seed

A migração **não** semeia nomes (privacidade/flexibilidade) — Otávio cadastra "Otávio" e "Ana" na tela de Configurações.

## Testes (TDD)

- **Modelo/migração**: aplica `0029` sem erro.
- **People API**: CRUD básico; nome único.
- **Atribuição**: `PUT /quotes/{id}/people` em orçamento **entregue** (finalizado) funciona; reescreve o conjunto; rejeita commercial (400); `QuoteOut.person_ids` reflete.
- **Insights core** (`personal_projects.py`): contagem/gramas/cpv por pessoa; projeto compartilhado conta pra ambos e entra em `shared_count`; respeita período.
- **Export**: `EXPORT_ENTITIES` inclui `people` e `quote_people`.
- **Frontend**: `npm run check` sem erros novos.

## Fora de escopo (v1)

- Histórico/auditoria de quem mudou a atribuição.
- Permissões por pessoa (login separado da Ana) — `people` é só rótulo analítico, desacoplado de `users`.
- Atribuição em orçamento comercial.
