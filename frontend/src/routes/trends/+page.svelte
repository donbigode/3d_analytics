<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { KeywordIdea, RankingRow, SparkPoint } from "$lib/types";

  let ideas: KeywordIdea[] = [];
  let ranking: RankingRow[] = [];
  let loading = true;
  let listError = "";

  // create form
  let newTerm = "";
  let newNotes = "";
  let submitting = false;
  let formError = "";

  // refresh
  let refreshing = false;
  let refreshBanner = "";

  let expanded: string | null = null;

  async function load() {
    loading = true;
    listError = "";
    try {
      const [i, r] = await Promise.all([
        api<KeywordIdea[]>("/trends/ideas"),
        api<RankingRow[]>("/trends/ranking"),
      ]);
      ideas = i;
      ranking = r;
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar tendências.");
    } finally {
      loading = false;
    }
  }

  async function addIdea() {
    if (!newTerm.trim()) return;
    formError = "";
    submitting = true;
    try {
      await api<KeywordIdea>("/trends/ideas", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          term: newTerm.trim(),
          notes: newNotes.trim() || null,
        }),
      });
      newTerm = "";
      newNotes = "";
      await load();
    } catch (err) {
      handleApiError(err);
      formError = errorMessage(err, "Falha ao adicionar termo.");
    } finally {
      submitting = false;
    }
  }

  async function removeIdea(id: string) {
    if (!confirm("Remover este termo? As observações também vão embora.")) return;
    try {
      await api(`/trends/ideas/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao remover.");
    }
  }

  async function refreshNow() {
    refreshing = true;
    refreshBanner = "";
    try {
      const res = await api<{ observations_created: number }>("/trends/refresh", {
        method: "POST",
      });
      refreshBanner = `Coleta concluída · ${res.observations_created} observações novas.`;
      await load();
    } catch (err) {
      handleApiError(err);
      refreshBanner = errorMessage(err, "Falha ao atualizar tendências.");
    } finally {
      refreshing = false;
    }
  }

  function num(v: number | string | null | undefined): number | null {
    if (v === null || v === undefined) return null;
    const n = typeof v === "string" ? parseFloat(v) : v;
    return Number.isFinite(n) ? n : null;
  }

  function fmtNum(v: number | string | null | undefined, dec = 2): string {
    const n = num(v);
    if (n === null) return "—";
    return n.toLocaleString("pt-BR", { maximumFractionDigits: dec });
  }

  function fmtMoney(v: number | string | null | undefined): string {
    const n = num(v);
    if (n === null) return "—";
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function sparkPath(points: SparkPoint[], w = 120, h = 32): string {
    if (!points || points.length < 2) return "";
    const values = points.map((p) => num(p.value) ?? 0);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const step = w / (values.length - 1);
    return values
      .map((v, i) => {
        const x = i * step;
        const y = h - ((v - min) / range) * h;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }

  function toggle(id: string) {
    expanded = expanded === id ? null : id;
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Inteligência / 08 · radar</span>
  <h1 class="page-title">Tendências<em>.</em></h1>
  <p class="page-lede">
    Monitora termos no <span class="mono">Google Trends</span> (interesse relativo BR)
    e na <span class="mono">API do Mercado Livre</span> (volume vendido + preço médio)
    para você identificar oportunidades antes do hype acabar.
  </p>
</header>

{#if listError}<div class="banner alert">{listError}</div>{/if}
{#if refreshBanner}<div class="banner ok">{refreshBanner}</div>{/if}

<section class="panel">
  <div class="panel-head">
    <div class="heading">
      <span class="page-eyebrow">Novo termo</span>
      <h2 class="form-title">Cadastrar palavra-chave</h2>
    </div>
    <button class="tiny ghost" on:click={refreshNow} disabled={refreshing || ideas.length === 0}>
      {refreshing ? "Coletando…" : "Atualizar agora"}
    </button>
  </div>
  <form class="form-grid" on:submit|preventDefault={addIdea}>
    <label class="field">
      Termo
      <input bind:value={newTerm} placeholder="ex: porta celular cabeceira" required />
    </label>
    <label class="field">
      Notas (opcional)
      <input bind:value={newNotes} placeholder="contexto livre" />
    </label>
    <div class="actions">
      <button type="submit" disabled={submitting || !newTerm.trim()}>
        {submitting ? "Adicionando…" : "Adicionar"}
      </button>
    </div>
  </form>
  {#if formError}<div class="banner alert inline">{formError}</div>{/if}
</section>

<section class="panel">
  <div class="panel-head">
    <h2 class="section-title">Ranking <span class="count">· {ranking.length}</span></h2>
  </div>

  {#if loading && ranking.length === 0}
    <p class="empty">Carregando ranking…</p>
  {:else if ranking.length === 0}
    <div class="empty-state">
      <span class="page-eyebrow">Sem dados ainda</span>
      <h3>Adicione termos acima e atualize.</h3>
      <p>
        A primeira coleta busca interesse no Google Trends e volume vendido no
        Mercado Livre. Depois o scheduler diário mantém o histórico em dia.
      </p>
    </div>
  {:else}
    <div class="rank-list">
      {#each ranking as row, i (row.id)}
        <article class="rank" class:expanded={expanded === row.id}>
          <div
            class="rank-head"
            role="button"
            tabindex="0"
            aria-expanded={expanded === row.id}
            on:click={() => toggle(row.id)}
            on:keydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(row.id); } }}
          >
            <span class="rank-pos mono">{String(i + 1).padStart(2, "0")}</span>
            <div class="rank-term">
              <strong>{row.term}</strong>
              <span class="muted">{row.top_listings.length} listings · clique para detalhar</span>
            </div>
            <svg class="spark" viewBox="0 0 120 32" preserveAspectRatio="none" aria-hidden="true">
              <path d={sparkPath(row.sparkline)} fill="none" stroke="currentColor" stroke-width="1.5" />
            </svg>
            <div class="metrics">
              <span class="metric"><dt>Score</dt><dd class="mono accent">{fmtNum(row.score, 1)}</dd></span>
              <span class="metric"><dt>Interesse</dt><dd class="mono">{fmtNum(row.interest, 0)}</dd></span>
              <span class="metric"><dt>Vendidos</dt><dd class="mono">{fmtNum(row.ml_volume, 0)}</dd></span>
              <span class="metric"><dt>Preço médio</dt><dd class="mono">{fmtMoney(row.ml_avg_price)}</dd></span>
            </div>
            <button class="tiny danger" type="button" on:click|stopPropagation={() => removeIdea(row.id)}>×</button>
          </div>
          {#if expanded === row.id}
            <div class="rank-body">
              <h4>Top 5 no Mercado Livre</h4>
              {#if row.top_listings.length === 0}
                <p class="muted">Nenhum listing coletado ainda. Tente "Atualizar agora".</p>
              {:else}
                <ul class="listings">
                  {#each row.top_listings as ln}
                    <li>
                      {#if ln.permalink}
                        <a href={ln.permalink} target="_blank" rel="noreferrer">{ln.title}</a>
                      {:else}
                        <span>{ln.title}</span>
                      {/if}
                      <span class="mono price">{fmtMoney(ln.price)}</span>
                      <span class="mono sold">· {fmtNum(ln.sold, 0)} vendidos</span>
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
          {/if}
        </article>
      {/each}
    </div>
  {/if}
</section>

<style>
  .page-head { margin-bottom: 1.5rem; }
  .page-head em { color: var(--brand); font-style: italic; }
  .banner {
    padding: 0.7rem 0.95rem;
    border: 1px solid var(--line-strong);
    margin-bottom: 1rem;
    background: var(--paper);
    font-size: 0.88rem;
  }
  .banner.ok { border-left: 4px solid var(--ok); }
  .banner.alert { border-left: 4px solid var(--danger); color: var(--danger); }
  .banner.inline { margin-top: 0.5rem; margin-bottom: 0; }
  .form-title {
    margin: 0;
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.25rem;
    letter-spacing: -0.01em;
  }
  .heading { display: flex; flex-direction: column; gap: 0.25rem; }
  .empty {
    padding: 1.5rem 1rem;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.78rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .empty-state {
    padding: 2.5rem 2rem;
    text-align: center;
    border: 1px dashed var(--line-strong);
  }
  .empty-state h3 {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.45rem;
    margin: 0.5rem 0;
    letter-spacing: -0.01em;
  }
  .empty-state p { color: var(--muted); max-width: 50ch; margin: 0 auto; }

  .rank-list { display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem; }
  .rank {
    border: 1px solid var(--line-strong);
    background: var(--paper);
  }
  .rank-head {
    display: grid;
    grid-template-columns: 36px 1fr 120px auto 30px;
    align-items: center;
    gap: 0.9rem;
    padding: 0.85rem 1rem;
    width: 100%;
    background: transparent;
    border: 0;
    cursor: pointer;
    text-align: left;
  }
  .rank-pos {
    font-size: 1.2rem;
    color: var(--muted);
  }
  .rank-term { display: flex; flex-direction: column; gap: 0.2rem; }
  .rank-term strong {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.05rem;
  }
  .rank-term .muted { color: var(--muted); font-size: 0.78rem; }
  .spark { width: 120px; height: 32px; color: var(--brand); }
  .metrics { display: flex; gap: 1.2rem; }
  .metric { display: flex; flex-direction: column; gap: 0.1rem; }
  .metric dt {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .metric dd { margin: 0; font-size: 0.95rem; }
  .metric dd.accent { color: var(--brand); font-weight: 500; }
  .rank-body {
    padding: 0.5rem 1.2rem 1rem;
    border-top: 1px dashed var(--line);
  }
  .rank-body h4 {
    margin: 0.6rem 0 0.4rem;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 500;
  }
  .listings {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .listings li {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 0.6rem;
    align-items: center;
    border-bottom: 1px dashed var(--line);
    padding-bottom: 0.35rem;
  }
  .listings a { color: var(--ink); text-decoration: none; }
  .listings a:hover { text-decoration: underline; }
  .listings .price { color: var(--brand); }
  .listings .sold { color: var(--muted); font-size: 0.78rem; }

  @media (max-width: 800px) {
    .rank-head { grid-template-columns: 32px 1fr 28px; gap: 0.6rem; }
    .spark, .metrics { grid-column: 1 / -1; }
    .metrics { padding-left: 44px; }
  }
</style>
