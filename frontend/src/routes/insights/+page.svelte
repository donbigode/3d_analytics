<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type {
    CalibrationInsight,
    CalibrationInsightApplyResult,
  } from "$lib/types";

  let rows: CalibrationInsight[] = [];
  let loading = true;
  let listError = "";
  let actingId: string | null = null;
  let banner = "";

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

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Operação / 06 · auto-calibração</span>
  <h1 class="page-title">Insights<em>.</em></h1>
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
</style>
