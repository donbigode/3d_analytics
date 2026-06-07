<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { ForecastOut } from "$lib/types";

  let forecast: ForecastOut | null = null;
  let loading = true;
  let listError = "";

  async function load() {
    loading = true;
    listError = "";
    try {
      forecast = await api<ForecastOut>("/capacity/forecast");
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar previsão.");
    } finally {
      loading = false;
    }
  }

  function fmtHours(v: number | string): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    if (n < 1) return `${(n * 60).toFixed(0)}min`;
    const h = Math.floor(n);
    const m = Math.round((n - h) * 60);
    return m ? `${h}h ${m}min` : `${h}h`;
  }

  function fmtDate(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString("pt-BR", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return s;
    }
  }

  function fmtDay(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleDateString("pt-BR", {
        weekday: "long",
        day: "2-digit",
        month: "long",
      });
    } catch {
      return s;
    }
  }

  $: loadPct = (() => {
    if (!forecast) return 0;
    const hpd = parseFloat(String(forecast.hours_per_day)) || 22;
    const qh = parseFloat(String(forecast.queue_hours)) || 0;
    const todaysFraction = Math.min(qh, hpd);
    return Math.round((todaysFraction / hpd) * 100);
  })();

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Operação / 07 · planejamento</span>
  <h1 class="page-title">Capacidade<em>.</em></h1>
  <p class="page-lede">
    Soma as horas dos orçamentos aprovados pendentes e mostra quando a fila se esvazia,
    considerando <span class="mono">{forecast?.hours_per_day ?? "—"}h/dia</span> de
    operação. Mude o valor em <a href="/settings">Ajustes → Custo de produção</a>.
  </p>
</header>

{#if listError}<div class="banner alert">{listError}</div>{/if}

{#if loading && !forecast}
  <section class="panel"><p class="empty">Carregando…</p></section>
{:else if forecast}
  <section class="panel highlight">
    <div class="panel-head">
      <span class="page-eyebrow">Próxima janela livre</span>
      <button class="tiny ghost" on:click={load} disabled={loading}>
        {loading ? "Recarregando…" : "Recarregar"}
      </button>
    </div>
    <div class="hero">
      <span class="big-date">{fmtDay(forecast.next_available_at)}</span>
      <span class="big-time mono">{fmtDate(forecast.next_available_at)}</span>
    </div>
    <dl class="kvs">
      <dt>Fila</dt>
      <dd class="mono">{forecast.queue_jobs} {forecast.queue_jobs === 1 ? "job" : "jobs"} · {fmtHours(forecast.queue_hours)}</dd>
      <dt>Dias para esvaziar</dt>
      <dd class="mono">{forecast.days_until_clear}</dd>
      <dt>Carga estimada do dia atual</dt>
      <dd class="mono">{loadPct}%</dd>
    </dl>
    <div class="gauge" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={loadPct}>
      <div class="gauge-fill" style:width={`${Math.min(loadPct, 100)}%`}></div>
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <h2 class="section-title">Fila FIFO <span class="count">· {forecast.jobs.length}</span></h2>
    </div>
    {#if forecast.jobs.length === 0}
      <p class="empty">Nenhum orçamento aprovado aguardando. Boa hora pra orçar mais.</p>
    {:else}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Job</th>
              <th class="right">Horas</th>
              <th class="right">ETA</th>
              <th class="right">Link</th>
            </tr>
          </thead>
          <tbody>
            {#each forecast.jobs as job, i (job.quote_id)}
              <tr>
                <td class="mono">{i + 1}</td>
                <td>{job.name}</td>
                <td class="right mono">{fmtHours(job.hours)}</td>
                <td class="right mono">{fmtDate(job.eta)}</td>
                <td class="right">
                  <a class="tiny ghost" href={`/quotes/${job.quote_id}`}>abrir</a>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
{/if}

<style>
  .page-head { margin-bottom: 1.5rem; }
  .page-head em { color: var(--brand); font-style: italic; }
  .banner.alert {
    border-left: 4px solid var(--danger);
    padding: 0.7rem 0.95rem;
    border: 1px solid var(--line-strong);
    border-left-width: 4px;
    color: var(--danger);
    margin-bottom: 1rem;
  }
  .panel.highlight {
    margin-bottom: 1.5rem;
    border-left: 4px solid var(--brand);
  }
  .hero {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    margin: 0.75rem 0 1rem;
  }
  .big-date {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 2rem;
    letter-spacing: -0.02em;
    text-transform: capitalize;
  }
  .big-time {
    color: var(--muted);
    letter-spacing: 0.06em;
  }
  .kvs {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.35rem 0.9rem;
    margin: 0;
  }
  .kvs dt { color: var(--muted); font-size: 0.85rem; }
  .kvs dd { margin: 0; }
  .gauge {
    margin-top: 0.9rem;
    height: 6px;
    background: var(--line);
    border-radius: 3px;
    overflow: hidden;
  }
  .gauge-fill {
    height: 100%;
    background: var(--brand);
    transition: width 0.3s ease;
  }
  .empty {
    padding: 1.5rem 1rem;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.78rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  a.tiny { text-decoration: none; }
</style>
