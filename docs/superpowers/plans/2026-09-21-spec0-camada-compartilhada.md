# Spec 0 — Camada compartilhada: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extrair a camada compartilhada do frontend (helpers de carga, formatadores, estilos) e fatiar `quotes.py`, sem nenhuma mudança de comportamento visível.

**Architecture:** Dois helpers de store (`resource`/`action`) substituem 98 blocos try/catch; um módulo `format.ts` substitui 14 formatadores duplicados; classes CSS repetidas sobem para `app.css`; `backend/api/routes/quotes.py` (1.171 linhas) vira pacote e as 8 transições de status viram tabela declarativa.

**Tech Stack:** SvelteKit 2 + Svelte 5, TypeScript, Vitest (novo), FastAPI, SQLAlchemy async, Alembic, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-21-camada-compartilhada-design.md`

## Global Constraints

- **Nenhuma mudança de comportamento visível.** Teste que precisa mudar = bug do refactor.
- **Nenhuma migração, nenhum endpoint novo, nenhuma mudança de schema.**
- Tudo roda via Docker Compose: `make test`, `make lint`, `make e2e`. Nunca `pytest` direto no host.
- Antes de tocar em qualquer coisa: rodar `make test` e guardar a contagem de testes. Cada tarefa termina com a mesma contagem e o mesmo verde.
- Idioma do código e dos comentários: português nos comentários de domínio, seguindo o que já existe nos arquivos.
- Commits frequentes, um por tarefa no mínimo.
- Mensagens de commit terminam com `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

### Task 0: Linha de base

**Files:**
- Nenhum. Tarefa de medição.

**Interfaces:**
- Consumes: nada.
- Produces: o número de testes que todas as tarefas seguintes devem preservar.

- [ ] **Step 1: Subir o ambiente e rodar a suíte**

```bash
make up-db
make test 2>&1 | tail -20
```

Expected: suíte verde. Anotar a linha final, por exemplo `=== 214 passed in 38.21s ===`.

- [ ] **Step 2: Registrar a linha de base no plano**

Editar este arquivo, substituindo a linha abaixo pelo número real:

```
LINHA DE BASE: <N> testes passando em <data>
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-09-21-spec0-camada-compartilhada.md
git commit -m "chore(plan): registra linha de base da suíte antes do refactor

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 1: Vitest + `format.ts`

O frontend não tem runner de teste nenhum hoje. Esta tarefa instala o Vitest e entrega a primeira peça de lógica pura testada.

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/lib/format.ts`
- Test: `frontend/src/lib/format.test.ts`

**Interfaces:**
- Consumes: nada.
- Produces:
  ```ts
  export function money(v: string | number | null | undefined): string
  export function date(v: string | null | undefined): string
  export function dateTime(v: string | null | undefined): string
  export function num(v: unknown, decimals?: number): string   // default 2
  export function dur(seconds: number | null | undefined): string
  export function pct(v: unknown, decimals?: number): string    // default 1
  export const DASH = "—"
  ```

- [ ] **Step 1: Instalar o Vitest**

```bash
cd frontend && npm install --save-dev vitest@^2.1.0
```

- [ ] **Step 2: Configurar o Vitest no `vite.config.ts`**

Adicionar o bloco `test` ao objeto passado para `defineConfig`, logo depois de `server`:

```ts
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    alias: {
      // $app/* só existe no runtime do SvelteKit; os testes de lógica pura
      // não tocam navegação, mas o grafo de imports passa por aqui.
      "$app/navigation": new URL("./src/test/stubs/navigation.ts", import.meta.url).pathname,
      "$app/stores": new URL("./src/test/stubs/stores.ts", import.meta.url).pathname,
    },
  },
```

E adicionar o script ao `frontend/package.json`, dentro de `"scripts"`:

```json
    "test": "vitest run",
    "test:watch": "vitest",
```

- [ ] **Step 3: Criar os stubs do `$app`**

Create `frontend/src/test/stubs/navigation.ts`:

```ts
/** Stub de $app/navigation para os testes unitários. Registra as chamadas
 *  para que os testes possam afirmar sobre redirecionamento sem um router. */
export const gotoCalls: string[] = [];
export function goto(url: string): Promise<void> {
  gotoCalls.push(url);
  return Promise.resolve();
}
```

Create `frontend/src/test/stubs/stores.ts`:

```ts
import { readable } from "svelte/store";
export const page = readable({ url: new URL("http://localhost/") });
```

- [ ] **Step 4: Escrever o teste que falha**

Create `frontend/src/lib/format.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { money, date, dateTime, num, dur, pct, DASH } from "./format";

describe("money", () => {
  it("formata em BRL pt-BR", () => {
    expect(money(1234.56)).toBe("R$ 1.234,56");
  });
  it("aceita string numérica vinda da API (Decimal serializado)", () => {
    expect(money("340.00")).toBe("R$ 340,00");
  });
  it("devolve travessão para nulo, indefinido, vazio e não-numérico", () => {
    expect(money(null)).toBe(DASH);
    expect(money(undefined)).toBe(DASH);
    expect(money("")).toBe(DASH);
    expect(money("abc")).toBe(DASH);
  });
  it("formata zero como valor, não como vazio", () => {
    expect(money(0)).toBe("R$ 0,00");
  });
});

describe("date", () => {
  it("formata ISO date como dd/mm/aaaa", () => {
    expect(date("2026-09-21")).toBe("21/09/2026");
  });
  it("aceita ISO datetime e ignora a hora", () => {
    expect(date("2026-09-21T14:30:00Z")).toBe("21/09/2026");
  });
  it("devolve travessão para nulo e vazio", () => {
    expect(date(null)).toBe(DASH);
    expect(date("")).toBe(DASH);
  });
});

describe("dateTime", () => {
  it("formata data curta com hora", () => {
    expect(dateTime("2026-09-21T14:30:00")).toBe("21/09/26 14:30");
  });
  it("devolve travessão para nulo", () => {
    expect(dateTime(null)).toBe(DASH);
  });
});

describe("num", () => {
  it("usa duas casas por padrão", () => {
    expect(num(1234.5)).toBe("1.234,50");
  });
  it("respeita o número de casas pedido", () => {
    expect(num(48.24, 1)).toBe("48,2");
  });
  it("devolve travessão para nulo e não-numérico", () => {
    expect(num(null)).toBe(DASH);
    expect(num("abc")).toBe(DASH);
  });
});

describe("dur", () => {
  it("formata horas e minutos", () => {
    expect(dur(8100)).toBe("2h 15min");
  });
  it("omite a hora quando menor que uma", () => {
    expect(dur(900)).toBe("15min");
  });
  it("devolve travessão para nulo", () => {
    expect(dur(null)).toBe(DASH);
  });
  it("formata zero como 0min, não como travessão", () => {
    expect(dur(0)).toBe("0min");
  });
});

describe("pct", () => {
  it("usa uma casa por padrão", () => {
    expect(pct(12.54)).toBe("12,5%");
  });
  it("devolve travessão para nulo", () => {
    expect(pct(null)).toBe(DASH);
  });
});
```

- [ ] **Step 5: Rodar o teste e confirmar que falha**

```bash
cd frontend && npm test
```

Expected: FAIL — `Failed to resolve import "./format"`.

- [ ] **Step 6: Implementar `format.ts`**

Create `frontend/src/lib/format.ts`:

```ts
/** Formatadores pt-BR do app. Uma implementação de cada, com os objetos Intl
 *  instanciados uma vez no módulo — antes disto havia 14 definições
 *  concorrentes em 9 arquivos, com regras de nulo divergentes.
 *
 *  Regra única de ausência: null, undefined, "" e NaN viram DASH. */

export const DASH = "—";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function toDate(v: string | null | undefined): Date | null {
  if (!v) return null;
  // Data pura (YYYY-MM-DD) é construída como local para não recuar um dia
  // por fuso — o backend manda date sem hora em sold_at, incurred_at etc.
  const pure = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  if (pure) return new Date(Number(pure[1]), Number(pure[2]) - 1, Number(pure[3]));
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function money(v: string | number | null | undefined): string {
  const n = toNumber(v);
  return n === null ? DASH : BRL.format(n);
}

export function date(v: string | null | undefined): string {
  const d = toDate(v);
  return d === null ? DASH : `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

export function dateTime(v: string | null | undefined): string {
  const d = toDate(v);
  if (d === null) return DASH;
  const ano = String(d.getFullYear()).slice(2);
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${ano} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function num(v: unknown, decimals = 2): string {
  const n = toNumber(v);
  if (n === null) return DASH;
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function dur(seconds: number | null | undefined): string {
  const n = toNumber(seconds);
  if (n === null) return DASH;
  const total = Math.round(n / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
}

export function pct(v: unknown, decimals = 1): string {
  const n = toNumber(v);
  return n === null ? DASH : `${num(n, decimals)}%`;
}
```

- [ ] **Step 7: Rodar o teste e confirmar que passa**

```bash
cd frontend && npm test
```

Expected: PASS, 20 testes.

- [ ] **Step 8: Confirmar que o build do frontend não quebrou**

```bash
cd frontend && npm run check && npm run build
```

Expected: sem erro de tipo, build conclui.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts \
        frontend/src/lib/format.ts frontend/src/lib/format.test.ts frontend/src/test/
git commit -m "feat(frontend): vitest + \$lib/format.ts com formatadores pt-BR únicos

Primeira peça de lógica pura testada do frontend. Substitui 14 definições
concorrentes de formatador espalhadas por 9 arquivos, unificando a regra
de ausência (null/undefined/\"\"/NaN -> travessão).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `resource()` e `action()`

**Files:**
- Create: `frontend/src/lib/resource.ts`
- Test: `frontend/src/lib/resource.test.ts`

**Interfaces:**
- Consumes: `api`, `errorMessage` de `$lib/api`; `handleApiError` de `$lib/guard`.
- Produces:
  ```ts
  export type ResourceState<T> = { loading: boolean; error: string; data: T | undefined };
  export type Resource<T> = Readable<ResourceState<T>> & {
    reload: () => Promise<void>;
    set: (v: T) => void;
  };
  export function resource<T>(
    fetcher: () => Promise<T>,
    opts?: { initial?: T; errorMessage?: string; auto?: boolean },
  ): Resource<T>;

  export type ActionState = { pending: boolean; error: string };
  export type Action<A extends unknown[], R> = Readable<ActionState> & {
    run: (...args: A) => Promise<R | undefined>;
  };
  export function action<A extends unknown[], R>(
    fn: (...args: A) => Promise<R>,
    opts?: { errorMessage?: string },
  ): Action<A, R>;
  ```

- [ ] **Step 1: Escrever o teste que falha**

Create `frontend/src/lib/resource.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { get } from "svelte/store";
import { resource, action } from "./resource";
import { ApiError } from "./api";
import { gotoCalls } from "../test/stubs/navigation";

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("resource", () => {
  it("não carrega sozinho quando auto=false", async () => {
    const fetcher = vi.fn().mockResolvedValue([1, 2]);
    const r = resource(fetcher, { auto: false });
    await tick();
    expect(fetcher).not.toHaveBeenCalled();
    expect(get(r).data).toBeUndefined();
  });

  it("carrega no reload e expõe os dados", async () => {
    const r = resource(() => Promise.resolve([1, 2]), { auto: false });
    await r.reload();
    expect(get(r).data).toEqual([1, 2]);
    expect(get(r).loading).toBe(false);
    expect(get(r).error).toBe("");
  });

  it("marca loading durante a carga", async () => {
    let solta: (v: number[]) => void = () => {};
    const r = resource(() => new Promise<number[]>((res) => { solta = res; }), { auto: false });
    const p = r.reload();
    expect(get(r).loading).toBe(true);
    solta([9]);
    await p;
    expect(get(r).loading).toBe(false);
  });

  it("captura o erro e usa a mensagem configurada", async () => {
    const r = resource(
      () => Promise.reject(new ApiError(500, null)),
      { auto: false, errorMessage: "Falha ao carregar vendas." },
    );
    await r.reload();
    expect(get(r).error).toContain("Falha ao carregar vendas.");
    expect(get(r).loading).toBe(false);
  });

  it("limpa o erro de uma carga anterior ao recarregar com sucesso", async () => {
    let falhar = true;
    const r = resource(
      () => (falhar ? Promise.reject(new ApiError(500, null)) : Promise.resolve([1])),
      { auto: false },
    );
    await r.reload();
    expect(get(r).error).not.toBe("");
    falhar = false;
    await r.reload();
    expect(get(r).error).toBe("");
    expect(get(r).data).toEqual([1]);
  });

  it("redireciona para /login em 401", async () => {
    gotoCalls.length = 0;
    const r = resource(() => Promise.reject(new ApiError(401, null)), { auto: false });
    await r.reload();
    expect(gotoCalls).toContain("/login");
  });

  it("set troca os dados sem refazer a chamada (atualização otimista)", async () => {
    const fetcher = vi.fn().mockResolvedValue([1]);
    const r = resource(fetcher, { auto: false });
    await r.reload();
    r.set([1, 2, 3]);
    expect(get(r).data).toEqual([1, 2, 3]);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("action", () => {
  it("marca pending durante a execução e devolve o resultado", async () => {
    let solta: (v: string) => void = () => {};
    const a = action(() => new Promise<string>((res) => { solta = res; }));
    const p = a.run();
    expect(get(a).pending).toBe(true);
    solta("ok");
    expect(await p).toBe("ok");
    expect(get(a).pending).toBe(false);
  });

  it("captura o erro, devolve undefined e não propaga", async () => {
    const a = action(() => Promise.reject(new ApiError(409, null)), {
      errorMessage: "Falha ao salvar venda.",
    });
    const res = await a.run();
    expect(res).toBeUndefined();
    expect(get(a).error).not.toBe("");
    expect(get(a).pending).toBe(false);
  });

  it("limpa o erro anterior numa execução bem-sucedida", async () => {
    let falhar = true;
    const a = action(() => (falhar ? Promise.reject(new ApiError(409, null)) : Promise.resolve(1)));
    await a.run();
    expect(get(a).error).not.toBe("");
    falhar = false;
    await a.run();
    expect(get(a).error).toBe("");
  });

  it("repassa os argumentos para a função", async () => {
    const fn = vi.fn().mockResolvedValue(null);
    const a = action(fn as (id: string, body: object) => Promise<null>);
    await a.run("abc", { x: 1 });
    expect(fn).toHaveBeenCalledWith("abc", { x: 1 });
  });
});
```

- [ ] **Step 2: Rodar o teste e confirmar que falha**

```bash
cd frontend && npm test
```

Expected: FAIL — `Failed to resolve import "./resource"`.

- [ ] **Step 3: Implementar `resource.ts`**

Create `frontend/src/lib/resource.ts`:

```ts
import { writable, type Readable } from "svelte/store";
import { errorMessage } from "$lib/api";
import { handleApiError } from "$lib/guard";

/** Helpers de carga e mutação.
 *
 *  Antes disto, cada função de cada página repetia o mesmo bloco
 *  loading/try/catch/handleApiError/errorMessage/finally — 98 vezes em
 *  16 páginas. Aqui o tratamento vive num lugar só, e o `pending` do
 *  action() dá o estado "salvando" de graça para qualquer tela. */

export type ResourceState<T> = { loading: boolean; error: string; data: T | undefined };

export type Resource<T> = Readable<ResourceState<T>> & {
  reload: () => Promise<void>;
  set: (v: T) => void;
};

export function resource<T>(
  fetcher: () => Promise<T>,
  opts: { initial?: T; errorMessage?: string; auto?: boolean } = {},
): Resource<T> {
  const { subscribe, update } = writable<ResourceState<T>>({
    loading: false,
    error: "",
    data: opts.initial,
  });

  async function reload(): Promise<void> {
    update((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await fetcher();
      update((s) => ({ ...s, loading: false, error: "", data }));
    } catch (err) {
      handleApiError(err);
      update((s) => ({ ...s, loading: false, error: errorMessage(err, opts.errorMessage) }));
    }
  }

  function set(v: T): void {
    update((s) => ({ ...s, data: v }));
  }

  if (opts.auto !== false) void reload();

  return { subscribe, reload, set };
}

export type ActionState = { pending: boolean; error: string };

export type Action<A extends unknown[], R> = Readable<ActionState> & {
  run: (...args: A) => Promise<R | undefined>;
};

export function action<A extends unknown[], R>(
  fn: (...args: A) => Promise<R>,
  opts: { errorMessage?: string } = {},
): Action<A, R> {
  const { subscribe, set } = writable<ActionState>({ pending: false, error: "" });

  async function run(...args: A): Promise<R | undefined> {
    set({ pending: true, error: "" });
    try {
      const res = await fn(...args);
      set({ pending: false, error: "" });
      return res;
    } catch (err) {
      handleApiError(err);
      set({ pending: false, error: errorMessage(err, opts.errorMessage) });
      return undefined;
    }
  }

  return { subscribe, run };
}
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

```bash
cd frontend && npm test
```

Expected: PASS, 31 testes no total (20 de format + 11 de resource).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/resource.ts frontend/src/lib/resource.test.ts
git commit -m "feat(frontend): helpers resource() e action()

Encapsulam loading/error/data e pending/error, com handleApiError e
errorMessage por dentro. Substituem o bloco try/catch repetido 98 vezes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Adotar `format.ts` em Contábil e Orçamentos

São as duas páginas que as Specs 1–3 vão reescrever. Adotar aqui primeiro evita conflito depois.

**Files:**
- Modify: `frontend/src/routes/accounting/+page.svelte` (remove `BRL`, `money`, `shortDate`)
- Modify: `frontend/src/routes/quotes/+page.svelte` (remove `fmtMoney`, `fmtDate`)
- Modify: `frontend/src/routes/quotes/[id]/+page.svelte` (remove `fmtMoney`, `fmtNum`, `fmtDur`, `fmtDate`)

**Interfaces:**
- Consumes: `money`, `date`, `dateTime`, `num`, `dur`, `DASH` de `$lib/format` (Task 1).
- Produces: nada para tarefas seguintes.

- [ ] **Step 1: Levantar as divergências antes de trocar**

Este é o passo que evita mudança silenciosa de tela. Para cada formatador local, comparar com o de `format.ts`:

```bash
cd /Users/orochage/Codes/3d_analytics
grep -n "function money\|function fmtMoney\|function shortDate\|function fmtDate\|function fmtNum\|function fmtDur" \
  frontend/src/routes/accounting/+page.svelte \
  frontend/src/routes/quotes/+page.svelte \
  "frontend/src/routes/quotes/[id]/+page.svelte"
```

Ler cada definição e anotar num scratch as diferenças de comportamento. Divergências já conhecidas:

| Local | Comportamento antigo | Novo (`format.ts`) |
|---|---|---|
| `accounting.money` | `money(null)` → `"R$ 0,00"` (usa `?? 0`) | `DASH` |
| `accounting.shortDate` | `"21/09/2026"` via split/reverse | igual |
| `quotes.fmtDate` | `dateTime` com ano de 2 dígitos | `dateTime` — igual |
| `quotes.fmtMoney` | `toLocaleString` por célula | `money` — igual |

A mudança de `money(null)` é **intencional e desejada** (a Spec 0 §4 unifica a regra), mas precisa ser conferida na tela: onde hoje aparece `R$ 0,00` por dado ausente, passará a aparecer `—`. Conferir que nenhuma coluna de total legítimo zerado caia nesse caso — totais zerados chegam como `"0"`/`0`, não como `null`, e continuam mostrando `R$ 0,00`.

- [ ] **Step 2: Trocar em `accounting/+page.svelte`**

Remover do `<script>` o bloco `BRL`/`money`/`shortDate` (linhas ~57-68) e adicionar ao topo dos imports:

```ts
  import { money, date as fmtDate } from "$lib/format";
```

Trocar as chamadas `shortDate(...)` por `fmtDate(...)`. As chamadas `money(...)` seguem com o mesmo nome.

- [ ] **Step 3: Trocar em `quotes/+page.svelte`**

Remover `fmtMoney` e `fmtDate` do `<script>` e adicionar:

```ts
  import { money as fmtMoney, dateTime as fmtDate } from "$lib/format";
```

Os nomes locais são mantidos por alias, então o markup não muda.

- [ ] **Step 4: Trocar em `quotes/[id]/+page.svelte`**

Remover `fmtMoney`, `fmtNum`, `fmtDur`, `fmtDate` do `<script>` e adicionar:

```ts
  import { money as fmtMoney, num as fmtNum, dur as fmtDur, dateTime as fmtDate } from "$lib/format";
```

Atenção: `fmtNum` local pode ter assinatura `(v, decimals)` — conferir que bate com a de `format.ts` (`num(v, decimals = 2)`). Se o local usava default diferente, passar o valor explicitamente nas chamadas.

- [ ] **Step 5: Verificar tipos e build**

```bash
cd frontend && npm run check && npm run build
```

Expected: sem erro.

- [ ] **Step 6: Conferir as três telas no app**

```bash
make up
```

Abrir `/accounting`, `/quotes` e um orçamento produzido. Conferir moeda, data e duração em cada coluna contra o comportamento anotado no Step 1. Qualquer diferença não prevista é regressão — corrigir antes de commitar.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/accounting/+page.svelte frontend/src/routes/quotes/
git commit -m "refactor(frontend): contábil e orçamentos usam \$lib/format

Remove 8 definições locais de formatador. Mudança visível prevista e
conferida: valor nulo passa de 'R\$ 0,00' para travessão no contábil.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Adotar `resource`/`action` no Contábil

**Files:**
- Modify: `frontend/src/routes/accounting/+page.svelte`

**Interfaces:**
- Consumes: `resource`, `action` de `$lib/resource` (Task 2).
- Produces: nada.

- [ ] **Step 1: Substituir as cargas**

No `<script>`, trocar os pares variável/flag/erro por recursos. Exemplo para vendas — as variáveis `sales`, `salesError`, `salesLoading` e a função `loadSales` (linhas ~19-22 e ~76-88) viram:

```ts
  import { resource, action } from "$lib/resource";

  $: salesUrl = `/accounting/sales${showStale ? "" : "?is_stale=false"}`;
  const sales = resource(() => api<Sale[]>(salesUrl), {
    initial: [],
    errorMessage: "Falha ao carregar vendas.",
    auto: false,
  });
```

No markup, `sales` vira `$sales.data ?? []`, `salesLoading` vira `$sales.loading`, `salesError` vira `$sales.error`, e `loadSales()` vira `sales.reload()`.

Repetir para `expenses`/`expError`/`expLoading`, `dre`/`dreLoading`/`dreError`, `monthly`/`monthlyLoading`, `prof`/`profLoading`/`profError`.

- [ ] **Step 2: Substituir as mutações**

`patchSale` e `createExpense` viram `action`:

```ts
  const saveSale = action(
    (id: string, body: Record<string, unknown>) =>
      api<Sale>(`/accounting/sales/${id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao salvar venda." },
  );

  async function patchSale(s: Sale, body: Partial<Sale>) {
    const updated = await saveSale.run(s.id, body);
    if (updated) await sales.reload();
  }
```

O `reload` fica **por enquanto** — a Spec 2 é que o remove em favor da atualização otimista. Não antecipar aqui: esta tarefa é refactor sem mudança de comportamento.

- [ ] **Step 3: Conferir que nenhum `catch (err)` sobrou**

```bash
grep -c "catch (err)" frontend/src/routes/accounting/+page.svelte
```

Expected: `0`.

- [ ] **Step 4: Verificar tipos, build e tela**

```bash
cd frontend && npm run check && npm run build
```

Abrir `/accounting` e exercitar as quatro sub-abas: carregar, dar erro (parar a API e clicar Atualizar), marcar uma venda, criar uma despesa. Comportamento idêntico ao anterior, incluindo as mensagens de erro.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/accounting/+page.svelte
git commit -m "refactor(contábil): cargas e mutações via resource()/action()

Zero blocos try/catch na página. Comportamento idêntico — a remoção do
reload após PATCH fica para a Spec 2.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Adotar `resource`/`action` em Orçamentos

**Files:**
- Modify: `frontend/src/routes/quotes/+page.svelte`
- Modify: `frontend/src/routes/quotes/[id]/+page.svelte`

**Interfaces:**
- Consumes: `resource`, `action` de `$lib/resource`.
- Produces: nada.

- [ ] **Step 1: Converter `quotes/+page.svelte`**

`load`, `loadClients`, `loadPeople` viram `resource`; `togglePerson` vira `action`. O padrão é o da Task 4.

Atenção: `load()` depende dos filtros (`fStatus`, `fKind`, `fClient`). Manter a URL reativa como na Task 4:

```ts
  $: quotesUrl = (() => {
    const qs = new URLSearchParams();
    if (fStatus) qs.set("status", fStatus);
    if (fKind) qs.set("kind", fKind);
    if (fClient) qs.set("client_id", fClient);
    return `/quotes${qs.toString() ? `?${qs}` : ""}`;
  })();
  const rows = resource(() => api<Quote[]>(quotesUrl), {
    initial: [], errorMessage: "Falha ao carregar orçamentos.", auto: false,
  });
```

Os `on:change={load}` dos selects viram `on:change={() => rows.reload()}`.

- [ ] **Step 2: Converter `quotes/[id]/+page.svelte`**

Arquivo grande (1.879 linhas) com muitas mutações (itens, serviços, fotos, transições, LLM). Converter **uma função por vez**, rodando `npm run check` entre elas, para não perder o rastro num arquivo desse tamanho.

Ordem sugerida: cargas primeiro (`loadQuote`, `loadMaterials`, `loadServices`, `loadPeople`), depois mutações de item, depois serviços, depois fotos, depois transições, depois LLM.

- [ ] **Step 3: Conferir que nenhum `catch (err)` sobrou**

```bash
grep -c "catch (err)" frontend/src/routes/quotes/+page.svelte "frontend/src/routes/quotes/[id]/+page.svelte"
```

Expected: `0` nos dois.

- [ ] **Step 4: Verificar tipos, build e o fluxo inteiro**

```bash
cd frontend && npm run check && npm run build
make e2e
```

Expected: `check` e `build` limpos, e2e verde. Além do e2e, exercitar manualmente: criar rascunho, adicionar peça com gcode, resolver material, finalizar, aprovar, produzir, concluir, gerar PDF.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/quotes/
git commit -m "refactor(orçamentos): cargas e mutações via resource()/action()

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Estilos compartilhados → `app.css`

**Files:**
- Modify: `frontend/src/app.css`
- Modify: todas as `frontend/src/routes/*/+page.svelte` que declaram as classes listadas

**Interfaces:**
- Consumes: nada.
- Produces: classes globais que a Spec 1 usa para a passada responsiva num arquivo só.

- [ ] **Step 1: Inventariar as declarações concorrentes**

Para cada classe da lista — `.panel`, `.panel-head`, `.section-title`, `.table-wrap`, `.tag`, `.badge`, `.empty`, `.alert`, `.hint`, `.subtab`, `.chip`, `.field`, `.toggle`, `.count` — extrair todas as versões:

```bash
cd /Users/orochage/Codes/3d_analytics
for c in panel panel-head section-title table-wrap tag badge empty alert hint subtab chip field toggle count; do
  echo "=== .$c"
  grep -rn "^\s*\.$c\s*{" frontend/src/routes/*/+page.svelte frontend/src/routes/*/*/+page.svelte frontend/src/app.css 2>/dev/null
done
```

Anotar num scratch, por classe, quais arquivos divergem e em quê.

- [ ] **Step 2: Escolher a versão canônica e subir para `app.css`**

Para cada classe, escolher a declaração mais completa (normalmente a de `app.css`, se já existir, ou a de `accounting`, que é a mais elaborada) e consolidá-la em `app.css`. Não remover nada das páginas ainda.

- [ ] **Step 3: Remover as locais, uma página por vez**

Ordem: `accounting` (436 linhas de style), `trends` (361), `insights` (356), `projects` (219), `inbox` (117), `library` (106), `quotes` (100), depois as menores.

Para cada página: remover as declarações que agora são globais, rodar `npm run build`, abrir a tela e comparar com um screenshot tirado antes. Página que divergir de propósito mantém o override local **com comentário dizendo por quê**:

```css
  /* Override local: no contábil o painel de lista encosta no sub-tab,
     sem a margem superior padrão. */
  .list-panel { margin-top: 0; }
```

- [ ] **Step 4: Medir o resultado**

```bash
for f in frontend/src/routes/*/+page.svelte; do
  n=$(awk '/^<style>/,/^<\/style>/' "$f" | wc -l); echo "$n $(basename $(dirname $f))";
done | sort -rn | awk '{s+=$1} END {print "total:", s}'
```

Expected: total sensivelmente abaixo de 2.024 (a Spec 0 estima ~40% de corte). O número exato não é critério de aceite; a ausência de regressão visual é.

- [ ] **Step 5: Commit**

Um commit por lote de páginas, não um commit gigante:

```bash
git add frontend/src/app.css frontend/src/routes/accounting/+page.svelte
git commit -m "refactor(css): sobe classes compartilhadas do contábil para app.css

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: `quotes.py` → pacote

Movimentação mecânica. **Nenhuma linha de lógica muda.**

**Files:**
- Delete: `backend/api/routes/quotes.py`
- Create: `backend/api/routes/quotes/__init__.py`
- Create: `backend/api/routes/quotes/_shared.py`
- Create: `backend/api/routes/quotes/crud.py`
- Create: `backend/api/routes/quotes/items.py`
- Create: `backend/api/routes/quotes/services.py`
- Create: `backend/api/routes/quotes/transitions.py`
- Create: `backend/api/routes/quotes/photos.py`
- Create: `backend/api/routes/quotes/pdf.py`
- Create: `backend/api/routes/quotes/people.py`

**Interfaces:**
- Consumes: nada.
- Produces: `backend.api.routes.quotes.router` — mesmo nome e mesmo caminho de import que `backend/app.py` já usa. `apply_production` continua importável de `backend.api.routes.quotes` (o `__init__.py` reexporta) porque `backend/api/routes/printer.py` a usa.

- [ ] **Step 1: Mapear quem importa o módulo hoje**

```bash
cd /Users/orochage/Codes/3d_analytics
grep -rn "routes.quotes\|routes import quotes\|from backend.api.routes.quotes" backend/ --include=*.py
```

Anotar cada símbolo importado de fora. O `__init__.py` precisa reexportar todos.

- [ ] **Step 2: Criar o pacote movendo código sem editar**

Criar o diretório e recortar os blocos do arquivo original para os módulos, na divisão da spec §6. Cada módulo declara seu próprio `router = APIRouter()` e registra suas rotas com os mesmos decoradores e caminhos.

`_shared.py` recebe: `_now`, `_get_settings_row`, `_quote_out`, `_photo_out`, `_assert_materials_resolved`, `_cycle_context_and_grams` e os imports comuns.

- [ ] **Step 3: Montar o `__init__.py` preservando a ordem das rotas**

```python
"""Rotas de orçamento.

Dividido em módulos por responsabilidade. A ORDEM de inclusão abaixo
importa: o FastAPI resolve rotas na ordem de registro, e `photos.py`
declara `/photos/{photo_id}/raw`, que é literal e precisa vir antes de
qualquer paramétrica `/{quote_id}` de `crud.py`.
"""
from fastapi import APIRouter

from backend.api.routes.quotes import crud, items, pdf, people, photos, services, transitions
from backend.api.routes.quotes._shared import _quote_out  # noqa: F401  (usado por testes)
from backend.api.routes.quotes.transitions import apply_production  # noqa: F401  (usado por printer.py)

router = APIRouter()
router.include_router(photos.router)      # literais primeiro
router.include_router(crud.router)
router.include_router(items.router)
router.include_router(services.router)
router.include_router(transitions.router)
router.include_router(people.router)
router.include_router(pdf.router)

__all__ = ["router", "apply_production", "_quote_out"]
```

- [ ] **Step 4: Rodar a suíte e comparar com a linha de base**

```bash
make test 2>&1 | tail -5
make lint
```

Expected: **mesma contagem** da Task 0, tudo verde. Um teste a menos ou a mais significa que o move perdeu ou duplicou uma rota.

- [ ] **Step 5: Conferir que a tabela de rotas é idêntica**

```bash
docker compose run --rm api python -c "
from backend.app import app
for r in app.routes:
    if hasattr(r, 'methods'):
        print(sorted(r.methods), r.path)
" | sort > /tmp/rotas_depois.txt
```

Comparar com a mesma saída obtida **antes** do move (gerar na Task 0 se ainda não existir, usando `git stash`). Diferença de ordem em rotas que não colidem é aceitável; diferença de caminho ou método, não.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/quotes.py backend/api/routes/quotes/
git commit -m "refactor(api): quotes.py (1171 linhas) vira pacote por responsabilidade

Movimentação mecânica, zero mudança de lógica. Resolve o MI grau C.
Ordem de include preserva a precedência de rotas literais sobre paramétricas.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Tabela declarativa de transições

**Files:**
- Modify: `backend/api/routes/quotes/transitions.py`

**Interfaces:**
- Consumes: o pacote da Task 7.
- Produces: `TRANSITIONS: dict[str, T]` e o handler genérico. `apply_production` permanece com a assinatura atual: `async def apply_production(session, q, assignments) -> None`.

- [ ] **Step 1: Rodar só os testes de ciclo de vida e guardar a saída**

```bash
docker compose run --rm api pytest -v \
  backend/tests/api/test_quotes_lifecycle.py \
  backend/tests/api/test_quotes_personal.py \
  backend/tests/api/test_production_flow.py 2>&1 | tail -30
```

Expected: verde. Esta é a rede de segurança da tarefa — anotar a contagem.

- [ ] **Step 2: Escrever a tabela e o handler**

Em `transitions.py`, acima dos endpoints:

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class T:
    """Uma transição de status declarada.

    `from_`  estados de origem aceitos
    `to`     estado destino
    `stamp`  atributo de timestamp carimbado com _now(), se houver
    `kinds`  tipos de orçamento que aceitam a transição (None = todos)
    `guard`  validação extra; recebe (session, quote) e levanta HTTPException
    `on_apply` efeito colateral; recebe (session, quote, payload)
    """
    from_: frozenset[QuoteStatus]
    to: QuoteStatus
    stamp: str | None = None
    kinds: frozenset[QuoteKind] | None = None
    guard: Callable[..., Awaitable[None]] | None = None
    on_apply: Callable[..., Awaitable[None]] | None = None


async def _apply_transition(session, q: Quote, name: str, payload=None) -> None:
    t = TRANSITIONS[name]
    if t.kinds is not None and q.kind not in t.kinds:
        raise HTTPException(409, f"transição '{name}' não se aplica a orçamento {q.kind}")
    if q.status not in t.from_:
        esperados = ", ".join(sorted(s.value for s in t.from_))
        raise HTTPException(409, f"quote must be {esperados} to {name}")
    if t.guard:
        await t.guard(session, q)
    if t.on_apply:
        await t.on_apply(session, q, payload)
    q.status = t.to
    if t.stamp:
        setattr(q, t.stamp, _now())
```

**Atenção às mensagens de erro:** os testes existentes afirmam textos específicos (ex.: `"quote must be em_producao to complete"`). Antes de escrever a tabela, extrair os textos atuais:

```bash
grep -rn 'HTTPException(409' backend/api/routes/quotes/transitions.py
grep -rn 'must be\|não se aplica' backend/tests/api/test_quotes_*.py backend/tests/api/test_production_flow.py
```

A mensagem gerada pelo handler tem que reproduzir o texto que os testes esperam. Onde não der para reproduzir genericamente, a transição recebe um campo `message: str | None` e usa o texto literal.

- [ ] **Step 3: Preencher a tabela**

```python
TRANSITIONS: dict[str, T] = {
    "finalize": T(from_=frozenset({QuoteStatus.DRAFT}), to=QuoteStatus.ORCADO,
                  stamp="finalized_at"),
    "reopen":   T(from_=frozenset({QuoteStatus.ORCADO}), to=QuoteStatus.DRAFT),
    "approve":  T(from_=frozenset({QuoteStatus.ORCADO}), to=QuoteStatus.APROVADO,
                  stamp="approved_at", kinds=frozenset({QuoteKind.COMMERCIAL}),
                  guard=_assert_materials_resolved),
    "complete": T(from_=frozenset({QuoteStatus.EM_PRODUCAO}), to=QuoteStatus.PRODUZIDO,
                  stamp="produced_at", on_apply=_record_success),
    "fail":     T(from_=frozenset({QuoteStatus.EM_PRODUCAO}), to=QuoteStatus.FALHOU,
                  on_apply=_record_failure),
    "deliver":  T(from_=frozenset({QuoteStatus.PRODUZIDO}), to=QuoteStatus.ENTREGUE,
                  stamp="delivered_at"),
    "cancel":   T(from_=_CANCELAVEIS, to=QuoteStatus.CANCELADO, stamp="cancelled_at"),
}
```

`_CANCELAVEIS` deve reproduzir exatamente a condição do `t_cancel` atual — lê-la no código antes de escrever, não deduzir.

`produce` **não entra na tabela** (spec §6): payload próprio, regra de origem por tipo e baixa de spool. Continua explícito abaixo da tabela.

- [ ] **Step 4: Reescrever os endpoints como chamadas ao handler**

Cada endpoint vira três linhas, preservando path, response_model e status code:

```python
@router.post("/{quote_id}/transitions/finalize", response_model=QuoteOut)
async def t_finalize(quote_id: UUID, _: User = Depends(require_user),
                     session: AsyncSession = Depends(db_session)):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    await _apply_transition(session, q, "finalize")
    await session.commit()
    return await _quote_out(session, q)
```

`t_complete` e `t_fail` passam o payload adiante (`payload` é consumido por `_record_success`/`_record_failure`).

- [ ] **Step 5: Rodar os testes de ciclo de vida**

```bash
docker compose run --rm api pytest -v \
  backend/tests/api/test_quotes_lifecycle.py \
  backend/tests/api/test_quotes_personal.py \
  backend/tests/api/test_production_flow.py 2>&1 | tail -30
```

Expected: mesma contagem e mesmo verde do Step 1. Teste que falha por mensagem de erro diferente é bug do refactor — ajustar o handler, **nunca o teste**.

- [ ] **Step 6: Rodar a suíte inteira**

```bash
make test 2>&1 | tail -5
make lint
```

Expected: mesma contagem da Task 0.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routes/quotes/transitions.py
git commit -m "refactor(quotes): 8 transições viram tabela declarativa

O fluxo de status inteiro passa a caber numa tela. produce fica de fora
(payload próprio, regra por tipo, baixa de spool). Mensagens de erro
preservadas ao pé da letra.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Adotar os helpers nas demais páginas

**Files:**
- Modify: `frontend/src/routes/{inbox,capacity,clients,materials,services,spools,library,settings,config,insights,trends,projects}/+page.svelte`

**Interfaces:**
- Consumes: `$lib/format`, `$lib/resource`.
- Produces: nada.

- [ ] **Step 1: Converter em ordem de densidade**

Ordem por número de `handleApiError`: `inbox` (10), `trends` (9), `settings` (9), `insights` (9), `materials` (6), `spools` (5), `services` (5), `library` (5), `config` (5), `clients` (5), `capacity` (4), `change-password` (2).

Para cada página, o mesmo padrão das Tasks 3–5: formatadores locais viram import de `$lib/format` (conferindo divergências antes), cargas viram `resource`, mutações viram `action`.

**Uma página por commit.** Rodar `npm run check && npm run build` e abrir a tela antes de cada commit.

- [ ] **Step 2: Conferir o resultado global**

```bash
cd /Users/orochage/Codes/3d_analytics
grep -rc "catch (err)" frontend/src/routes/*/+page.svelte frontend/src/routes/*/*/+page.svelte 2>/dev/null \
  | grep -v ":0" || echo "nenhum try/catch restante"
```

Expected: nenhum, ou apenas os justificados (por exemplo, `logout` no layout, que engole erro de propósito).

- [ ] **Step 3: Verificação final**

```bash
make test 2>&1 | tail -5
make lint
cd frontend && npm test && npm run check && npm run build
cd .. && make e2e
```

Expected: tudo verde, contagem de pytest igual à da Task 0.

- [ ] **Step 4: Commit final**

```bash
git commit -m "refactor(frontend): últimas páginas adotam format/resource

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Critério de pronto da Spec 0

- [ ] `make test` verde com a **mesma contagem** da Task 0.
- [ ] `make lint` verde.
- [ ] `make e2e` verde.
- [ ] `cd frontend && npm test` verde (31+ testes).
- [ ] `radon mi backend` não reporta grau C em `quotes/`.
- [ ] Zero `catch (err)` em `accounting/` e `quotes/`.
- [ ] Nenhuma migração criada, nenhum endpoint novo, nenhuma mudança visível.
