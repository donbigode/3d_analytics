<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type {
    KeywordIdea,
    LLMSuggestion,
    RankingRow,
    SourceMetric,
    SourceMetricsOut,
    SparkPoint,
  } from "$lib/types";

  let ideas: KeywordIdea[] = [];
  let ranking: RankingRow[] = [];
  let sources: SourceMetric[] = [];
  let suggestions: LLMSuggestion[] = [];
  let loading = true;
  let listError = "";

  let llmRefreshing = false;
  let llmBanner = "";
  let actingSuggestion: string | null = null;
  let promotingAll = false;

  type Window = "day" | "week" | "month" | "all";
  let activeWindow: Window = "all";

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
      const [i, r, s, su] = await Promise.all([
        api<KeywordIdea[]>("/trends/ideas"),
        api<RankingRow[]>("/trends/ranking"),
        api<SourceMetricsOut>("/trends/sources"),
        api<LLMSuggestion[]>("/trends/suggestions?status=pending"),
      ]);
      ideas = i;
      ranking = r;
      sources = s.sources;
      suggestions = su;
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

  async function llmRefreshNow() {
    llmRefreshing = true;
    llmBanner = "";
    try {
      const res = await api<{ status: string; items_created: number; error: string | null }>(
        "/trends/llm-refresh",
        { method: "POST" },
      );
      llmBanner = res.status === "error"
        ? `Falhou: ${res.error}`
        : `LLM gerou ${res.items_created} sugest${res.items_created === 1 ? "ão" : "ões"}.`;
      await load();
    } catch (err) {
      handleApiError(err);
      llmBanner = errorMessage(err, "Falha na coleta LLM.");
    } finally {
      llmRefreshing = false;
    }
  }

  async function promoteSuggestion(id: string) {
    actingSuggestion = id;
    try {
      await api(`/trends/suggestions/${id}/promote`, { method: "POST" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao promover sugestão.");
    } finally {
      actingSuggestion = null;
    }
  }

  async function promoteAllSuggestions() {
    if (suggestions.length === 0) return;
    if (!confirm(`Promover todas as ${suggestions.length} sugestões pendentes?`)) return;
    promotingAll = true;
    llmBanner = "";
    try {
      const res = await api<{ promoted: number }>("/trends/suggestions/promote-all", {
        method: "POST",
      });
      llmBanner = `${res.promoted} sugest${res.promoted === 1 ? "ão promovida" : "ões promovidas"}.`;
      await load();
    } catch (err) {
      handleApiError(err);
      llmBanner = errorMessage(err, "Falha ao promover sugestões.");
    } finally {
      promotingAll = false;
    }
  }

  async function dismissSuggestion(id: string) {
    actingSuggestion = id;
    try {
      await api(`/trends/suggestions/${id}/dismiss`, { method: "POST" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao descartar sugestão.");
    } finally {
      actingSuggestion = null;
    }
  }

  function fmtRelative(s: string | null): string {
    if (!s) return "—";
    const t = new Date(s).getTime();
    const diff = Math.max(0, Date.now() - t);
    if (diff < 60_000) return "agora";
    if (diff < 3600_000) return `há ${Math.floor(diff / 60_000)}min`;
    if (diff < 86400_000) return `há ${Math.floor(diff / 3600_000)}h`;
    return `há ${Math.floor(diff / 86400_000)}d`;
  }

  function sourceLabel(s: string): string {
    return ({
      google_trends: "Google Trends",
      mercadolivre: "Mercado Livre",
      wikipedia: "Wikipedia (PT-BR)",
      reddit: "Reddit (sem auth)",
      anthropic: "Anthropic Claude",
      gemini: "Google Gemini",
      openai: "OpenAI GPT",
      llm: "Coleta LLM (job)",
    } as Record<string, string>)[s] || s;
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

  function windowLabel(w: string): string {
    return ({ day: "Diário", week: "Semanal", month: "Mensal" } as Record<string, string>)[w] || w;
  }
  function providerLabel(p: string | null | undefined): string {
    if (!p) return "Manual";
    return ({
      anthropic: "Claude",
      gemini: "Gemini",
      openai: "GPT",
    } as Record<string, string>)[p] || p;
  }

  $: filteredRanking = ranking.filter((r) =>
    activeWindow === "all" ? true : r.temporal_window === activeWindow,
  );
  $: windowCounts = ranking.reduce(
    (acc, r) => {
      acc[r.temporal_window] = (acc[r.temporal_window] ?? 0) + 1;
      return acc;
    },
    { day: 0, week: 0, month: 0 } as Record<string, number>,
  );

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
{#if llmBanner}<div class="banner ok">{llmBanner}</div>{/if}

<section class="panel actions-panel">
  <div class="panel-head">
    <div class="heading">
      <span class="page-eyebrow">Ações</span>
      <h2 class="form-title">Disparar coleta</h2>
    </div>
  </div>
  <div class="action-grid">
    <button class="big-action llm" on:click={llmRefreshNow} disabled={llmRefreshing}>
      <span class="big-action-eyebrow">LLM</span>
      <span class="big-action-title">Buscar tendências com IA</span>
      <span class="big-action-hint">
        {llmRefreshing ? "Coletando…" : "Pede 10 candidatos (Claude ou Gemini) com janela dia/semana/mês"}
      </span>
    </button>
    <button class="big-action coll" on:click={refreshNow} disabled={refreshing}>
      <span class="big-action-eyebrow">Coleta</span>
      <span class="big-action-title">Google Trends + Mercado Livre</span>
      <span class="big-action-hint">
        {refreshing ? "Coletando…" : "Refaz observações de TODOS os termos cadastrados"}
      </span>
    </button>
    <button
      class="big-action promote"
      on:click={promoteAllSuggestions}
      disabled={promotingAll || suggestions.length === 0}
    >
      <span class="big-action-eyebrow">Inbox</span>
      <span class="big-action-title">
        Adicionar {suggestions.length} sugest{suggestions.length === 1 ? "ão" : "ões"} ao radar
      </span>
      <span class="big-action-hint">
        {promotingAll
          ? "Promovendo…"
          : suggestions.length === 0
            ? "Nenhuma sugestão pendente"
            : "Promove todas e dispara coleta no próximo ciclo"}
      </span>
    </button>
  </div>
</section>

<section class="panel sources-panel">
  <div class="panel-head">
    <div class="heading">
      <span class="page-eyebrow">Fontes de dados</span>
      <h2 class="form-title">Status das integrações</h2>
    </div>
    <a class="tiny ghost" href="/config">Gerenciar chaves →</a>
  </div>
  <div class="source-grid">
    {#each sources as src (src.source)}
      <article class="src" class:off={!src.enabled}>
        <header>
          <span class="src-name">{sourceLabel(src.source)}</span>
          <span class="dot" class:on={src.enabled} aria-hidden="true"></span>
        </header>
        <dl>
          <dt>Última</dt>
          <dd class="mono">
            {fmtRelative(src.last_run_at)}
            {#if src.last_status}<span class="status-tag {src.last_status}">{src.last_status}</span>{/if}
          </dd>
          <dt>Itens 24h</dt>
          <dd class="mono">{src.items_created_24h}</dd>
          <dt>Execuções 24h</dt>
          <dd class="mono">{src.runs_24h}</dd>
          <dt>Erros 7d</dt>
          <dd class="mono">{src.errors_7d}</dd>
        </dl>
        {#if src.last_error}
          <p class="src-error" title={src.last_error}>{src.last_error}</p>
        {/if}
      </article>
    {/each}
  </div>
</section>

{#if suggestions.length > 0 || llmBanner}
  <section class="panel">
    <div class="panel-head">
      <div class="heading">
        <span class="page-eyebrow">Inbox de sugestões</span>
        <h2 class="form-title">Sugestões do LLM ({suggestions.length} pendentes)</h2>
      </div>
      <button class="tiny ghost" on:click={llmRefreshNow} disabled={llmRefreshing}>
        {llmRefreshing ? "Coletando…" : "Coletar agora"}
      </button>
    </div>
    {#if suggestions.length === 0}
      <p class="empty">Nenhuma sugestão pendente. Auto-promovidas viraram termos direto.</p>
    {:else}
      <div class="suggestion-list">
        {#each suggestions as s (s.id)}
          <article class="suggestion">
            <header>
              <strong>{s.term}</strong>
              <div class="suggestion-tags">
                {#if s.temporal_window}
                  <span class="badge window {s.temporal_window}">{windowLabel(s.temporal_window)}</span>
                {/if}
                <span class="badge provider {s.provider}">{providerLabel(s.provider)}</span>
              </div>
            </header>
            {#if s.rationale}<p class="rationale">{s.rationale}</p>{/if}
            <footer>
              <span class="mono recurrence">recorrência {Number(s.recurrence_score).toFixed(2)}</span>
              <div class="actions">
                <button class="tiny ghost" on:click={() => dismissSuggestion(s.id)} disabled={actingSuggestion === s.id}>
                  Descartar
                </button>
                <button class="tiny" on:click={() => promoteSuggestion(s.id)} disabled={actingSuggestion === s.id}>
                  {actingSuggestion === s.id ? "Promovendo…" : "Adicionar ao radar"}
                </button>
              </div>
            </footer>
          </article>
        {/each}
      </div>
    {/if}
  </section>
{/if}

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
    <div class="tabs">
      <button class="tab" class:active={activeWindow === "all"} on:click={() => (activeWindow = "all")}>
        Todos <span class="count">· {ranking.length}</span>
      </button>
      <button class="tab" class:active={activeWindow === "day"} on:click={() => (activeWindow = "day")}>
        Diário <span class="count">· {windowCounts.day}</span>
      </button>
      <button class="tab" class:active={activeWindow === "week"} on:click={() => (activeWindow = "week")}>
        Semanal <span class="count">· {windowCounts.week}</span>
      </button>
      <button class="tab" class:active={activeWindow === "month"} on:click={() => (activeWindow = "month")}>
        Mensal <span class="count">· {windowCounts.month}</span>
      </button>
    </div>
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
  {:else if filteredRanking.length === 0}
    <p class="empty">Nenhum termo nessa janela.</p>
  {:else}
    <div class="rank-list">
      {#each filteredRanking as row, i (row.id)}
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
              <div class="row-meta">
                <span class="badge window {row.temporal_window}">{windowLabel(row.temporal_window)}</span>
                <span class="badge provider {row.source_provider ?? 'manual'}">{providerLabel(row.source_provider)}</span>
                <span class="muted">{row.top_listings.length} listings · clique para detalhar</span>
              </div>
            </div>
            <svg class="spark" viewBox="0 0 120 32" preserveAspectRatio="none" aria-hidden="true">
              <path d={sparkPath(row.sparkline)} fill="none" stroke="currentColor" stroke-width="1.5" />
            </svg>
            <div class="metrics">
              <span class="metric"><dt>Score</dt><dd class="mono accent">{fmtNum(row.score, 1)}</dd></span>
              <span class="metric"><dt>Interesse</dt><dd class="mono">{fmtNum(row.interest, 0)}</dd></span>
              <span class="metric"><dt>Wiki/dia</dt><dd class="mono">{fmtNum(row.wiki_views, 0)}</dd></span>
              <span class="metric"><dt>Vendidos</dt><dd class="mono">{fmtNum(row.ml_volume, 0)}</dd></span>
              <span class="metric"><dt>Preço médio</dt><dd class="mono">{fmtMoney(row.ml_avg_price)}</dd></span>
              <span class="metric"><dt>Reddit ⬆</dt><dd class="mono">{fmtNum(row.reddit_score, 0)}</dd></span>
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

              {#if row.top_reddit_posts && row.top_reddit_posts.length > 0}
                <h4>Top no Reddit</h4>
                <ul class="reddit-posts">
                  {#each row.top_reddit_posts as p}
                    <li>
                      {#if p.permalink}
                        <a href={p.permalink} target="_blank" rel="noreferrer">{p.title}</a>
                      {:else}
                        <span>{p.title}</span>
                      {/if}
                      <span class="mono sub">r/{p.subreddit}</span>
                      <span class="mono votes">⬆ {fmtNum(p.score, 0)} · 💬 {fmtNum(p.comments, 0)}</span>
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

  .reddit-posts {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .reddit-posts li {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 0.6rem;
    align-items: center;
    border-bottom: 1px dashed var(--line);
    padding-bottom: 0.35rem;
  }
  .reddit-posts a { color: var(--ink); text-decoration: none; }
  .reddit-posts a:hover { text-decoration: underline; }
  .reddit-posts .sub { color: var(--brand); font-size: 0.78rem; }
  .reddit-posts .votes { color: var(--muted); font-size: 0.78rem; }

  @media (max-width: 800px) {
    .rank-head { grid-template-columns: 32px 1fr 28px; gap: 0.6rem; }
    .spark, .metrics { grid-column: 1 / -1; }
    .metrics { padding-left: 44px; }
  }

  /* --------- sources panel --------- */
  .sources-panel { margin-bottom: 1.5rem; }
  .source-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 0.7rem;
    margin-top: 0.6rem;
  }
  .src {
    border: 1px solid var(--line);
    padding: 0.7rem 0.9rem;
    background: var(--paper);
  }
  .src.off { opacity: 0.55; }
  .src header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.4rem;
  }
  .src-name {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 0.95rem;
    letter-spacing: -0.005em;
  }
  .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--muted);
  }
  .dot.on { background: var(--ok); }
  .src dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.18rem 0.7rem;
    margin: 0;
  }
  .src dt {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .src dd { margin: 0; font-size: 0.78rem; }
  .status-tag {
    margin-left: 0.4rem;
    font-family: var(--font-mono);
    font-size: 0.6rem;
    padding: 0.05rem 0.3rem;
    border: 1px solid var(--line-strong);
  }
  .status-tag.success { color: var(--ok); border-color: var(--ok); }
  .status-tag.error { color: var(--danger); border-color: var(--danger); }
  .status-tag.running { color: var(--brand); border-color: var(--brand); }
  .src-error {
    margin: 0.5rem 0 0;
    padding: 0.35rem 0.5rem;
    border: 1px solid var(--danger);
    border-left-width: 3px;
    background: #fff1f0;
    color: var(--danger);
    font-size: 0.72rem;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  /* --------- suggestions --------- */
  .suggestion-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .suggestion {
    border: 1px solid var(--line-strong);
    padding: 0.85rem 1rem;
    background: var(--paper);
  }
  .suggestion header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.6rem;
  }
  .suggestion strong {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.05rem;
  }
  .suggestion .provider {
    font-size: 0.62rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid var(--line);
    padding: 0.05rem 0.35rem;
  }
  .rationale {
    color: var(--muted);
    font-size: 0.88rem;
    margin: 0.35rem 0 0.5rem;
  }
  .suggestion footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 1px dashed var(--line);
    padding-top: 0.5rem;
    margin-top: 0.3rem;
  }
  .recurrence {
    font-size: 0.7rem;
    color: var(--muted);
    letter-spacing: 0.06em;
  }

  /* ----- prominent action buttons ----- */
  .actions-panel { margin-bottom: 1.5rem; }
  .action-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 0.7rem;
    margin-top: 0.6rem;
  }
  .big-action {
    text-align: left;
    background: var(--paper);
    border: 1px solid var(--line-strong);
    padding: 0.95rem 1.05rem;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    transition: background 120ms, border-color 120ms, transform 120ms;
  }
  .big-action:hover:not(:disabled) {
    background: var(--bg);
    border-color: var(--ink);
  }
  .big-action:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .big-action-eyebrow {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .big-action-title {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.05rem;
    letter-spacing: -0.005em;
    line-height: 1.2;
  }
  .big-action-hint {
    font-size: 0.78rem;
    color: var(--muted);
  }
  .big-action.llm { border-left: 4px solid var(--brand); }
  .big-action.coll { border-left: 4px solid var(--ok); }
  .big-action.promote { border-left: 4px solid #c08400; }

  /* ----- temporal tabs ----- */
  .tabs { display: inline-flex; gap: 0.25rem; }
  .tab {
    background: transparent;
    border: 1px solid var(--line);
    padding: 0.3rem 0.65rem;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    cursor: pointer;
  }
  .tab:hover { color: var(--ink); border-color: var(--line-strong); }
  .tab.active {
    background: var(--brand);
    color: var(--paper);
    border-color: var(--brand);
  }
  .tab .count { color: inherit; opacity: 0.65; }

  /* ----- badges (window + provider) ----- */
  .row-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
    margin-top: 0.2rem;
  }
  .suggestion-tags { display: inline-flex; gap: 0.35rem; }
  .badge {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    padding: 0.05rem 0.4rem;
    border: 1px solid var(--line-strong);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .badge.window.day { color: var(--danger); border-color: var(--danger); }
  .badge.window.week { color: var(--brand); border-color: var(--brand); }
  .badge.window.month { color: var(--ok); border-color: var(--ok); }
  .badge.provider.anthropic { background: #fef3c7; color: #92400e; border-color: #92400e; }
  .badge.provider.gemini { background: #dbeafe; color: #1e3a8a; border-color: #1e3a8a; }
  .badge.provider.openai { background: #dcfce7; color: #166534; border-color: #166534; }
  .badge.provider.manual { color: var(--muted); border-color: var(--line); }
</style>
