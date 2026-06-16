<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type { Sale, Expense, Dre, ExpenseCategory } from "$lib/types";

  let tab: "vendas" | "despesas" | "dre" = "vendas";

  let sales: Sale[] = [];
  let salesError = "";
  let salesLoading = false;
  let showStale = false;

  let expenses: Expense[] = [];
  let expError = "";
  let expLoading = false;
  let exCategory: ExpenseCategory = "maintenance";
  let exDescription = "";
  let exAmount = "";
  let exRecurring = false;
  let exDate = new Date().toISOString().slice(0, 10);
  let exSubmitting = false;

  let dre: Dre | null = null;
  let dreLoading = false;
  let dreError = "";
  let from = new Date().toISOString().slice(0, 8) + "01";
  let to = new Date().toISOString().slice(0, 10);

  const CATS: { value: ExpenseCategory; label: string }[] = [
    { value: "maintenance", label: "Manutenção" },
    { value: "parts", label: "Peças" },
    { value: "tools", label: "Ferramentas" },
    { value: "labor", label: "Mecânicos" },
    { value: "equipment", label: "Máquinas/Equipamentos" },
    { value: "other", label: "Outros" },
  ];
  const catLabel = (c: string) => CATS.find((x) => x.value === c)?.label ?? c;
  const fmtKind = (k: string) => (k === "personal" ? "Pessoal" : "Comercial");

  const BRL = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
  function money(v: string | number | null | undefined): string {
    const n = Number(v ?? 0);
    return Number.isFinite(n) ? BRL.format(n) : "—";
  }
  function shortDate(v: string | null): string {
    if (!v) return "—";
    return v.slice(0, 10).split("-").reverse().join("/");
  }

  async function loadSales() {
    salesError = "";
    salesLoading = true;
    try {
      sales = await api<Sale[]>(`/accounting/sales${showStale ? "" : "?is_stale=false"}`);
    } catch (err) {
      handleApiError(err);
      salesError = errorMessage(err, "Falha ao carregar vendas.");
    } finally {
      salesLoading = false;
    }
  }
  async function patchSale(s: Sale, body: Partial<Sale>) {
    salesError = "";
    try {
      await api<Sale>(`/accounting/sales/${s.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      await loadSales();
    } catch (err) {
      handleApiError(err);
      salesError = errorMessage(err, "Falha ao salvar venda.");
    }
  }
  async function loadExpenses() {
    expError = "";
    expLoading = true;
    try {
      expenses = await api<Expense[]>("/accounting/expenses");
    } catch (err) {
      handleApiError(err);
      expError = errorMessage(err, "Falha ao carregar despesas.");
    } finally {
      expLoading = false;
    }
  }
  async function createExpense() {
    expError = "";
    exSubmitting = true;
    try {
      await api<Expense>("/accounting/expenses", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          category: exCategory,
          description: exDescription,
          amount: exAmount,
          is_recurring: exRecurring,
          incurred_at: exDate,
        }),
      });
      exDescription = "";
      exAmount = "";
      exRecurring = false;
      await loadExpenses();
    } catch (err) {
      handleApiError(err);
      expError = errorMessage(err, "Falha ao criar despesa.");
    } finally {
      exSubmitting = false;
    }
  }
  async function removeExpense(id: string) {
    if (!confirm("Remover esta despesa?")) return;
    expError = "";
    try {
      await api(`/accounting/expenses/${id}`, { method: "DELETE" });
      await loadExpenses();
    } catch (err) {
      handleApiError(err);
      expError = errorMessage(err, "Falha ao remover.");
    }
  }
  async function loadDre() {
    dreError = "";
    dreLoading = true;
    try {
      dre = await api<Dre>(`/accounting/dre?from=${from}&to=${to}`);
    } catch (err) {
      handleApiError(err);
      dreError = errorMessage(err, "Falha ao gerar o DRE.");
    } finally {
      dreLoading = false;
    }
  }

  function openTab(t: typeof tab) {
    tab = t;
    if (t === "dre" && !dre) loadDre();
  }

  $: confirmedCount = sales.filter((s) => s.is_sold).length;
  $: expenseTotal = expenses.reduce((acc, e) => acc + Number(e.amount || 0), 0);
  $: dreNegative = dre ? Number(dre.resultado_liquido) < 0 : false;

  onMount(() => {
    if (requireAuth()) return;
    loadSales();
    loadExpenses();
    loadDre();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Financeiro / 05</span>
  <h1 class="page-title">Contábil<em>.</em></h1>
  <p class="page-lede">
    Vendas confirmadas viram receita; despesas avulsas entram no DRE. Confirme o que entregou, lance os
    gastos do mês e leia o resultado líquido fechado.
  </p>
</header>

<nav class="subtabs" aria-label="Seções da contabilidade">
  <button type="button" class="subtab" class:active={tab === "vendas"} on:click={() => openTab("vendas")}>
    <span class="idx">01</span> Vendas
    <span class="badge mono">{confirmedCount}/{sales.length}</span>
  </button>
  <button type="button" class="subtab" class:active={tab === "despesas"} on:click={() => openTab("despesas")}>
    <span class="idx">02</span> Despesas
    <span class="badge mono">{expenses.length}</span>
  </button>
  <button type="button" class="subtab" class:active={tab === "dre"} on:click={() => openTab("dre")}>
    <span class="idx">03</span> DRE
  </button>
</nav>

{#if tab === "vendas"}
  <section class="panel list-panel">
    <div class="panel-head">
      <h2 class="section-title">
        Vendas <span class="count">· {sales.length}</span>
      </h2>
      <div class="head-tools">
        <label class="toggle mono">
          <input type="checkbox" bind:checked={showStale} on:change={loadSales} />
          mostrar arquivadas
        </label>
        <button class="tiny ghost" on:click={loadSales} disabled={salesLoading}>
          {salesLoading ? "Carregando…" : "Atualizar"}
        </button>
      </div>
    </div>
    {#if salesError}<div class="alert">{salesError}</div>{/if}
    <Table
      columns={[
        { key: "quote_id", label: "Orçamento", mono: true, format: (v) => String(v).slice(0, 8) },
        { key: "quote_kind", label: "Tipo", format: (v) => fmtKind(v as string) },
        { key: "quote_status", label: "Estado" },
        { key: "quote_total", label: "Total", mono: true, align: "right", format: (v) => money(v as string) },
        { key: "cpv_calc", label: "CPV", mono: true, align: "right", format: (v) => money(v as string) },
        {
          key: "sold_at",
          label: "Vendido em",
          mono: true,
          align: "center",
          format: (v) => shortDate(v as string | null),
        },
      ]}
      rows={sales}
      empty="Nenhuma venda elegível ainda"
    >
      <svelte:fragment slot="actions" let:row>
        <div class="sale-actions" class:stale={(row as Sale).is_stale}>
          <label class="sold-toggle mono" title="Confirmar como vendido">
            <input
              type="checkbox"
              checked={(row as Sale).is_sold}
              on:change={(e) => patchSale(row as Sale, { is_sold: e.currentTarget.checked })}
            />
            Vendido
          </label>
          <input
            class="revenue mono"
            type="number"
            step="0.01"
            min="0"
            title="Receita confirmada"
            value={(row as Sale).confirmed_revenue ?? (row as Sale).quote_total}
            on:change={(e) => patchSale(row as Sale, { confirmed_revenue: e.currentTarget.value })}
          />
        </div>
      </svelte:fragment>
    </Table>
    <p class="hint mono">
      A receita confirmada substitui o total do orçamento no DRE. Bobinas e CPV vêm do cálculo original.
    </p>
  </section>
{/if}

{#if tab === "despesas"}
  <Form
    eyebrow="Novo lançamento"
    title="Registrar despesa"
    submitLabel="Lançar"
    submitting={exSubmitting}
    error={expError}
    allowSubmit={exDescription.trim().length > 0 && exAmount !== ""}
    on:submit={createExpense}
  >
    <label class="field">
      Categoria
      <select bind:value={exCategory}>
        {#each CATS as c}<option value={c.value}>{c.label}</option>{/each}
      </select>
    </label>
    <label class="field full">
      Descrição
      <input bind:value={exDescription} placeholder="Troca de bico, parafusos, lubrificante…" required />
    </label>
    <label class="field">
      Valor (R$)
      <input bind:value={exAmount} type="number" step="0.01" min="0" required />
    </label>
    <label class="field">
      Data
      <input type="date" bind:value={exDate} required />
    </label>
    <label class="field recurring-field">
      <span class="recurring-spacer">&nbsp;</span>
      <span class="recurring-check toggle mono">
        <input type="checkbox" bind:checked={exRecurring} />
        recorrente (mensal)
      </span>
    </label>
  </Form>

  <section class="panel list-panel">
    <div class="panel-head">
      <h2 class="section-title">
        Despesas <span class="count">· {expenses.length}</span>
        {#if expenses.length > 0}<span class="head-sum mono">total {money(expenseTotal)}</span>{/if}
      </h2>
      <button class="tiny ghost" on:click={loadExpenses} disabled={expLoading}>
        {expLoading ? "Carregando…" : "Atualizar"}
      </button>
    </div>
    {#if expError}<div class="alert">{expError}</div>{/if}
    <Table
      columns={[
        {
          key: "incurred_at",
          label: "Data",
          mono: true,
          format: (v) => shortDate(v as string),
        },
        { key: "category", label: "Categoria", format: (v) => catLabel(v as string) },
        { key: "description", label: "Descrição" },
        {
          key: "is_recurring",
          label: "Recorrência",
          align: "center",
          format: (v) => (v ? "mensal" : "—"),
        },
        { key: "amount", label: "Valor", mono: true, align: "right", format: (v) => money(v as string) },
      ]}
      rows={expenses}
      empty="Nenhuma despesa lançada"
    >
      <svelte:fragment slot="actions" let:row>
        <button class="tiny danger" on:click={() => removeExpense((row as Expense).id)}>Excluir</button>
      </svelte:fragment>
    </Table>
  </section>
{/if}

{#if tab === "dre"}
  <section class="panel dre-controls">
    <div class="panel-head">
      <h2 class="section-title">Demonstrativo de resultado</h2>
    </div>
    <div class="period">
      <label class="field">
        De
        <input type="date" bind:value={from} />
      </label>
      <label class="field">
        Até
        <input type="date" bind:value={to} />
      </label>
      <button class="generate" on:click={loadDre} disabled={dreLoading}>
        {dreLoading ? "Calculando…" : "Gerar"}
      </button>
    </div>
    {#if dreError}<div class="alert">{dreError}</div>{/if}
  </section>

  {#if dreLoading && !dre}
    <div class="state mono">Calculando demonstrativo…</div>
  {:else if dre}
    <section class="ledger panel" aria-label="Demonstrativo de resultado">
      <div class="ledger-mast">
        <span class="ledger-eyebrow mono">DRE</span>
        <span class="ledger-range mono">{shortDate(from)} — {shortDate(to)}</span>
      </div>

      <dl class="statement">
        <div class="line revenue">
          <dt>Receita bruta</dt>
          <dd class="mono">{money(dre.receita_bruta)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> Impostos</dt>
          <dd class="mono">{money(dre.impostos)}</dd>
        </div>
        <div class="line subtotal">
          <dt><span class="op">=</span> Receita líquida</dt>
          <dd class="mono">{money(dre.receita_liquida)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> CPV</dt>
          <dd class="mono">{money(dre.cpv)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> Custos variáveis</dt>
          <dd class="mono">{money(dre.custos_variaveis)}</dd>
        </div>
        <div class="line subtotal">
          <dt><span class="op">=</span> Lucro bruto</dt>
          <dd class="mono">{money(dre.lucro_bruto)}</dd>
        </div>

        <div class="group-head">
          <dt>Despesas operacionais</dt>
          <dd class="mono">{money(dre.total_despesas)}</dd>
        </div>
        <div class="line expense">
          <dt><span class="op">(−)</span> Custo de estoque (não vendido)</dt>
          <dd class="mono">{money(dre.custo_estoque)}</dd>
        </div>
        {#each Object.entries(dre.despesas) as [cat, val]}
          <div class="line expense">
            <dt><span class="op">(−)</span> {catLabel(cat)}</dt>
            <dd class="mono">{money(val)}</dd>
          </div>
        {/each}
        {#if Object.keys(dre.despesas).length === 0}
          <div class="line expense empty-line">
            <dt>Sem despesas no período</dt>
            <dd class="mono">{money(0)}</dd>
          </div>
        {/if}

        <div class="line result" class:negative={dreNegative}>
          <dt><span class="op">=</span> Resultado líquido</dt>
          <dd class="mono">{money(dre.resultado_liquido)}</dd>
        </div>
      </dl>

      <div class="margin-strip" class:negative={dreNegative}>
        <span class="margin-label mono">Margem líquida</span>
        <span class="margin-value mono">{dre.margem_liquida_pct}%</span>
      </div>
    </section>
  {:else}
    <div class="state mono">Selecione um período e gere o demonstrativo.</div>
  {/if}
{/if}

<style>
  .page-head {
    margin-bottom: 1.5rem;
  }
  .list-panel {
    margin-top: 1.5rem;
  }
  .field.full {
    grid-column: 1 / -1;
  }

  /* ---------- sub-tabs ---------- */
  .subtabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0;
    border: 1px solid var(--line-strong);
    background: var(--paper);
    margin-bottom: 1.5rem;
  }
  .subtab {
    flex: 1 1 0;
    min-width: 130px;
    background: transparent;
    color: var(--muted);
    border: 0;
    border-right: 1px solid var(--line);
    padding: 0.75rem 1rem;
    font-family: var(--font-display);
    font-size: 0.95rem;
    letter-spacing: 0.02em;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    justify-content: flex-start;
    transition: background 120ms ease, color 120ms ease;
  }
  .subtab:last-child {
    border-right: 0;
  }
  .subtab:hover {
    background: rgba(26, 26, 29, 0.04);
    color: var(--ink);
  }
  .subtab.active {
    background: var(--ink);
    color: var(--paper);
  }
  .subtab.active:hover {
    background: var(--ink);
  }
  .subtab .idx {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    opacity: 0.55;
  }
  .subtab .badge {
    margin-left: auto;
    font-size: 0.64rem;
    letter-spacing: 0.1em;
    padding: 0.1rem 0.4rem;
    border: 1px solid currentColor;
    opacity: 0.8;
  }

  /* ---------- vendas ---------- */
  .head-tools {
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    cursor: pointer;
  }
  .toggle input {
    width: auto;
    margin: 0;
  }
  .sale-actions {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    justify-content: flex-end;
  }
  .sale-actions.stale {
    opacity: 0.45;
  }
  .sold-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.64rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink);
    cursor: pointer;
    white-space: nowrap;
  }
  .sold-toggle input {
    width: auto;
    margin: 0;
  }
  .revenue {
    width: 110px;
    padding: 0.3rem 0.45rem;
    font-size: 0.82rem;
    text-align: right;
  }
  .hint {
    margin: 1rem 0 0;
    font-size: 0.68rem;
    color: var(--muted);
    letter-spacing: 0.04em;
  }
  .recurring-field .recurring-spacer {
    display: block;
    font-size: 0.66rem;
  }
  .recurring-check {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.55rem 0;
  }
  .recurring-check input {
    width: auto;
    margin: 0;
  }
  .head-sum {
    margin-left: 0.6rem;
    font-size: 0.64rem;
    color: var(--muted);
    letter-spacing: 0.08em;
    text-transform: none;
  }

  /* ---------- DRE controls ---------- */
  .dre-controls .period {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 0.85rem 1rem;
  }
  .dre-controls .field {
    flex: 0 0 auto;
    min-width: 150px;
  }
  .generate {
    height: fit-content;
  }

  .state {
    border: 1px dashed var(--line);
    background: var(--paper);
    padding: 2.5rem 1rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.74rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-top: 1.5rem;
  }

  /* ---------- DRE statement ---------- */
  .ledger {
    margin-top: 1.5rem;
    padding: 0;
    overflow: hidden;
  }
  .ledger-mast {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 1rem 1.4rem;
    border-bottom: 1px solid var(--line-strong);
    background: var(--ink);
    color: var(--paper);
  }
  .ledger-eyebrow {
    font-size: 0.72rem;
    letter-spacing: 0.32em;
    text-transform: uppercase;
  }
  .ledger-range {
    font-size: 0.68rem;
    letter-spacing: 0.12em;
    opacity: 0.7;
  }

  .statement {
    margin: 0;
    padding: 0.6rem 1.4rem;
  }
  .statement .line,
  .statement .group-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--line);
  }
  .statement dt {
    font-size: 0.92rem;
    color: var(--ink);
  }
  .statement dd {
    margin: 0;
    font-size: 0.92rem;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .statement .op {
    display: inline-block;
    width: 1.6rem;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.78rem;
  }

  .line.deduction dt,
  .line.expense dt {
    color: var(--muted);
  }
  .line.deduction dd,
  .line.expense dd {
    color: var(--muted);
  }
  .line.expense {
    padding-left: 1rem;
  }
  .empty-line dt {
    font-style: italic;
  }

  .group-head {
    margin-top: 0.4rem;
    border-bottom: 1px dashed var(--line-strong);
  }
  .group-head dt {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink);
  }
  .group-head dd {
    font-size: 0.82rem;
    color: var(--muted);
  }

  .line.subtotal {
    border-bottom: 1px solid var(--line-strong);
  }
  .line.subtotal dt,
  .line.subtotal dd {
    font-weight: 600;
  }

  .line.result {
    border-bottom: none;
    border-top: 2px solid var(--ink);
    margin-top: 0.3rem;
    padding-top: 0.8rem;
  }
  .line.result dt {
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 600;
  }
  .line.result dd {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--ok);
  }
  .line.result.negative dd {
    color: var(--danger);
  }

  .margin-strip {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 0.85rem 1.4rem;
    border-top: 1px solid var(--line);
    background: rgba(47, 111, 79, 0.06);
  }
  .margin-strip.negative {
    background: rgba(168, 32, 26, 0.06);
  }
  .margin-label {
    font-size: 0.66rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .margin-value {
    font-size: 1.05rem;
    font-weight: 500;
    color: var(--ok);
  }
  .margin-strip.negative .margin-value {
    color: var(--danger);
  }

  @media (max-width: 560px) {
    .subtab .badge {
      display: none;
    }
    .head-tools {
      flex-direction: column;
      align-items: flex-end;
      gap: 0.4rem;
    }
  }
</style>
