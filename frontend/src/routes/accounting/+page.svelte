<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import { money, date as fmtDate } from "$lib/format";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type {
    Sale,
    Expense,
    Dre,
    ExpenseCategory,
    MonthlyDre,
    Profitability,
  } from "$lib/types";

  let tab: "vendas" | "despesas" | "dre" | "lucratividade" = "vendas";
  let dreMode: "periodo" | "mensal" = "periodo";

  let showStale = false;
  $: salesUrl = `/accounting/sales${showStale ? "" : "?is_stale=false"}`;
  const sales = resource(() => api<Sale[]>(salesUrl), {
    initial: [],
    errorMessage: "Falha ao carregar vendas.",
    auto: false,
  });
  const saveSale = action(
    (id: string, body: Record<string, unknown>) =>
      api<Sale>(`/accounting/sales/${id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao salvar venda." },
  );

  let exCategory: ExpenseCategory = "maintenance";
  let exDescription = "";
  let exAmount = "";
  let exRecurring = false;
  let exDate = new Date().toISOString().slice(0, 10);

  const expenses = resource(() => api<Expense[]>("/accounting/expenses"), {
    initial: [],
    errorMessage: "Falha ao carregar despesas.",
    auto: false,
  });
  const createExpenseAction = action(
    (body: Record<string, unknown>) =>
      api<Expense>("/accounting/expenses", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao criar despesa." },
  );
  const removeExpenseAction = action(
    (id: string) => api(`/accounting/expenses/${id}`, { method: "DELETE" }),
    { errorMessage: "Falha ao remover." },
  );
  // Erro exibido no painel de despesas: qualquer uma das três operações pode tê-lo produzido.
  $: expError = $expenses.error || $createExpenseAction.error || $removeExpenseAction.error;

  let from = new Date().toISOString().slice(0, 8) + "01";
  let to = new Date().toISOString().slice(0, 10);

  const dre = resource(() => api<Dre>(`/accounting/dre?from=${from}&to=${to}`), {
    errorMessage: "Falha ao gerar o DRE.",
    auto: false,
  });
  const monthly = resource(
    () => api<MonthlyDre[]>(`/accounting/dre/monthly?from=${from}&to=${to}`),
    { initial: [], errorMessage: "Falha ao gerar o DRE mensal.", auto: false },
  );
  $: monthlyRows = $monthly.data ?? [];
  // A limpeza de fato é feita por reloadDre()/reloadMonthly() (cada um chama
  // reset() no resource() irmão antes de recarregar o seu) — isso já garante
  // que só um dos dois pode ter erro "fresco" por vez. A seleção por modo
  // aqui é só uma escolha de exibição por cima disso: evita mostrar, por um
  // instante, o erro do modo que você acabou de sair enquanto o do modo atual
  // ainda não voltou (loading) — não é o mecanismo que apaga o erro velho.
  $: dreError = dreMode === "mensal" ? $monthly.error : $dre.error;

  const prof = resource(() => api<Profitability>(`/accounting/profitability?from=${from}&to=${to}`), {
    errorMessage: "Falha ao gerar a lucratividade.",
    auto: false,
  });

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

  const MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  function monthLabel(m: string): string {
    const [y, mm] = m.split("-");
    const idx = Number(mm) - 1;
    return `${MONTHS_PT[idx] ?? mm}/${(y ?? "").slice(2)}`;
  }

  // Recarregar a lista é o "caminho de recarga" que também precisa limpar o
  // erro de uma mutação irmã: sales.reload()/expenses.reload() só zeram o
  // próprio erro do resource — não sabem (nem devem saber, ver resource.ts)
  // que existe uma action() cujo erro está combinado no mesmo alerta. Sem
  // isso, um PATCH/POST/DELETE que falhou deixa a mensagem presa na tela
  // mesmo depois de um "Atualizar" bem-sucedido.
  function reloadSales() {
    saveSale.reset();
    return sales.reload();
  }
  function reloadExpenses() {
    createExpenseAction.reset();
    removeExpenseAction.reset();
    return expenses.reload();
  }
  // Mesmo raciocínio para o DRE: dre e monthly são dois resource() (não um
  // resource()+action()), mas o problema é idêntico — um reload() bem-sucedido
  // num modo não apaga o erro velho que ficou no outro. reset() cobre também o
  // caso em que o modo com erro tem dados de uma carga anterior (monthlyRows
  // não fica vazio só porque o reload mais recente falhou), que a guarda de
  // "só recarrega se list vazia" do setDreMode/openTab não pega sozinha.
  function reloadDre() {
    monthly.reset();
    return dre.reload();
  }
  function reloadMonthly() {
    dre.reset();
    return monthly.reload();
  }

  async function patchSale(s: Sale, body: Partial<Sale>) {
    const updated = await saveSale.run(s.id, body);
    if (updated) await sales.reload();
  }
  async function createExpense() {
    const created = await createExpenseAction.run({
      category: exCategory,
      description: exDescription,
      amount: exAmount,
      is_recurring: exRecurring,
      incurred_at: exDate,
    });
    if (created) {
      exDescription = "";
      exAmount = "";
      exRecurring = false;
      await reloadExpenses();
    }
  }
  async function removeExpense(id: string) {
    if (!confirm("Remover esta despesa?")) return;
    // run() volta undefined tanto no erro quanto no sucesso sem corpo (DELETE não devolve
    // conteúdo) — os dois casos só se distinguem olhando o .error da action.
    await removeExpenseAction.run(id);
    if (!$removeExpenseAction.error) await reloadExpenses();
  }
  function exportXlsx() {
    window.open(`/api/accounting/dre/export.xlsx?from=${from}&to=${to}`, "_blank");
  }

  function generateDre() {
    if (dreMode === "mensal") reloadMonthly();
    else reloadDre();
  }
  // dre.reset()/monthly.reset() aqui, antes da guarda de "só recarrega se
  // vazio" decidir: essa guarda (pré-existente) olha monthlyRows.length, e
  // monthlyRows NÃO fica vazio só porque o reload mais recente falhou — um
  // reload que falha preserva os dados antigos, só marca error. Sem isto, sair
  // do modo "mensal" e voltar sem passar por reloadMonthly() (porque a lista
  // já tinha dados de antes) reexibe um erro velho de uma tentativa que nunca
  // mais rodou. Resetar os dois é sempre seguro: no ramo em que a guarda
  // decide recarregar, reloadMonthly()/reloadDre() já fazem o próprio
  // reset+reload de novo (redundante, inofensivo); no ramo em que a guarda
  // decide NÃO recarregar (dados em cache), zerar o erro é exatamente o
  // conserto — estamos escolhendo mostrar dados de uma carga que deu certo,
  // não faz sentido um erro de outra tentativa continuar por cima.
  function setDreMode(m: typeof dreMode) {
    dreMode = m;
    dre.reset();
    monthly.reset();
    if (m === "mensal" && monthlyRows.length === 0) reloadMonthly();
    else if (m === "periodo" && !$dre.data) reloadDre();
  }

  function openTab(t: typeof tab) {
    tab = t;
    if (t === "dre") {
      dre.reset();
      monthly.reset();
      if (dreMode === "mensal" && monthlyRows.length === 0) reloadMonthly();
      else if (dreMode === "periodo" && !$dre.data) reloadDre();
    }
    if (t === "lucratividade" && !$prof.data) prof.reload();
  }

  type DreAmountKey =
    | "receita_bruta"
    | "impostos"
    | "receita_liquida"
    | "cpv"
    | "custos_variaveis"
    | "lucro_bruto"
    | "custo_estoque"
    | "perda_operacional"
    | "resultado_liquido";
  function sumMonthly(key: DreAmountKey): number {
    return monthlyRows.reduce((acc, m) => acc + Number(m[key] || 0), 0);
  }
  function sumMonthlyCat(cat: string): number {
    return monthlyRows.reduce((acc, m) => acc + Number(m.despesas[cat] || 0), 0);
  }
  $: monthlyCats = Array.from(
    new Set(monthlyRows.flatMap((m) => Object.keys(m.despesas))),
  ).sort();
  $: totalReceitaLiquida = sumMonthly("receita_liquida");
  $: totalResultado = sumMonthly("resultado_liquido");
  $: totalMargemPct =
    totalReceitaLiquida !== 0 ? (totalResultado / totalReceitaLiquida) * 100 : 0;

  $: confirmedCount = ($sales.data ?? []).filter((s) => s.is_sold).length;
  $: expenseTotal = ($expenses.data ?? []).reduce((acc, e) => acc + Number(e.amount || 0), 0);
  $: dreNegative = $dre.data ? Number($dre.data.resultado_liquido) < 0 : false;

  onMount(() => {
    if (requireAuth()) return;
    reloadSales();
    reloadExpenses();
    reloadDre();
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
    <span class="badge mono">{confirmedCount}/{($sales.data ?? []).length}</span>
  </button>
  <button type="button" class="subtab" class:active={tab === "despesas"} on:click={() => openTab("despesas")}>
    <span class="idx">02</span> Despesas
    <span class="badge mono">{($expenses.data ?? []).length}</span>
  </button>
  <button type="button" class="subtab" class:active={tab === "dre"} on:click={() => openTab("dre")}>
    <span class="idx">03</span> DRE
  </button>
  <button
    type="button"
    class="subtab"
    class:active={tab === "lucratividade"}
    on:click={() => openTab("lucratividade")}
  >
    <span class="idx">04</span> Lucratividade
  </button>
</nav>

{#if tab === "vendas"}
  <section class="panel list-panel">
    <div class="panel-head">
      <h2 class="section-title">
        Vendas <span class="count">· {($sales.data ?? []).length}</span>
      </h2>
      <div class="head-tools">
        <label class="toggle mono">
          <input type="checkbox" bind:checked={showStale} on:change={reloadSales} />
          mostrar arquivadas
        </label>
        <button class="tiny ghost" on:click={reloadSales} disabled={$sales.loading}>
          {$sales.loading ? "Carregando…" : "Atualizar"}
        </button>
      </div>
    </div>
    {#if $sales.error || $saveSale.error}<div class="alert">{$sales.error || $saveSale.error}</div>{/if}
    <Table
      columns={[
        { key: "quote_id", label: "Orçamento", mono: true, format: (v) => String(v).slice(0, 8) },
        { key: "client_name", label: "Cliente" },
        { key: "quote_kind", label: "Tipo", format: (v) => fmtKind(v as string) },
        { key: "itens_label", label: "Itens" },
        { key: "quote_status", label: "Estado" },
        { key: "quote_total", label: "Total", mono: true, align: "right", format: (v) => money(v as string) },
        { key: "cpv_calc", label: "CPV", mono: true, align: "right", format: (v) => money(v as string) },
        {
          key: "sold_at",
          label: "Vendido em",
          mono: true,
          align: "center",
          format: (v) => fmtDate(v as string | null),
        },
      ]}
      rows={$sales.data ?? []}
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
    submitting={$createExpenseAction.pending}
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
        Despesas <span class="count">· {($expenses.data ?? []).length}</span>
        {#if ($expenses.data ?? []).length > 0}<span class="head-sum mono">total {money(expenseTotal)}</span>{/if}
      </h2>
      <button class="tiny ghost" on:click={reloadExpenses} disabled={$expenses.loading}>
        {$expenses.loading ? "Carregando…" : "Atualizar"}
      </button>
    </div>
    {#if expError}<div class="alert">{expError}</div>{/if}
    <Table
      columns={[
        {
          key: "incurred_at",
          label: "Data",
          mono: true,
          format: (v) => fmtDate(v as string),
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
      rows={$expenses.data ?? []}
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
      <div class="head-tools">
        <div class="segmented mono" role="group" aria-label="Modo do DRE">
          <button
            type="button"
            class:active={dreMode === "periodo"}
            on:click={() => setDreMode("periodo")}>Período</button
          >
          <button
            type="button"
            class:active={dreMode === "mensal"}
            on:click={() => setDreMode("mensal")}>Mensal</button
          >
        </div>
        <button class="tiny ghost" on:click={exportXlsx}>Exportar XLSX</button>
      </div>
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
      <button class="generate" on:click={generateDre} disabled={$dre.loading || $monthly.loading}>
        {$dre.loading || $monthly.loading ? "Calculando…" : "Gerar"}
      </button>
    </div>
    {#if dreError}<div class="alert">{dreError}</div>{/if}
  </section>

  {#if dreMode === "mensal"}
    {#if $monthly.loading && monthlyRows.length === 0}
      <div class="state mono">Calculando demonstrativo mensal…</div>
    {:else if monthlyRows.length > 0}
      <section class="ledger panel" aria-label="DRE mensal">
        <div class="ledger-mast">
          <span class="ledger-eyebrow mono">DRE mensal</span>
          <span class="ledger-range mono">{fmtDate(from)} — {fmtDate(to)}</span>
        </div>
        <div class="grid-wrap">
          <table class="dre-grid">
            <thead>
              <tr>
                <th class="acct">Conta</th>
                {#each monthlyRows as m}<th class="num">{monthLabel(m.month)}</th>{/each}
                <th class="num total">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="acct">Receita bruta</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.receita_bruta)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("receita_bruta"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct"><span class="op">(−)</span> Impostos</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.impostos)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("impostos"))}</td>
              </tr>
              <tr class="sub">
                <td class="acct"><span class="op">=</span> Receita líquida</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.receita_liquida)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("receita_liquida"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct"><span class="op">(−)</span> CPV</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.cpv)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("cpv"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct"><span class="op">(−)</span> Custos variáveis</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.custos_variaveis)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("custos_variaveis"))}</td>
              </tr>
              <tr class="sub">
                <td class="acct"><span class="op">=</span> Lucro bruto</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.lucro_bruto)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("lucro_bruto"))}</td>
              </tr>
              {#each monthlyCats as cat}
                <tr class="muted">
                  <td class="acct expense"><span class="op">(−)</span> {catLabel(cat)}</td>
                  {#each monthlyRows as m}<td class="num mono">{money(m.despesas[cat] ?? 0)}</td>{/each}
                  <td class="num mono total">{money(sumMonthlyCat(cat))}</td>
                </tr>
              {/each}
              <tr class="muted">
                <td class="acct expense"><span class="op">(−)</span> Custo de estoque</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.custo_estoque)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("custo_estoque"))}</td>
              </tr>
              <tr class="muted">
                <td class="acct expense"><span class="op">(−)</span> Perda operacional (uso pessoal)</td>
                {#each monthlyRows as m}<td class="num mono">{money(m.perda_operacional)}</td>{/each}
                <td class="num mono total">{money(sumMonthly("perda_operacional"))}</td>
              </tr>
              <tr class="result">
                <td class="acct"><span class="op">=</span> Resultado líquido</td>
                {#each monthlyRows as m}
                  <td class="num mono" class:neg={Number(m.resultado_liquido) < 0}>
                    {money(m.resultado_liquido)}
                  </td>
                {/each}
                <td class="num mono total" class:neg={totalResultado < 0}>{money(totalResultado)}</td>
              </tr>
              <tr class="margin-row">
                <td class="acct">Margem %</td>
                {#each monthlyRows as m}<td class="num mono">{m.margem_liquida_pct}%</td>{/each}
                <td class="num mono total">{totalMargemPct.toFixed(1)}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    {:else}
      <div class="state mono">Selecione um período e gere o demonstrativo mensal.</div>
    {/if}
  {:else if $dre.loading && !$dre.data}
    <div class="state mono">Calculando demonstrativo…</div>
  {:else if $dre.data}
    {@const d = $dre.data}
    <section class="ledger panel" aria-label="Demonstrativo de resultado">
      <div class="ledger-mast">
        <span class="ledger-eyebrow mono">DRE</span>
        <span class="ledger-range mono">{fmtDate(from)} — {fmtDate(to)}</span>
      </div>

      <dl class="statement">
        <div class="line revenue">
          <dt>Receita bruta</dt>
          <dd class="mono">{money(d.receita_bruta)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> Impostos</dt>
          <dd class="mono">{money(d.impostos)}</dd>
        </div>
        <div class="line subtotal">
          <dt><span class="op">=</span> Receita líquida</dt>
          <dd class="mono">{money(d.receita_liquida)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> CPV</dt>
          <dd class="mono">{money(d.cpv)}</dd>
        </div>
        <div class="line deduction">
          <dt><span class="op">(−)</span> Custos variáveis</dt>
          <dd class="mono">{money(d.custos_variaveis)}</dd>
        </div>
        <div class="line subtotal">
          <dt><span class="op">=</span> Lucro bruto</dt>
          <dd class="mono">{money(d.lucro_bruto)}</dd>
        </div>

        <div class="group-head">
          <dt>Despesas operacionais</dt>
          <dd class="mono">{money(d.total_despesas)}</dd>
        </div>
        <div class="line expense">
          <dt><span class="op">(−)</span> Custo de estoque (não vendido)</dt>
          <dd class="mono">{money(d.custo_estoque)}</dd>
        </div>
        <div class="line expense">
          <dt><span class="op">(−)</span> Perda operacional (uso pessoal)</dt>
          <dd class="mono">{money(d.perda_operacional)}</dd>
        </div>
        {#each Object.entries(d.despesas) as [cat, val]}
          <div class="line expense">
            <dt><span class="op">(−)</span> {catLabel(cat)}</dt>
            <dd class="mono">{money(val)}</dd>
          </div>
        {/each}
        {#if Object.keys(d.despesas).length === 0}
          <div class="line expense empty-line">
            <dt>Sem despesas no período</dt>
            <dd class="mono">{money(0)}</dd>
          </div>
        {/if}

        <div class="line result" class:negative={dreNegative}>
          <dt><span class="op">=</span> Resultado líquido</dt>
          <dd class="mono">{money(d.resultado_liquido)}</dd>
        </div>
      </dl>

      <div class="margin-strip" class:negative={dreNegative}>
        <span class="margin-label mono">Margem líquida</span>
        <span class="margin-value mono">{d.margem_liquida_pct}%</span>
      </div>
    </section>
  {:else}
    <div class="state mono">Selecione um período e gere o demonstrativo.</div>
  {/if}
{/if}

{#if tab === "lucratividade"}
  <section class="panel dre-controls">
    <div class="panel-head">
      <h2 class="section-title">Lucratividade</h2>
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
      <button class="generate" on:click={prof.reload} disabled={$prof.loading}>
        {$prof.loading ? "Calculando…" : "Gerar"}
      </button>
    </div>
    {#if $prof.error}<div class="alert">{$prof.error}</div>{/if}
  </section>

  {#if $prof.loading && !$prof.data}
    <div class="state mono">Calculando lucratividade…</div>
  {:else if $prof.data}
    {@const p = $prof.data}
    {#each [{ title: "Por cliente", rows: p.by_client, empty: "Nenhum cliente no período" }, { title: "Por material", rows: p.by_material, empty: "Nenhum material no período" }] as block}
      <section class="panel list-panel">
        <div class="panel-head">
          <h2 class="section-title">
            {block.title} <span class="count">· {block.rows.length}</span>
          </h2>
        </div>
        <Table
          columns={[
            { key: "label", label: block.title.replace("Por ", "") },
            { key: "receita", label: "Receita", mono: true, align: "right", format: (v) => money(v as string) },
            { key: "custo", label: "Custo", mono: true, align: "right", format: (v) => money(v as string) },
            { key: "margem", label: "Margem", mono: true, align: "right", format: (v) => money(v as string) },
            { key: "margem_pct", label: "Margem %", mono: true, align: "right", format: (v) => `${v}%` },
          ]}
          rows={block.rows as unknown as Record<string, unknown>[]}
          empty={block.empty}
        />
      </section>
    {/each}
  {:else}
    <div class="state mono">Selecione um período e gere a lucratividade.</div>
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

  /* ---------- segmented control ---------- */
  .segmented {
    display: inline-flex;
    border: 1px solid var(--line-strong);
    background: var(--paper);
  }
  .segmented button {
    background: transparent;
    border: 0;
    border-right: 1px solid var(--line);
    color: var(--muted);
    padding: 0.4rem 0.8rem;
    font-size: 0.66rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 120ms ease, color 120ms ease;
  }
  .segmented button:last-child {
    border-right: 0;
  }
  .segmented button:hover {
    color: var(--ink);
  }
  .segmented button.active {
    background: var(--ink);
    color: var(--paper);
  }

  /* ---------- DRE monthly grid ---------- */
  .grid-wrap {
    overflow-x: auto;
  }
  .dre-grid {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.86rem;
  }
  .dre-grid th,
  .dre-grid td {
    padding: 0.5rem 0.85rem;
    border-bottom: 1px solid var(--line);
    white-space: nowrap;
  }
  .dre-grid thead th {
    font-family: var(--font-mono);
    font-weight: 500;
    font-size: 0.64rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--line-strong);
    background: var(--paper);
    position: sticky;
    top: 0;
  }
  .dre-grid .acct {
    text-align: left;
    color: var(--ink);
  }
  .dre-grid .acct.expense {
    padding-left: 1.6rem;
    color: var(--muted);
  }
  .dre-grid .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .dre-grid .total {
    border-left: 1px solid var(--line-strong);
    font-weight: 600;
  }
  .dre-grid .op {
    display: inline-block;
    width: 1.4rem;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.72rem;
  }
  .dre-grid tr.muted td {
    color: var(--muted);
  }
  .dre-grid tr.sub td {
    font-weight: 600;
    border-bottom: 1px solid var(--line-strong);
  }
  .dre-grid tr.sub td.acct {
    color: var(--ink);
  }
  .dre-grid tr.result td {
    border-top: 2px solid var(--ink);
    border-bottom: none;
    font-weight: 600;
    color: var(--ok);
  }
  .dre-grid tr.result td.acct {
    color: var(--ink);
    font-family: var(--font-display);
  }
  .dre-grid tr.result td.neg {
    color: var(--danger);
  }
  .dre-grid tr.margin-row td {
    border-bottom: none;
    color: var(--muted);
    font-size: 0.78rem;
  }
  .dre-grid tr.margin-row td.acct {
    letter-spacing: 0.08em;
    text-transform: uppercase;
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
