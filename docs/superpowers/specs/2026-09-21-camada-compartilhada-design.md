# Spec 0 — Camada compartilhada (frontend + fatiar `quotes.py`)

**Data:** 2026-09-21
**Status:** aprovado no brainstorming, aguardando revisão da spec
**Ordem:** primeira das quatro. Barateia as Specs 1, 2 e 3.

## 1. Contexto e objetivo

O review de UX levantou cinco pedidos de produto (Specs 1–3). Ao medir o código
para planejá-los, o gargalo apareceu **antes** das features: os dois arquivos que
todas as specs tocam — `frontend/src/routes/accounting/+page.svelte` (1.103 linhas)
e `frontend/src/routes/quotes/[id]/+page.svelte` (1.879 linhas) — carregam uma
quantidade grande de código que deveria ser compartilhado e não é.

Medição (radon + contagem direta, 2026-09-21):

```
Backend  · média de complexidade ciclomática: B (5,8)
         · nada acima de B nos arquivos do pedido
         · único alerta: quotes.py com Maintainability Index grau C (0,75)
           → causa é TAMANHO (1.171 linhas), não complexidade por função
         · pior função do backend: build_dre_xlsx — D (21)

Frontend · 98 blocos try/catch quase idênticos espalhados por 16 páginas
         · handleApiError invocado 88 vezes
         · money/fmtMoney/Intl.NumberFormat reimplementado em 6 arquivos
         · fmtDate/shortDate/fmtNum/fmtDur: 14 definições em 9 arquivos
         · 2.024 linhas de <style> dentro de páginas
           (accounting: 436 · trends: 361 · insights: 356)
```

**Objetivo:** extrair a camada compartilhada que já existe implicitamente, de modo
que as Specs 1–3 sejam escritas contra ela em vez de engrossá-la. Nenhuma mudança
de comportamento visível ao usuário.

### Nota sobre Jinja

O pedido original cogitou usar Jinja para reduzir esforço. **Decisão: não.** Trocar
SvelteKit por Jinja seria reescrever o app, não simplificá-lo — as telas caras são
justamente as interativas (editores inline na tabela de peças, popover de venda,
filtro ao vivo, upload de foto), que em Jinja virariam reload de página inteira por
clique, ou HTMX, que é mais uma dependência e outro modelo mental.

Jinja já está no projeto onde ele ganha: `backend/infra/pdf/templates/`. O que vale
fazer ali está na seção 6.

## 2. Escopo

**Dentro:**
- `$lib/resource.ts` — helpers `resource()` e `action()`.
- `$lib/format.ts` — formatadores pt-BR únicos.
- Migração das classes compartilhadas de `<style>` de página para `app.css`.
- `backend/api/routes/quotes.py` → pacote `backend/api/routes/quotes/`.
- Tabela declarativa de transições de status.

**Fora:**
- Qualquer mudança de comportamento, endpoint, schema ou layout visível.
- Refatorar `trends/`, `insights/`, `library/` além da adoção dos helpers — são
  páginas que nenhuma das outras specs toca; entram só se sobrar folga.
- `build_dre_xlsx` (complexidade D, 21). Anotado como dívida; ver seção 6.

## 3. `resource()` e `action()`

### Problema

O padrão abaixo se repete 98 vezes, com variações mínimas de nome de variável:

```ts
async function loadSales() {
  salesError = ""; salesLoading = true;
  try { sales = await api<Sale[]>("/accounting/sales"); }
  catch (err) { handleApiError(err); salesError = errorMessage(err, "Falha ao carregar vendas."); }
  finally { salesLoading = false; }
}
```

### Contrato

```ts
// $lib/resource.ts

/** Leitura: encapsula loading/error/data + reload. */
export function resource<T>(
  fetcher: () => Promise<T>,
  opts?: { initial?: T; errorMessage?: string; auto?: boolean },
): Readable<{ loading: boolean; error: string; data: T | undefined }> & {
  reload: () => Promise<void>;
  set: (v: T) => void;          // atualização otimista de uma linha
};

/** Mutação: encapsula pending/error e devolve o resultado. */
export function action<A extends unknown[], R>(
  fn: (...args: A) => Promise<R>,
  opts?: { errorMessage?: string },
): Readable<{ pending: boolean; error: string }> & {
  run: (...args: A) => Promise<R | undefined>;
};
```

Uso:

```ts
const sales = resource(() => api<Sale[]>("/accounting/sales"),
                       { errorMessage: "Falha ao carregar vendas." });
const saveSale = action((id: string, body: Partial<Sale>) =>
  api<Sale>(`/accounting/sales/${id}`, { method: "PATCH", ... }));
```

```svelte
{#if $sales.loading}…{:else if $sales.error}<div class="alert">{$sales.error}</div>{/if}
<button disabled={$saveSale.pending}>{$saveSale.pending ? "Salvando…" : "Salvar"}</button>
```

Ambos chamam `handleApiError` internamente (preservando o redirect de sessão
expirada de `$lib/guard.ts`) e usam `errorMessage()` para o texto.

**Ganho colateral:** o `pending` do `action()` entrega o estado "salvando" que o
review apontou como ausente no contábil — sem código de tela.

98 blocos try/catch passam a ~16 declarações.

## 4. `$lib/format.ts`

Uma implementação de cada formatador, pt-BR, com os objetos `Intl` instanciados
uma vez no módulo (hoje `quotes/+page.svelte` chama `toLocaleString` por célula
renderizada).

```ts
export function money(v: string | number | null | undefined): string;  // R$ 1.234,56 · "—" se nulo
export function date(v: string | null): string;                        // 21/09/2026
export function dateTime(v: string | null): string;                    // 21/09/26 14:30
export function num(v: unknown, decimals = 2): string;                 // 1.234,56
export function dur(seconds: number | null): string;                   // 2h 15min
export function pct(v: unknown, decimals = 1): string;                 // 12,5%
```

Regra de nulo unificada: `null`/`undefined`/`""`/`NaN` → `"—"`. Hoje as 14
definições divergem — algumas devolvem `"—"`, outras `"0"`, outras a string crua.
A migração deve conferir caso a caso qual comportamento a tela espera antes de
trocar, e registrar no PR qualquer lugar onde o resultado visível mude.

## 5. Estilos compartilhados → `app.css`

Classes hoje redeclaradas em várias páginas, com valores iguais ou quase:
`.panel`, `.panel-head`, `.section-title`, `.table-wrap`, `.tag`, `.badge`,
`.empty`, `.alert`, `.hint`, `.subtab`, `.chip`, `.field`, `.toggle`, `.count`.

Sobem para `app.css`. Fica em `<style>` de página só o que é genuinamente local
(ex.: `.people-chips`, `.fil-stack`, `.photo-grid`).

Método, para não quebrar visual: para cada classe, comparar as declarações
concorrentes, escolher a versão canônica, subir, e **remover** as locais uma
página por vez conferindo a tela. Onde uma página divergir de propósito, ela
mantém o override local com comentário dizendo por quê.

Estimativa: ~40% das 2.024 linhas. O ganho maior é futuro — a passada responsiva
da Spec 1 passa a acontecer em um arquivo em vez de dezesseis.

## 6. `quotes.py` → pacote

### Estrutura

```
backend/api/routes/quotes/
  __init__.py      # APIRouter + include dos submódulos; ordem de rotas preservada
  _shared.py       # _quote_out, _now, _get_settings_row, _photo_out, guards
  crud.py          # POST "" · GET "" · GET/PUT /{id}
  items.py         # items: POST · PUT · DELETE · reparse
  services.py      # linhas de serviço
  transitions.py   # tabela de transições + apply_production
  photos.py        # upload/serve/delete de fotos
  pdf.py           # GET /{id}/pdf
  people.py        # PUT /{id}/people
```

O caminho importado por `backend/app.py` não muda (`backend.api.routes.quotes`
continua expondo `router`). Atenção a uma armadilha de FastAPI: rotas literais
precisam vir antes das paramétricas — `GET /photos/{photo_id}/raw` está hoje
declarado depois de `GET /{quote_id}`, e funciona por não colidir. O
`__init__.py` deve incluir os submódulos numa ordem que preserve o
comportamento atual, e os testes de rota confirmam.

### Transições declarativas

As 8 transições repetem *pega quote → valida status de origem → seta status →
carimba timestamp → commita → devolve*. Viram:

```python
@dataclass(frozen=True)
class T:
    from_: set[QuoteStatus]
    to: QuoteStatus
    stamp: str | None = None
    kinds: set[QuoteKind] | None = None          # None = qualquer tipo
    guard: Callable | None = None                # ex.: _assert_materials_resolved
    on_apply: Callable | None = None             # ex.: registra ProductionEvent

TRANSITIONS: dict[str, T] = {
    "finalize": T(from_={DRAFT},           to=ORCADO,      stamp="finalized_at"),
    "reopen":   T(from_={ORCADO},          to=DRAFT,       stamp=None),
    "approve":  T(from_={ORCADO},          to=APROVADO,    stamp="approved_at",
                  kinds={COMMERCIAL}, guard=_assert_materials_resolved),
    "complete": T(from_={EM_PRODUCAO},     to=PRODUZIDO,   stamp="produced_at",
                  on_apply=_record_success),
    "fail":     T(from_={EM_PRODUCAO},     to=FALHOU,      on_apply=_record_failure),
    "deliver":  T(from_={PRODUZIDO},       to=ENTREGUE,    stamp="delivered_at"),
    "cancel":   T(from_=ANY_EXCEPT_FINAL,  to=CANCELADO,   stamp="cancelled_at"),
}
```

`produce` **fica de fora da tabela**: tem payload próprio (`ProduceRequest`),
regra de origem por tipo (comercial entra de `aprovado`/`falhou`, pessoal de
`draft`/`falhou`) e efeito colateral pesado (`apply_production` debita spools).
Forçá-lo na tabela criaria mais complexidade do que remove. Permanece explícito
em `transitions.py`, ao lado da tabela.

Ganho: ~200 linhas repetidas a menos, e o fluxo de status inteiro passa a caber
numa tela. Hoje, responder "de onde dá pra ir pra onde" exige ler 8 funções
espalhadas em 1.171 linhas.

### Rede de segurança

Refactor sem mudança de comportamento, coberto por testes já existentes:
`backend/tests/api/test_quotes_lifecycle.py` (359 linhas),
`test_quotes_personal.py` (133), `test_production_flow.py` (132),
`test_quote_photos.py` (77).

**Regra de execução:** rodar a suíte inteira *antes* de tocar em qualquer coisa e
guardar a saída. Cada passo do refactor termina com a mesma suíte verde e o mesmo
número de testes. Nenhum teste é alterado durante o refactor — se um teste
precisar mudar, o comportamento mudou, e isso é bug do refactor.

### Jinja: o que vale

Não trocar o app. Mas as Specs 1 e 3 já mexem em `quote.html` e `_base.html`
(número humano no cabeçalho; filamento). Ao fazê-lo, consolidar macros de moeda
e data nos templates, para a formatação pt-BR não ter duas verdades entre Python
e TypeScript.

`build_dre_xlsx` (complexidade D, 21 — a pior função do backend) monta layout na
unha em Python. **Fora do escopo desta spec**, mas anotado: se o DRE em PDF um
dia for pedido, o caminho é um template Jinja, e a mesma refatoração serve ao
XLSX.

## 7. Plano de execução

Ordem que mantém o app funcionando a cada passo:

1. `format.ts` + adoção em `accounting/` e `quotes/` (as páginas das próximas specs).
2. `resource.ts` + adoção nas mesmas duas páginas.
3. Estilos compartilhados → `app.css`, uma página por vez.
4. `quotes.py` → pacote (sem tocar em lógica).
5. Tabela de transições.
6. Adoção dos helpers nas demais páginas, conforme folga.

Passos 1–3 são frontend puro; 4–5 backend puro. Podem correr em paralelo.

## 8. Testes

- **Backend:** nenhum teste novo. A suíte existente é o critério — mesma contagem,
  mesmo verde, antes e depois. `make test` e `make lint` via compose.
- **Frontend:** testes unitários novos para `format.ts` (tabela de casos, incluindo
  todos os nulos) e `resource.ts` (sucesso, erro, `pending`, `reload`). São as duas
  primeiras peças de lógica pura do frontend e merecem cobertura, porque toda tela
  passa a depender delas.
- **E2E:** o happy-path Playwright existente (`make e2e`) roda ao fim de cada passo
  como verificação de que nada visível quebrou.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| Unificar formatadores muda texto na tela sem ninguém notar | Comparar as 14 definições antes de trocar; registrar no PR cada diferença visível |
| Subir estilo compartilhado quebra layout de uma página | Uma página por vez, conferindo a tela; override local permitido com comentário |
| Reordenar rotas no pacote muda resolução do FastAPI | Preservar ordem de include; testes de rota confirmam |
| Refactor "aproveitar pra melhorar" vaza escopo | Comportamento idêntico é regra dura: teste que precisa mudar = bug do refactor |

## 10. Critério de pronto

- `make test` e `make lint` verdes, com a mesma contagem de testes do início.
- `make e2e` verde.
- `radon mi backend` não reporta mais grau C em `quotes/`.
- Contagem de `catch (err)` em `accounting/` e `quotes/` reduzida a zero (o
  tratamento vive nos helpers).
- Nenhuma migração, nenhum endpoint novo, nenhuma mudança visível ao usuário.
