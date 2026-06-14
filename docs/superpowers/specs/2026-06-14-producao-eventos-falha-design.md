# Produção em fila + eventos de falha + insights por IA

**Data:** 2026-06-14
**Status:** aprovado no brainstorming (seções 1–4), pronto para plano de implementação.

## 1. Objetivo

Transformar "Produzir" num fluxo de **fila de produção** com desfecho explícito
(**sucesso** ou **falha**), deduzindo material no momento da produção, e registrar
cada desfecho como um **evento** estruturado. Esses eventos viram a base para a
**aba Insights** sugerir, via IA, "o que vigiar" por material e por tipo de peça —
incluindo taxa de falha e tentativas.

Resolve dores reais da oficina:
- registrar uma impressão que **falhou gastando só material** (ex.: boneco pessoal
  que saiu ruim e não seguiu);
- contar **tentativas/iterações** e acumular **taxa de falha** por material/peça;
- alimentar a IA com o histórico de falhas para recomendações em projetos futuros.

Faseamento: **Fase A** (fluxo + eventos, fundação de dados) e **Fase B** (embeddings,
parsing LLM e sugestões em Insights). Implementadas em sequência, num só spec.

## 2. Estados e fluxo

Dois novos estados em `QuoteStatus` (StrEnum, coluna `String(20)` — sem migração de
enum no banco): **`em_producao`** e **`falhou`**.

`falhou` é distinto de `cancelado`: *cancelado* = abandonado antes de produzir;
*falhou* = tentou, gastou material, não concluiu.

```
Comercial:  draft → orcado → aprovado → [Produzir] → em_producao → [Concluir] → produzido → entregue
Pessoal:    draft → [Produzir] → em_producao → [Concluir] → produzido
                                              ↘ [Falhar] → falhou → [Re-produzir] → em_producao …
```

- **Produzir** (origem `aprovado` comercial, `draft` pessoal, ou `falhou` qualquer):
  abre o modal de spool, **deduz material** (lógica atual + guarda de `filament_m=0`),
  status → `em_producao`, entra na **fila FIFO** da Capacidade.
- **Concluir**: `em_producao → produzido` (sucesso). Cria `ProductionEvent(outcome=success)`.
- **Falhar**: registra `ProductionEvent(outcome=failure, ...)`, status → `falhou`.
- **Re-produzir**: ação própria a partir de `falhou` — inicia novo ciclo (deduz material
  de novo, novo evento). É só "Produzir" aceitando origem `falhou`.

## 3. Modelo de dados

Nova tabela **`production_events`**:

| Campo | Tipo | Observação |
|---|---|---|
| `id` | uuid PK | |
| `quote_id` | uuid FK→quotes, `ON DELETE SET NULL` | evento sobrevive se o orçamento sumir |
| `kind` | string (`commercial`/`personal`) | snapshot |
| `outcome` | string (`success`/`failure`) | |
| `attempts` | int, default 1 | tentativas até o desfecho (usuário informa) |
| `failure_description` | text, nullable | "o que houve" (só em falha) |
| `context` | JSONB | `[{name, material_type, color, manufacturer, filament_m, time_s, is_multi_color, machine, model_source_url}]` por peça |
| `grams_wasted` | numeric(10,2), nullable | material gasto na falha (soma do `MaterialConsumption` do ciclo) |
| `embedding` | `Vector(384)`, nullable | Fase B — preenchido por job |
| `llm_tags` | JSONB, nullable | Fase B — `{causa, parte_afetada, severidade, dica_curta}` |
| `created_at` | timestamptz, default now | |

- Migração cria a tabela; garante `CREATE EXTENSION IF NOT EXISTS vector`; índice
  `ivfflat (embedding vector_cosine_ops)` (segue o padrão de `0006_llm_radar`).
- Material continua deduzido no **Produzir** via `MaterialConsumption` (já existe);
  o evento só *snapshota* `grams_wasted` — sem dupla contagem.
- Decisão: **evento por orçamento** (a unidade que se produz), com contexto **por peça**
  no JSON. `attempts` registrado tanto em sucesso quanto em falha (alimenta taxa real).

## 4. API (backend)

- **`POST /quotes/{id}/transitions/produce`** (ajuste): aceita origem `aprovado`
  (commercial), `draft` (personal) e `falhou` (qualquer). Mantém modal/consumo atual
  e a guarda de `filament_m=0`. Status final → `em_producao` (antes: `produzido`).
- **`POST /quotes/{id}/transitions/complete`**: `em_producao → produzido`.
  Body `{attempts?: int}` (default 1). Cria `ProductionEvent(outcome=success)`.
  Carimba `produced_at`.
- **`POST /quotes/{id}/transitions/fail`**: `em_producao → falhou`.
  Body `{failure_description: str, attempts?: int}`. Cria `ProductionEvent(outcome=failure)`
  com `grams_wasted` = soma do consumo do ciclo. Snapshota `context` a partir dos itens.
- **`POST /quotes/{id}/transitions/deliver`**: inalterado (`produzido → entregue`, comercial).
- **Capacidade** (`/capacity`): novo endpoint read de **fila em produção**
  (`em_producao` em ordem FIFO por `produced_at`/entrada). O forecast de `aprovado`
  existente permanece.
- `_quote_out` e schemas expõem os novos estados; `context`/snapshot montados de
  `QuoteItem.gcode_meta` + spool atribuído.

## 5. UI (frontend)

- **Capacidade** ganha duas seções:
  1. **Em produção (fila FIFO)** — cards dos jobs `em_producao`, cada um com **Concluir**
     e **Falhar**. "Falhar" abre mini-form: descrição (texto) + nº de tentativas.
     "Concluir" pede (opcional) nº de tentativas.
  2. **Aprovados (backlog + ETA)** — o forecast atual, intacto.
- **Tela do orçamento**: botão Produzir leva a `em_producao`; timeline mostra
  `em_producao`/`falhou`; quote `em_producao` mostra atalho "ver na Capacidade";
  quote `falhou` mostra **Re-produzir**.
- **Aba Insights** — nova seção "Atenção na produção" (ver §6).

## 6. Fase B — IA e Insights

**Pipeline (job no scheduler existente):**
1. Para cada `ProductionEvent` de **falha** sem embedding: compõe texto
   (`failure_description` + resumo do `context`: material tipo/cor/fabricante +
   características da peça) → `embeddings.embed` (e5 multilíngue, 384-d) → grava
   `embedding`.
2. **Parsing LLM** (reusa `llm_features/runner.py`, cadeia de providers respeitando
   `preferred_llm_provider`): extrai `llm_tags = {causa, parte_afetada, severidade,
   dica_curta}` da descrição. Em lote, para controlar custo.

**Aba Insights — "Atenção na produção":**
- **(a) Sempre visível, sem LLM:** tabela de **taxa de falha** agregada (`falhas /
  tentativas`) por material (tipo/cor/fabricante) e por bucket de característica da peça
  (alta, multicor, tempo longo). Puro SQL.
- **(b) Sugestões da IA (sob demanda + cache):** botão "Gerar sugestões" → busca vetorial
  (pgvector cosine) das falhas similares + LLM resume "o que vigiar". Resultado **cacheado**
  (padrão `LLMDigest`) para não gastar token à toa. Honra o provider preferido.

**Custo:** agregações SQL são de graça; LLM só sob demanda e cacheado.

## 7. Decisões fixas (do brainstorming)

1. Dedução de material no **Produzir** (entrada na fila), não na conclusão.
2. `falhou` é estado **separado** de `cancelado`; **Re-produzir** é ação própria.
3. Evento **por orçamento** com contexto **por peça**; `attempts` informado no desfecho.
4. `embedding`/`llm_tags` nulos na Fase A; preenchidos por job na Fase B.
5. IA sob demanda + cache; agregações SQL sempre-visíveis e gratuitas.

## 8. Testes (TDD)

- **Backend**: produce → `em_producao` (e re-produce de `falhou`); complete → `produzido`
  + evento success; fail → `falhou` + evento failure com `grams_wasted` e `context`
  snapshot; transições inválidas (409); fila FIFO da capacidade lista `em_producao`.
- **Agregação de taxa de falha** por material/característica (pura, testável sem LLM).
- **Pipeline B**: embedding preenchido para eventos de falha (modelo real ou stub);
  parsing LLM com provider fake; busca vetorial retorna similares; cache de sugestões.
- **Frontend**: `svelte-check` limpo; ações Concluir/Falhar/Re-produzir disparam as
  chamadas certas.

## 9. Faseamento de implementação

- **Fase A**: estados + transições + `production_events` + Capacidade (fila/ações) +
  Re-produzir + taxa de falha agregada em Insights (SQL). Entrega valor sozinha.
- **Fase B**: embeddings + parsing LLM + sugestões sob demanda na aba Insights.
