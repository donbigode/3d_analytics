<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type {
    CalibrationInsight,
    CalibrationInsightApplyResult,
    FailureRateRow,
    PersonalProjects,
    ProductionSuggestionsOut,
  } from "$lib/types";

  type Overview = {
    window_days: number;
    funnel: Record<string, number>;
    conversion_pct: number;
    approved_count: number;
    finalized_count: number;
    avg_ticket: number | null;
    top_materials_grams: { label: string; grams: number }[];
    top_materials_revenue: { label: string; revenue: number }[];
    top_names: { name: string; count: number }[];
    source_attribution: { site: string; count: number }[];
    multi_color_share_pct: number;
    latest_digest: {
      date: string;
      provider: string;
      body: string;
    } | null;
    digest_count_window: number;
    alerts: { pending_items_draft: number; stalled_quotes: number };
    top_clients: { name: string; count: number }[];
  };

  let rows: CalibrationInsight[] = [];
  let overview: Overview | null = null;
  let overviewError = "";
  let personal: PersonalProjects | null = null;
  let failureRates: FailureRateRow[] = [];
  let suggestions: ProductionSuggestionsOut | null = null;
  let generatingSuggestions = false;
  let suggestionsError = "";
  let loading = true;
  let listError = "";
  let actingId: string | null = null;
  let banner = "";

  async function loadOverview() {
    try {
      overview = await api<Overview>("/insights/overview?days=90");
    } catch (err) {
      handleApiError(err);
      overviewError = errorMessage(err, "Falha ao carregar painel de insights.");
    }
    try {
      const fr = await api<{ by_material: FailureRateRow[] }>("/insights/failure-rates");
      failureRates = fr.by_material;
    } catch (err) {
      handleApiError(err);
    }
    await loadSuggestions();
    try {
      personal = await api<PersonalProjects>("/insights/personal-projects");
    } catch (err) {
      handleApiError(err);
    }
  }

  async function loadSuggestions() {
    try {
      suggestions = await api<ProductionSuggestionsOut>("/insights/production-suggestions");
    } catch (err) {
      handleApiError(err);
    }
  }

  async function generateSuggestions() {
    generatingSuggestions = true;
    suggestionsError = "";
    try {
      await api("/insights/production-suggestions/generate", { method: "POST" });
      await loadSuggestions();
    } catch (err) {
      handleApiError(err);
      suggestionsError = errorMessage(err, "Falha ao gerar sugestões.");
    } finally {
      generatingSuggestions = false;
    }
  }

  async function load() {
    loading = true;
    listError = "";
    try {
      rows = await api<CalibrationInsight[]>("/calibration/insights");
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar sugestões.");
    } finally {
      loading = false;
    }
  }

  async function apply(id: string, scopeRef: string) {
    actingId = id;
    banner = "";
    try {
      const res = await api<CalibrationInsightApplyResult>(
        `/calibration/insights/${id}/apply`,
        { method: "POST" }
      );
      banner = `Sugestão aplicada em ${res.material_code}: ${res.field} → ${fmtNumber(res.new_value)}.`;
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao aplicar sugestão.");
    } finally {
      actingId = null;
    }
  }

  async function dismiss(id: string) {
    actingId = id;
    banner = "";
    try {
      await api(`/calibration/insights/${id}/dismiss`, { method: "POST" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao descartar sugestão.");
    } finally {
      actingId = null;
    }
  }

  function fmtNumber(v: number | string, opts?: { suffix?: string }): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    const formatted = n.toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return opts?.suffix ? `${formatted}${opts.suffix}` : formatted;
  }

  function fmtMoney(v: number | string): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function fmtDelta(v: number | string): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(2)}%`;
  }

  function scopeLabel(s: CalibrationInsight): string {
    if (s.scope_kind === "material_failure") {
      return `Material · ${s.scope_ref} · taxa de falha`;
    }
    return `Material · ${s.scope_ref} · preço de referência`;
  }

  function headline(s: CalibrationInsight): string {
    const d = typeof s.delta_pct === "string" ? parseFloat(s.delta_pct) : s.delta_pct;
    const up = d > 0;
    if (s.scope_kind === "material_failure") {
      return up
        ? `Falha real de ${s.scope_ref} está ${Math.abs(d).toFixed(1)} pts acima do cadastro`
        : `Falha real de ${s.scope_ref} está ${Math.abs(d).toFixed(1)} pts abaixo do cadastro`;
    }
    return up
      ? `Preço real de ${s.scope_ref} está ${Math.abs(d).toFixed(1)}% acima do cadastro`
      : `Preço real de ${s.scope_ref} está ${Math.abs(d).toFixed(1)}% abaixo do cadastro`;
  }

  function unit(s: CalibrationInsight, value: number | string): string {
    if (s.scope_kind === "material_failure") return `${fmtNumber(value)} %`;
    return `${fmtMoney(value)}/kg`;
  }

  // group by material for visual hierarchy
  $: grouped = (() => {
    const m = new Map<string, CalibrationInsight[]>();
    for (const r of rows) {
      const k = r.scope_ref;
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(r);
    }
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  })();

  function fmtPct(v: number): string {
    return `${v.toFixed(1)}%`;
  }
  function fmtGrams(v: number): string {
    if (v >= 1000) return `${(v / 1000).toFixed(2)} kg`;
    return `${Math.round(v)} g`;
  }
  function statusLabelPt(s: string): string {
    return (
      {
        draft: "rascunho",
        orcado: "orçado",
        aprovado: "aprovado",
        produzido: "produzido",
        entregue: "entregue",
        cancelado: "cancelado",
      } as Record<string, string>
    )[s] ?? s;
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
    loadOverview();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Operação / 06 · insights</span>
  <h1 class="page-title">Insights<em>.</em></h1>
  <p class="page-lede">
    O que o sistema está vendo do seu negócio: pulso comercial, materiais
    campeões, demanda recorrente e ajustes de calibração que o uso real está
    sugerindo.
  </p>
</header>

{#if overviewError}
  <div class="banner alert">{overviewError}</div>
{/if}

{#if personal && (personal.people.length > 0 || personal.unassigned_count > 0)}
  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">Projetos pessoais · últimos 12 meses</span>
      <h2 class="form-title">Quem sobe mais projeto pessoal</h2>
    </div>
    <table class="pp-table">
      <thead>
        <tr>
          <th>Pessoa</th>
          <th class="pp-num">Projetos</th>
          <th class="pp-num">Filamento (g)</th>
          <th class="pp-num">Custo</th>
        </tr>
      </thead>
      <tbody>
        {#each personal.people as p (p.person_id)}
          <tr>
            <td>{p.name}</td>
            <td class="pp-num">{p.count}</td>
            <td class="pp-num">{Number(p.grams).toLocaleString("pt-BR", { maximumFractionDigits: 0 })}</td>
            <td class="pp-num">{fmtMoney(p.cpv)}</td>
          </tr>
        {/each}
        {#if personal.people.length === 0}
          <tr><td colspan="4" class="pp-empty">Nenhum projeto pessoal atribuído ainda</td></tr>
        {/if}
      </tbody>
    </table>
    <p class="pp-hint">
      Compartilhados (2+ pessoas): {personal.shared_count} · Sem marcação: {personal.unassigned_count}.
      Projeto compartilhado conta pra cada pessoa.
    </p>
  </section>
{/if}

{#if overview}
  <!-- ============ Pulso comercial ============ -->
  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">Pulso comercial · últimos 30 dias</span>
      <h2 class="form-title">Funil comercial</h2>
    </div>
    <div class="kpi-row">
      <div class="kpi">
        <span class="kpi-label">Orçamentos finalizados</span>
        <span class="kpi-value">{overview.finalized_count}</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Aprovados+</span>
        <span class="kpi-value">{overview.approved_count}</span>
      </div>
      <div class="kpi">
        <span class="kpi-label">Conversão</span>
        <span class="kpi-value">{fmtPct(overview.conversion_pct)}</span>
      </div>
      {#if overview.avg_ticket !== null}
        <div class="kpi">
          <span class="kpi-label">Ticket médio (apr.)</span>
          <span class="kpi-value">{fmtMoney(overview.avg_ticket)}</span>
        </div>
      {/if}
      <div class="kpi">
        <span class="kpi-label">Multicolor</span>
        <span class="kpi-value">{fmtPct(overview.multi_color_share_pct)}</span>
      </div>
    </div>
    {#if Object.keys(overview.funnel).length > 0}
      <ul class="funnel-list">
        {#each Object.entries(overview.funnel) as [status, n]}
          <li>
            <span class="mono">{statusLabelPt(status)}</span>
            <span class="bar" style="--w: {Math.min(100, Math.round(100 * n / Math.max(1, overview.finalized_count + (overview.funnel.draft ?? 0))))}%"></span>
            <span class="mono">{n}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">Produção</span>
      <h2 class="form-title">Atenção na produção · taxa de falha</h2>
    </div>
    {#if failureRates.length === 0}
      <p class="empty">Sem eventos de produção ainda. Conclua ou marque falhas na Capacidade.</p>
    {:else}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Material</th>
              <th class="right">Falhas</th>
              <th class="right">Total</th>
              <th class="right">Taxa</th>
            </tr>
          </thead>
          <tbody>
            {#each failureRates as r (r.material_type)}
              <tr>
                <td class="mono">{r.material_type}</td>
                <td class="right mono">{r.failures}</td>
                <td class="right mono">{r.total}</td>
                <td class="right mono">{(r.failure_rate * 100).toFixed(0)}%</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    <div class="suggest-head">
      <h3 class="form-title">Sugestões da IA</h3>
      <button class="tiny" on:click={generateSuggestions} disabled={generatingSuggestions}>
        {generatingSuggestions ? "Gerando…" : suggestions?.generated_at ? "Regerar" : "Gerar sugestões"}
      </button>
    </div>
    {#if suggestionsError}<div class="banner alert">{suggestionsError}</div>{/if}
    {#if suggestions && suggestions.stale && suggestions.generated_at}
      <p class="hint">Há novas falhas desde a última geração — clique em Regerar.</p>
    {/if}
    {#if suggestions && suggestions.suggestions.length > 0}
      <ul class="suggest-list">
        {#each suggestions.suggestions as s}
          <li><strong class="mono">{s.material_type}</strong> — {s.advice}</li>
        {/each}
      </ul>
    {:else if suggestions && !suggestions.generated_at}
      <p class="empty">Sem sugestões ainda. Gere a partir das falhas registradas.</p>
    {/if}
  </section>

  {#if overview.alerts.pending_items_draft > 0 || overview.alerts.stalled_quotes > 0}
    <section class="panel attention">
      <div class="panel-head">
        <span class="page-eyebrow">Atenção</span>
        <h2 class="form-title">Pontos abertos</h2>
      </div>
      <ul class="alert-list">
        {#if overview.alerts.pending_items_draft > 0}
          <li>
            <strong>{overview.alerts.pending_items_draft}</strong> peça(s) em rascunho com material pendente —
            <a href="/quotes?status=draft">resolver</a>.
          </li>
        {/if}
        {#if overview.alerts.stalled_quotes > 0}
          <li>
            <strong>{overview.alerts.stalled_quotes}</strong> orçamento(s) parado(s) há mais de 7 dias em
            "orçado" —
            <a href="/quotes?status=orcado">retomar contato</a>.
          </li>
        {/if}
      </ul>
    </section>
  {/if}

  <!-- ============ Materiais campeões ============ -->
  {#if overview.top_materials_grams.length > 0 || overview.top_materials_revenue.length > 0}
    <section class="panel two-col">
      <div>
        <div class="panel-head">
          <span class="page-eyebrow">Materiais · 90 dias</span>
          <h2 class="form-title">Top por volume</h2>
        </div>
        {#if overview.top_materials_grams.length === 0}
          <p class="empty-inline">Sem consumo registrado.</p>
        {:else}
          <ol class="rank">
            {#each overview.top_materials_grams as m, i}
              <li>
                <span class="rank-pos mono">{i + 1}</span>
                <span class="rank-label">{m.label}</span>
                <span class="rank-val mono">{fmtGrams(m.grams)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>
      <div>
        <div class="panel-head">
          <span class="page-eyebrow">Materiais · 90 dias</span>
          <h2 class="form-title">Top por valor de filamento</h2>
        </div>
        {#if overview.top_materials_revenue.length === 0}
          <p class="empty-inline">—</p>
        {:else}
          <ol class="rank">
            {#each overview.top_materials_revenue as m, i}
              <li>
                <span class="rank-pos mono">{i + 1}</span>
                <span class="rank-label">{m.label}</span>
                <span class="rank-val mono">{fmtMoney(m.revenue)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>
    </section>
  {/if}

  <!-- ============ Demanda recorrente ============ -->
  {#if overview.top_names.length > 0 || overview.top_clients.length > 0}
    <section class="panel two-col">
      <div>
        <div class="panel-head">
          <span class="page-eyebrow">Peças mais orçadas</span>
          <h2 class="form-title">Demanda recorrente</h2>
        </div>
        {#if overview.top_names.length === 0}
          <p class="empty-inline">Sem peças repetidas ainda.</p>
        {:else}
          <ol class="rank">
            {#each overview.top_names as n, i}
              <li>
                <span class="rank-pos mono">{i + 1}</span>
                <span class="rank-label">{n.name}</span>
                <span class="rank-val mono">{n.count}×</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>
      <div>
        <div class="panel-head">
          <span class="page-eyebrow">Clientes recorrentes</span>
          <h2 class="form-title">Top clientes · 90 dias</h2>
        </div>
        {#if overview.top_clients.length === 0}
          <p class="empty-inline">Sem clientes cadastrados em orçamentos.</p>
        {:else}
          <ol class="rank">
            {#each overview.top_clients as c, i}
              <li>
                <span class="rank-pos mono">{i + 1}</span>
                <span class="rank-label">{c.name}</span>
                <span class="rank-val mono">{c.count} orç.</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>
    </section>
  {/if}

  <!-- ============ Atribuição de modelos ============ -->
  {#if overview.source_attribution.length > 0}
    <section class="panel">
      <div class="panel-head">
        <span class="page-eyebrow">Catálogo externo · 90 dias</span>
        <h2 class="form-title">De onde vêm os modelos</h2>
      </div>
      <ul class="src-list">
        {#each overview.source_attribution as s}
          <li>
            <span class="mono">{s.site}</span>
            <span class="bar" style="--w: {Math.round(100 * s.count / overview.source_attribution.reduce((a, x) => a + x.count, 0))}%"></span>
            <span class="mono">{s.count}</span>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <!-- ============ Briefing IA ============ -->
  {#if overview.latest_digest}
    <section class="panel">
      <div class="panel-head">
        <div>
          <span class="page-eyebrow">IA · briefing diário · {overview.digest_count_window} em 90 dias</span>
          <h2 class="form-title">Última leitura ({overview.latest_digest.date})</h2>
        </div>
      </div>
      <p class="digest-body">{overview.latest_digest.body}</p>
      <p class="digest-meta mono">provider: {overview.latest_digest.provider}</p>
    </section>
  {/if}
{/if}

<header class="page-head" style="margin-top:2rem;">
  <span class="page-eyebrow">Auto-calibração</span>
  <h2 class="page-title" style="font-size:1.4rem;">Sugestões do consumo real<em>.</em></h2>
  <p class="page-lede">
    Comparamos o que você <em>orçou</em> com o que de fato foi <em>consumido</em> nas
    produções para sugerir ajustes no cadastro. Cada sugestão exige mínimo de 5 amostras e
    desvio acima de 3% antes de aparecer aqui.
  </p>
</header>

{#if banner}
  <div class="banner ok">{banner}</div>
{/if}
{#if listError}
  <div class="banner alert">{listError}</div>
{/if}

<section class="panel toolbar">
  <div class="panel-head">
    <div class="heading">
      <span class="page-eyebrow">Sugestões abertas</span>
      <h2 class="form-title">
        {rows.length} {rows.length === 1 ? "ajuste sugerido" : "ajustes sugeridos"}
      </h2>
    </div>
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "Recalculando…" : "Recalcular"}
    </button>
  </div>
</section>

{#if loading && rows.length === 0}
  <section class="panel"><p class="empty">Carregando insights…</p></section>
{:else if rows.length === 0}
  <section class="panel empty-state">
    <span class="page-eyebrow">Tudo certo por aqui</span>
    <h3>Nada para calibrar ainda.</h3>
    <p>
      Conforme você produzir mais peças, o sistema vai comparar o consumo real
      com o que estava orçado. Sugestões de ajuste aparecem aqui quando o desvio
      for relevante.
    </p>
  </section>
{:else}
  {#each grouped as [code, items] (code)}
    <section class="panel group">
      <div class="panel-head">
        <h2 class="section-title">
          <span class="mono mat">{code}</span>
          <span class="count">· {items.length} {items.length === 1 ? "sugestão" : "sugestões"}</span>
        </h2>
      </div>
      <div class="cards">
        {#each items as ins (ins.id)}
          {@const dir = (typeof ins.delta_pct === "string" ? parseFloat(ins.delta_pct) : ins.delta_pct) >= 0 ? "up" : "down"}
          <article class="card" data-dir={dir}>
            <header>
              <span class="eyebrow">{scopeLabel(ins)}</span>
              <h3>{headline(ins)}</h3>
            </header>
            <dl class="values">
              <div>
                <dt>Atual</dt>
                <dd class="mono">{unit(ins, ins.current_value)}</dd>
              </div>
              <div class="arrow" aria-hidden="true">→</div>
              <div>
                <dt>Sugerido</dt>
                <dd class="mono accent">{unit(ins, ins.suggested_value)}</dd>
              </div>
              <div class="delta-pill {dir}">{fmtDelta(ins.delta_pct)}</div>
            </dl>
            <footer>
              <span class="sample mono">
                amostra · {ins.sample_size} {ins.sample_size === 1 ? "produção" : "produções"}
              </span>
              <div class="actions">
                <button
                  class="tiny ghost"
                  disabled={actingId === ins.id}
                  on:click={() => dismiss(ins.id)}
                >
                  Descartar
                </button>
                <button
                  class="tiny"
                  disabled={actingId === ins.id}
                  on:click={() => apply(ins.id, ins.scope_ref)}
                >
                  {actingId === ins.id ? "Aplicando…" : "Aplicar"}
                </button>
              </div>
            </footer>
          </article>
        {/each}
      </div>
    </section>
  {/each}
{/if}

<style>
  .pp-table { width: 100%; border-collapse: collapse; }
  .pp-table th, .pp-table td {
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid var(--line);
    text-align: left;
  }
  .pp-num { text-align: right; font-variant-numeric: tabular-nums; }
  .pp-empty { color: var(--muted); text-align: center; }
  .pp-hint { color: var(--muted); font-size: 0.85rem; margin-top: 0.5rem; }
  .page-head {
    margin-bottom: 1.5rem;
  }
  .page-head em {
    color: var(--brand);
    font-style: italic;
  }
  .banner {
    padding: 0.7rem 0.95rem;
    border: 1px solid var(--line-strong);
    font-size: 0.88rem;
    margin-bottom: 1rem;
    background: var(--paper);
  }
  .banner.ok {
    border-left: 4px solid var(--ok);
  }
  .banner.alert {
    border-left: 4px solid var(--danger);
    color: var(--danger);
  }
  .toolbar {
    margin-bottom: 1.5rem;
  }
  .form-title {
    margin: 0;
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.25rem;
    letter-spacing: -0.01em;
  }
  .heading {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .empty-state {
    padding: 3rem 2rem;
    text-align: center;
    border-style: dashed;
  }
  .empty-state h3 {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.6rem;
    margin: 0.6rem 0 0.5rem;
    letter-spacing: -0.01em;
  }
  .empty-state p {
    color: var(--muted);
    max-width: 50ch;
    margin: 0 auto;
  }

  .group {
    margin-bottom: 1.5rem;
  }
  .mat {
    color: var(--ink);
    letter-spacing: 0.18em;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 1rem;
    margin-top: 0.5rem;
  }
  .card {
    border: 1px solid var(--line-strong);
    background: var(--paper);
    padding: 1.1rem 1.1rem 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
    position: relative;
    overflow: hidden;
  }
  .card::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--muted);
  }
  .card[data-dir="up"]::before {
    background: var(--danger);
  }
  .card[data-dir="down"]::before {
    background: var(--ok);
  }
  .card header {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .card .eyebrow {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .card h3 {
    margin: 0;
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.08rem;
    line-height: 1.25;
    letter-spacing: -0.005em;
    color: var(--ink);
  }
  .values {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: end;
    gap: 0.5rem 0.8rem;
    margin: 0;
  }
  .values > div:not(.arrow):not(.delta-pill) {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .values dt {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .values dd {
    margin: 0;
    font-size: 1.05rem;
  }
  .values dd.accent {
    color: var(--brand);
    font-weight: 500;
  }
  .arrow {
    font-family: var(--font-mono);
    color: var(--muted);
    align-self: center;
    padding-bottom: 0.15rem;
  }
  .delta-pill {
    grid-column: 1 / -1;
    justify-self: start;
    margin-top: 0.4rem;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    padding: 0.18rem 0.55rem;
    border: 1px solid var(--line-strong);
    letter-spacing: 0.08em;
  }
  .delta-pill.up {
    color: var(--danger);
    border-color: var(--danger);
  }
  .delta-pill.down {
    color: var(--ok);
    border-color: var(--ok);
  }
  .card footer {
    border-top: 1px dashed var(--line);
    padding-top: 0.7rem;
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
  }
  .sample {
    font-size: 0.66rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .actions {
    display: inline-flex;
    gap: 0.4rem;
  }
  .empty {
    padding: 2rem 1rem;
    text-align: center;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.74rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }
  .empty-inline {
    color: var(--muted);
    font-size: 0.85rem;
    padding: 0.5rem 0;
  }
  /* ---------- New overview sections ---------- */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem;
    margin: 0.5rem 0 0.9rem;
  }
  .kpi {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    padding: 0.7rem 0.9rem;
    background: var(--paper);
    border: 1px solid var(--line);
  }
  .kpi-label {
    font-family: var(--font-mono);
    font-size: 0.66rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .kpi-value {
    font-family: var(--font-display);
    font-size: 1.6rem;
    font-weight: 500;
    letter-spacing: -0.01em;
    color: var(--ink);
  }
  .funnel-list,
  .src-list {
    list-style: none;
    padding: 0;
    margin: 0.3rem 0 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .funnel-list li,
  .src-list li {
    display: grid;
    grid-template-columns: 8rem 1fr 4rem;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.85rem;
  }
  .funnel-list .bar,
  .src-list .bar {
    height: 0.6rem;
    background: var(--line);
    position: relative;
    display: inline-block;
  }
  .funnel-list .bar::after,
  .src-list .bar::after {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: var(--w, 0%);
    background: var(--brand);
  }
  .two-col {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5rem;
  }
  .two-col > div { display: contents; }
  @supports (display: contents) {
    /* fallback handled above */
  }
  .two-col {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 2rem;
  }
  .two-col > div { display: block; }
  .rank {
    list-style: none;
    padding: 0;
    margin: 0.4rem 0 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .rank li {
    display: grid;
    grid-template-columns: 1.6rem 1fr auto;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.4rem 0.55rem;
    background: var(--paper);
    border: 1px solid var(--line);
    font-size: 0.88rem;
  }
  .rank-pos { color: var(--muted); font-size: 0.78rem; }
  .rank-label { color: var(--ink); }
  .rank-val { color: var(--brand); font-weight: 500; }
  .panel.attention {
    border-left: 4px solid var(--warn, #f59e0b);
  }
  .alert-list {
    list-style: none;
    padding: 0;
    margin: 0.4rem 0 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.92rem;
  }
  .alert-list a { color: var(--brand); }
  .digest-body {
    white-space: pre-wrap;
    line-height: 1.55;
    margin: 0.4rem 0 0.6rem;
    color: var(--ink);
  }
  .digest-meta {
    color: var(--muted);
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .suggest-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-top: 1.25rem;
    padding-top: 1rem;
    border-top: 1px dashed var(--line);
  }
  .suggest-list {
    list-style: none;
    margin: 0.6rem 0 0;
    padding: 0;
    display: grid;
    gap: 0.45rem;
  }
  .suggest-list li {
    font-size: 0.9rem;
    line-height: 1.4;
  }
  .hint {
    font-size: 0.8rem;
    color: var(--muted);
    margin: 0.5rem 0 0;
  }
</style>
