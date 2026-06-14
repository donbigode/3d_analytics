<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { ForecastOut, InProductionOut, InProductionJob } from "$lib/types";

  let forecast: ForecastOut | null = null;
  let inProduction: InProductionOut | null = null;
  let loading = true;
  let listError = "";
  let acting = "";

  // fail modal
  let failJob: InProductionJob | null = null;
  let failDescription = "";
  let failAttempts = 1;
  let failError = "";
  let failing = false;

  async function load() {
    loading = true;
    listError = "";
    try {
      [forecast, inProduction] = await Promise.all([
        api<ForecastOut>("/capacity/forecast"),
        api<InProductionOut>("/capacity/in-production"),
      ]);
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar previsão.");
    } finally {
      loading = false;
    }
  }

  async function complete(job: InProductionJob) {
    const raw = prompt("Quantas tentativas até concluir?", "1");
    if (raw === null) return;
    const attempts = Math.max(1, parseInt(raw, 10) || 1);
    acting = job.quote_id;
    try {
      await api(`/quotes/${job.quote_id}/transitions/complete`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ attempts }),
      });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao concluir.");
    } finally {
      acting = "";
    }
  }

  function openFail(job: InProductionJob) {
    failJob = job;
    failDescription = "";
    failAttempts = 1;
    failError = "";
  }

  async function confirmFail() {
    if (!failJob) return;
    const desc = failDescription.trim();
    if (!desc) {
      failError = "Descreva o que houve.";
      return;
    }
    failing = true;
    failError = "";
    try {
      await api(`/quotes/${failJob.quote_id}/transitions/fail`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          failure_description: desc,
          attempts: Math.max(1, failAttempts),
        }),
      });
      failJob = null;
      await load();
    } catch (err) {
      handleApiError(err);
      failError = errorMessage(err, "Falha ao registrar.");
    } finally {
      failing = false;
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
  <section class="panel">
    <div class="panel-head">
      <h2 class="section-title">
        Em produção <span class="count">· {inProduction?.jobs.length ?? 0}</span>
      </h2>
    </div>
    {#if !inProduction || inProduction.jobs.length === 0}
      <p class="empty">Nada na impressora agora. Produza um orçamento aprovado.</p>
    {:else}
      <ul class="prod-rows">
        {#each inProduction.jobs as job, i (job.quote_id)}
          <li class="prod-row">
            <div class="prod-info">
              <span class="mono pos">{i + 1}</span>
              <a class="prod-name" href={`/quotes/${job.quote_id}`}>{job.name}</a>
              <span class="muted mono">· {job.kind === "personal" ? "pessoal" : "comercial"} · {fmtHours(job.hours)}</span>
            </div>
            <div class="prod-actions">
              <button class="tiny" on:click={() => complete(job)} disabled={acting === job.quote_id}>
                {acting === job.quote_id ? "…" : "Concluir"}
              </button>
              <button class="tiny danger" on:click={() => openFail(job)} disabled={acting === job.quote_id}>
                Falhar
              </button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

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

{#if failJob}
  <div class="modal-backdrop" on:click|self={() => (failJob = null)} role="presentation">
    <div class="modal">
      <h2>Registrar falha — {failJob.name}</h2>
      <p class="dim">O material já gasto permanece como despesa. Descreva o que houve para alimentar os insights.</p>
      {#if failError}<div class="banner alert">{failError}</div>{/if}
      <label class="field">
        O que houve?
        <textarea bind:value={failDescription} rows="3" placeholder="ex.: descolou da mesa na camada 40; warping nos cantos"></textarea>
      </label>
      <label class="field">
        Tentativas
        <input type="number" min="1" step="1" bind:value={failAttempts} />
      </label>
      <div class="modal-actions">
        <button class="ghost" on:click={() => (failJob = null)} disabled={failing}>Cancelar</button>
        <button class="danger" on:click={confirmFail} disabled={failing}>
          {failing ? "Registrando…" : "Registrar falha"}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .page-head { margin-bottom: 1.5rem; }
  .prod-rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; }
  .prod-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 0.75rem; padding: 0.55rem 0.7rem; border: 1px solid var(--line);
    border-radius: 6px;
  }
  .prod-info { display: flex; align-items: baseline; gap: 0.5rem; min-width: 0; }
  .prod-info .pos { color: var(--muted); }
  .prod-name { font-weight: 500; text-decoration: none; }
  .prod-actions { display: flex; gap: 0.4rem; flex-shrink: 0; }
  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.4);
    display: flex; align-items: center; justify-content: center; z-index: 50; padding: 1rem;
  }
  .modal {
    background: var(--paper); border: 1px solid var(--line-strong);
    border-radius: 8px; padding: 1.25rem; width: min(480px, 100%);
    display: grid; gap: 0.75rem;
  }
  .modal .field { display: grid; gap: 0.3rem; }
  .modal textarea, .modal input { width: 100%; }
  .modal-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
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
