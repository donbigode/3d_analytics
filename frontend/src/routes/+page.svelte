<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import { user } from "$lib/stores/user";
  import type { DashboardOut, DigestOut } from "$lib/types";
  import Card from "$lib/components/Card.svelte";
  import Funnel from "$lib/components/Funnel.svelte";
  import Pie from "$lib/components/Pie.svelte";

  let data: DashboardOut | null = null;
  let loading = true;
  let pageError = "";

  let digest: DigestOut | null = null;
  let digestLoading = false;
  let digestError = "";
  let digestAutoEnabled = true;  // mirrors /config/providers.digest_auto_enabled

  async function loadDigest(force = false) {
    digestLoading = true;
    digestError = "";
    try {
      digest = await api<DigestOut>(`/llm/digest${force ? "?force=true" : ""}`);
    } catch (err) {
      handleApiError(err);
      digestError = errorMessage(err, "Falha ao gerar resumo.");
    } finally {
      digestLoading = false;
    }
  }

  async function loadDigestPreference() {
    try {
      const p = await api<{ digest_auto_enabled: boolean }>("/config/providers");
      digestAutoEnabled = p.digest_auto_enabled;
    } catch {
      // Falha silenciosa — assume ligado se /config/providers não responder.
      digestAutoEnabled = true;
    }
  }

  // filters
  type Period = "7d" | "30d" | "month" | "year" | "all";
  let period: Period = "30d";
  let kind: "" | "commercial" | "personal" = "";

  function periodRange(p: Period): { from?: string; to?: string } {
    const now = new Date();
    if (p === "all") return {};
    const to = now.toISOString();
    let from = new Date();
    if (p === "7d") from.setDate(now.getDate() - 7);
    else if (p === "30d") from.setDate(now.getDate() - 30);
    else if (p === "month") from = new Date(now.getFullYear(), now.getMonth(), 1);
    else if (p === "year") from = new Date(now.getFullYear(), 0, 1);
    return { from: from.toISOString(), to };
  }

  async function load() {
    loading = true;
    pageError = "";
    try {
      const { from, to } = periodRange(period);
      const qs = new URLSearchParams();
      if (from) qs.set("from", from);
      if (to) qs.set("to", to);
      if (kind) qs.set("kind", kind);
      data = await api<DashboardOut>(`/dashboard${qs.toString() ? `?${qs}` : ""}`);
    } catch (err) {
      handleApiError(err);
      pageError = errorMessage(err, "Falha ao carregar dashboard.");
    } finally {
      loading = false;
    }
  }

  function fmtMoney(v: number | string): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  function fmtNum(v: number | string, dec = 2): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    return n.toLocaleString("pt-BR", { maximumFractionDigits: dec });
  }
  function fmtPct(v: number | string): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    return `${n.toFixed(1)}%`;
  }
  function fmtDate(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleDateString("pt-BR");
    } catch {
      return s;
    }
  }
  function statusLabel(s: string): string {
    return (
      { draft: "rascunho", orcado: "orçado", aprovado: "aprovado", produzido: "produzido", entregue: "entregue", cancelado: "cancelado" } as Record<string, string>
    )[s] ?? s;
  }

  $: estadoBreakdown = data
    ? (Object.entries(data.cards.orcamentos_por_estado) as [string, number][])
        .filter(([, n]) => n > 0)
    : [];

  $: estadoTotal = estadoBreakdown.reduce((a, [, n]) => a + n, 0);

  $: despesaCategorias = data
    ? (Object.entries(data.charts.despesa_categorias)).map(([k, v]) => ({
        label:
          ({
            filamento: "Filamento",
            energia: "Energia",
            mao_obra: "Mão de obra",
            depreciacao: "Depreciação",
          } as Record<string, string>)[k] ?? k,
        value: Number(v) || 0,
      }))
    : [];

  $: funilStages = data
    ? [
        { label: "Orçado", value: data.charts.funil.orcado },
        { label: "Aprovado", value: data.charts.funil.aprovado },
        { label: "Produzido", value: data.charts.funil.produzido },
        { label: "Entregue", value: data.charts.funil.entregue },
      ]
    : [];

  $: revExpSeries = data?.charts?.receita_vs_despesa ?? [];
  $: orcadoVsReal = data?.charts?.orcado_vs_real ?? [];

  function revExpPath(values: number[], w = 320, h = 80): string {
    if (!values || values.length < 2) return "";
    const max = Math.max(1, ...values);
    const step = w / (values.length - 1);
    return values
      .map((v, i) => {
        const x = i * step;
        const y = h - (v / max) * h;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }

  $: revExpReceita = revExpSeries.map((p: any) => Number(p.receita) || 0);
  $: revExpDespesa = revExpSeries.map((p: any) => Number(p.despesa) || 0);

  onMount(async () => {
    if (requireAuth()) return;
    load();
    await loadDigestPreference();
    if (digestAutoEnabled) {
      loadDigest();
    }
  });
</script>

{#if !$user}
  <p>Faça login: <a href="/login">/login</a></p>
{:else}
  <header class="page-head">
    <span class="page-eyebrow">Visão geral / 00</span>
    <h1 class="page-title">Dashboard<em>.</em></h1>
    <p class="page-lede">
      Receita, despesa e operação no período. Use os filtros para ajustar o
      recorte. Indicadores reagem aos lançamentos de produção.
    </p>
  </header>

  <section class="panel filter-bar">
    <div class="form-grid filter-grid">
      <label class="field">
        Período
        <select bind:value={period} on:change={load}>
          <option value="7d">últimos 7 dias</option>
          <option value="30d">últimos 30 dias</option>
          <option value="month">mês corrente</option>
          <option value="year">ano corrente</option>
          <option value="all">tudo</option>
        </select>
      </label>
      <label class="field">
        Tipo
        <select bind:value={kind} on:change={load}>
          <option value="">comercial + pessoal</option>
          <option value="commercial">apenas comercial</option>
          <option value="personal">apenas pessoal</option>
        </select>
      </label>
      <div class="actions">
        <button type="button" class="ghost tiny" on:click={load} disabled={loading}>
          {loading ? "Carregando…" : "Atualizar"}
        </button>
      </div>
    </div>
  </section>

  {#if pageError}<div class="alert">{pageError}</div>{/if}

  {#if data}
    <section class="panel digest-panel">
      <div class="panel-head">
        <div>
          <span class="page-eyebrow">F1 · IA · resumo</span>
          <h2 class="form-title">Brief do dia</h2>
        </div>
        <button class="tiny ghost" on:click={() => loadDigest(true)} disabled={digestLoading}>
          {digestLoading ? "Gerando…" : digest ? "Regenerar" : "Gerar"}
        </button>
      </div>
      {#if digestError}
        <p class="alert">{digestError}</p>
      {:else if digest}
        <p class="digest-body">{digest.body}</p>
        <p class="digest-meta mono">
          via {digest.provider}{digest.cached ? " · cache" : " · novo"}
        </p>
      {:else if digestLoading}
        <p class="empty">Gerando resumo…</p>
      {:else}
        <p class="empty">Nenhum resumo gerado hoje. Clique em "Gerar".</p>
      {/if}
    </section>

    <section class="cards-grid">
      <Card eyebrow="C1" label="Receita comercial" value={fmtMoney(data.cards.receita)} accent />
      <Card eyebrow="C2" label="Despesa comercial real" value={fmtMoney(data.cards.despesa)} />
      <Card
        eyebrow="C3"
        label="Lucro líquido"
        value={fmtMoney(data.cards.lucro)}
        tone={Number(data.cards.lucro) >= 0 ? "ok" : "warn"}
      />
      <Card eyebrow="C4" label="Margem média" value={fmtPct(data.cards.margem_pct)} />
      <Card eyebrow="C5" label="Gasto pessoal" value={fmtMoney(data.cards.gasto_pessoal)} tone="muted" />
      <Card eyebrow="C6" label="Orçamentos por estado" value={String(estadoTotal)} hint="total no período">
        {#if estadoBreakdown.length > 0}
          <ul class="mini-list">
            {#each estadoBreakdown as [k, n]}
              <li><span class="muted-text">{statusLabel(k)}</span><span class="mono">{n}</span></li>
            {/each}
          </ul>
        {/if}
      </Card>
      <Card eyebrow="C7" label="Taxa de conversão" value={fmtPct(data.cards.taxa_conversao_pct)} hint="aprovado / orçado" />
      <Card
        eyebrow="C8"
        label="Estoque atual"
        value={`${fmtNum(data.cards.estoque.total_grams, 0)} g`}
        hint={`≈ ${fmtMoney(data.cards.estoque.estimated_value)}`}
      />
    </section>

    <section class="viz-grid">
      <article class="panel">
        <div class="panel-head">
          <div>
            <span class="page-eyebrow">G1</span>
            <h2 class="form-title">Receita vs despesa</h2>
          </div>
          <span class="dim mono">{revExpSeries.length} períodos</span>
        </div>
        {#if revExpSeries.length === 0}
          <div class="empty">sem dados no período</div>
        {:else}
          <div class="rev-exp">
            <svg viewBox="0 0 320 80" preserveAspectRatio="none" class="rev-exp-svg">
              <path d={revExpPath(revExpReceita)} fill="none" stroke="var(--ok)" stroke-width="2" />
              <path d={revExpPath(revExpDespesa)} fill="none" stroke="var(--danger)" stroke-width="2" />
            </svg>
            <div class="rev-exp-legend">
              <span><span class="dot rev"></span> Receita</span>
              <span><span class="dot exp"></span> Despesa</span>
            </div>
            <div class="rev-exp-ticks">
              {#each revExpSeries as p}
                <span class="mono tick">{p.period}</span>
              {/each}
            </div>
          </div>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <span class="page-eyebrow">G2</span>
            <h2 class="form-title">Funil de orçamentos</h2>
          </div>
        </div>
        <Funnel stages={funilStages} />
      </article>

      <article class="panel">
        <div class="panel-head">
          <div>
            <span class="page-eyebrow">G3</span>
            <h2 class="form-title">Despesa por categoria</h2>
          </div>
        </div>
        <Pie slices={despesaCategorias} />
      </article>

      <article class="panel wide">
        <div class="panel-head">
          <div>
            <span class="page-eyebrow">G6</span>
            <h2 class="form-title">Orçado vs real</h2>
          </div>
          <span class="dim mono">{orcadoVsReal.length} orçamentos</span>
        </div>
        {#if orcadoVsReal.length === 0}
          <div class="empty">sem orçamentos produzidos no período</div>
        {:else}
          <div class="table-wrap">
            <table class="cmp-table">
              <thead>
                <tr>
                  <th>Orçamento</th>
                  <th class="right">Orçado</th>
                  <th class="right">Real</th>
                  <th class="right">Variância</th>
                </tr>
              </thead>
              <tbody>
                {#each orcadoVsReal as row}
                  <tr>
                    <td><a href={`/quotes/${row.quote_id}`} class="mono">{String(row.quote_id).slice(0, 8)}</a></td>
                    <td class="right mono">{fmtMoney(row.orcado)}</td>
                    <td class="right mono">{fmtMoney(row.real)}</td>
                    <td class="right mono" class:over={row.variancia_pct > 0} class:under={row.variancia_pct < 0}>
                      {row.variancia_pct > 0 ? "+" : ""}{fmtNum(row.variancia_pct, 1)}%
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </article>
    </section>

    <section class="lists-grid">
      <article class="panel">
        <div class="panel-head">
          <h2 class="section-title">L1 · Últimos orçamentos <span class="count">· {data.lists.ultimos_orcamentos.length}</span></h2>
        </div>
        {#if data.lists.ultimos_orcamentos.length === 0}
          <div class="empty">sem registros</div>
        {:else}
          <ul class="rows">
            {#each data.lists.ultimos_orcamentos as q}
              <li>
                <a class="row-link" href={`/quotes/${q.id}`}>
                  <span class="mono">{q.id.slice(0, 8)}</span>
                  <span class="tag {q.kind === 'commercial' ? 'brand' : 'muted'}">{q.kind}</span>
                  <span class="tag muted">{statusLabel(q.status)}</span>
                  <span class="mono dim">{fmtDate(q.created_at)}</span>
                </a>
              </li>
            {/each}
          </ul>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2 class="section-title">L2 · Parados em aprovado <span class="count">· {data.lists.parados.length}</span></h2>
        </div>
        {#if data.lists.parados.length === 0}
          <div class="empty">nenhum parado</div>
        {:else}
          <ul class="rows">
            {#each data.lists.parados as p}
              <li>
                <a class="row-link" href={`/quotes/${p.id}`}>
                  <span class="mono">{p.id.slice(0, 8)}</span>
                  <span class="mono dim">aprovado em {fmtDate(p.approved_at)}</span>
                </a>
              </li>
            {/each}
          </ul>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2 class="section-title">L3 · Spools baixos <span class="count">· {data.lists.spools_baixos.length}</span></h2>
        </div>
        {#if data.lists.spools_baixos.length === 0}
          <div class="empty">tudo abastecido</div>
        {:else}
          <ul class="rows">
            {#each data.lists.spools_baixos as sp}
              <li>
                <a class="row-link" href="/spools">
                  <span class="mono">{sp.material_type}</span>
                  <span class="mono dim">{fmtNum(sp.remaining_grams, 0)} g</span>
                </a>
              </li>
            {/each}
          </ul>
        {/if}
      </article>

      <article class="panel">
        <div class="panel-head">
          <h2 class="section-title">L4 · Inbox watcher <span class="count">· {data.lists.inbox.length}</span></h2>
        </div>
        {#if data.lists.inbox.length === 0}
          <div class="empty">nada pendente</div>
        {:else}
          <ul class="rows">
            {#each data.lists.inbox as r}
              <li>
                <a class="row-link" href="/inbox">
                  <span class="mono">{(r.original_path || "").split("/").pop()}</span>
                </a>
              </li>
            {/each}
          </ul>
        {/if}
      </article>
    </section>
  {/if}
{/if}

<style>
  .page-head {
    margin-bottom: 1.5rem;
  }
  .filter-bar {
    margin-bottom: 1.25rem;
  }
  .filter-grid {
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }
  .cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  .viz-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  .viz-grid .wide { grid-column: 1 / -1; }
  @media (max-width: 880px) {
    .viz-grid {
      grid-template-columns: 1fr;
    }
  }

  .rev-exp { display: flex; flex-direction: column; gap: 0.5rem; padding-top: 0.5rem; }
  .rev-exp-svg { width: 100%; height: 100px; }
  .rev-exp-legend {
    display: flex;
    gap: 1rem;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .rev-exp-legend .dot {
    display: inline-block;
    width: 10px;
    height: 2px;
    margin-right: 0.35rem;
    vertical-align: middle;
  }
  .rev-exp-legend .dot.rev { background: var(--ok); }
  .rev-exp-legend .dot.exp { background: var(--danger); }
  .rev-exp-ticks {
    display: flex;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--muted);
    letter-spacing: 0.06em;
  }
  .rev-exp-ticks .tick:nth-child(n + 2) { margin-left: -1rem; }

  .cmp-table { width: 100%; border-collapse: collapse; }
  .cmp-table th, .cmp-table td { padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--line); font-size: 0.85rem; }
  .cmp-table th { font-family: var(--font-mono); font-size: 0.65rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); }
  .cmp-table td.right, .cmp-table th.right { text-align: right; }
  .cmp-table td.over { color: var(--danger); }
  .cmp-table td.under { color: var(--ok); }
  .cmp-table a { color: var(--ink); text-decoration: none; }
  .cmp-table a:hover { text-decoration: underline; }

  .digest-panel { margin-bottom: 1.2rem; border-left: 4px solid var(--brand); }
  .digest-body {
    font-family: var(--font-display);
    font-size: 1.02rem;
    line-height: 1.45;
    color: var(--ink);
    margin: 0.4rem 0 0.3rem;
  }
  .digest-meta {
    color: var(--muted);
    font-size: 0.7rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .alert { color: var(--danger); }
  .empty { color: var(--muted); font-style: italic; }
  .lists-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 1rem;
  }
  .form-title {
    margin: 0;
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.1rem;
    letter-spacing: -0.01em;
  }
  .section-title {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--ink);
    margin: 0;
  }
  .section-title .count {
    color: var(--muted);
    font-weight: 400;
  }
  .mini-list {
    list-style: none;
    margin: 0.25rem 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.18rem;
    font-size: 0.78rem;
  }
  .mini-list li {
    display: flex;
    justify-content: space-between;
    color: var(--muted);
  }
  .muted-text {
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  .rows li {
    border-bottom: 1px dashed var(--line);
  }
  .rows li:last-child {
    border-bottom: none;
  }
  .row-link {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    padding: 0.55rem 0.1rem;
    text-decoration: none;
    color: inherit;
    font-size: 0.85rem;
  }
  .row-link:hover {
    background: rgba(26, 26, 29, 0.025);
  }
  .dim {
    color: var(--muted);
  }
  .empty {
    padding: 1.5rem 0.5rem;
    text-align: center;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.74rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }
</style>
