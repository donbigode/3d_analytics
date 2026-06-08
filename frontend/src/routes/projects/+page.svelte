<script lang="ts">
  import { onMount } from "svelte";
  import { requireAuth } from "$lib/guard";
  import {
    CATEGORY_LABEL,
    PROJECT_SITES,
    TIER_LABEL,
    type SiteCategory,
    type Tier,
  } from "$lib/data/project-sites";

  type Filter = "all" | SiteCategory;
  let filter: Filter = "all";

  $: filtered = filter === "all"
    ? PROJECT_SITES
    : PROJECT_SITES.filter((s) => s.category === filter);

  $: counts = PROJECT_SITES.reduce(
    (acc, s) => {
      acc[s.category] = (acc[s.category] ?? 0) + 1;
      return acc;
    },
    {} as Record<SiteCategory, number>,
  );

  function tierClass(t: Tier): string {
    return ({ free: "tier-free", freemium: "tier-mid", paid: "tier-paid" })[t];
  }

  onMount(() => {
    requireAuth();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Recursos / 10 · diretório</span>
  <h1 class="page-title">Sites de modelos<em>.</em></h1>
  <p class="page-lede">
    Catálogo curado dos lugares onde a maioria dos modelos 3D vive — comunidades
    grátis, marketplaces pagos e bibliotecas de engenharia. Clique no card pra
    abrir o site em nova aba.
  </p>
</header>

<section class="panel toolbar">
  <div class="panel-head">
    <span class="page-eyebrow">Filtrar por categoria</span>
  </div>
  <div class="tabs">
    <button class="tab" class:active={filter === "all"} on:click={() => (filter = "all")}>
      Todos <span class="count">· {PROJECT_SITES.length}</span>
    </button>
    {#each Object.entries(CATEGORY_LABEL) as [key, label]}
      {@const cat = key as SiteCategory}
      <button class="tab" class:active={filter === cat} on:click={() => (filter = cat)}>
        {label} <span class="count">· {counts[cat] ?? 0}</span>
      </button>
    {/each}
  </div>
</section>

<section class="grid">
  {#each filtered as s (s.slug)}
    <a class="site-card" href={s.url} target="_blank" rel="noreferrer noopener">
      <header>
        <div class="title-row">
          <h3>{s.name}</h3>
          <span class="tier {tierClass(s.tier)}">{TIER_LABEL[s.tier]}</span>
        </div>
        <span class="cat">{CATEGORY_LABEL[s.category]}</span>
        {#if s.ecosystem}<span class="eco">· {s.ecosystem}</span>{/if}
      </header>
      <p class="tagline">{s.tagline}</p>
      <p class="desc">{s.description}</p>
      <ul class="highlights">
        {#each s.highlights as h}<li>{h}</li>{/each}
      </ul>
      <footer>
        <span class="mono url">{s.url.replace(/^https?:\/\//, "")}</span>
        <span class="arrow" aria-hidden="true">↗</span>
      </footer>
    </a>
  {/each}
</section>

<style>
  .page-head { margin-bottom: 1.5rem; }
  .page-head em { color: var(--brand); font-style: italic; }
  .toolbar { margin-bottom: 1.5rem; }
  .tabs { display: inline-flex; gap: 0.25rem; flex-wrap: wrap; margin-top: 0.4rem; }
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
  .tab .count { color: inherit; opacity: 0.7; }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1rem;
  }

  .site-card {
    background: var(--paper);
    border: 1px solid var(--line-strong);
    padding: 1.1rem 1.2rem;
    text-decoration: none;
    color: var(--ink);
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
    transition: transform 120ms, border-color 120ms, background 120ms;
  }
  .site-card:hover {
    border-color: var(--ink);
    transform: translateY(-1px);
    background: var(--bg);
  }
  .site-card header { display: flex; flex-direction: column; gap: 0.2rem; }
  .title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .title-row h3 {
    margin: 0;
    font-family: var(--font-display);
    font-weight: 600;
    font-size: 1.2rem;
    letter-spacing: -0.01em;
  }
  .tier {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    padding: 0.1rem 0.4rem;
    border: 1px solid var(--line-strong);
  }
  .tier-free { color: var(--ok); border-color: var(--ok); }
  .tier-mid { color: #c08400; border-color: #c08400; }
  .tier-paid { color: var(--danger); border-color: var(--danger); }
  .cat, .eco {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .tagline {
    margin: 0;
    font-family: var(--font-display);
    font-style: italic;
    color: var(--ink);
    font-size: 0.95rem;
  }
  .desc {
    margin: 0;
    color: var(--muted);
    font-size: 0.85rem;
    line-height: 1.4;
  }
  .highlights {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
  }
  .highlights li {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    letter-spacing: 0.06em;
    padding: 0.1rem 0.45rem;
    background: var(--bg);
    border: 1px dashed var(--line);
    color: var(--muted);
  }
  .site-card footer {
    border-top: 1px dashed var(--line);
    padding-top: 0.5rem;
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .url { color: var(--muted); font-size: 0.72rem; }
  .arrow {
    font-family: var(--font-mono);
    color: var(--brand);
    font-size: 1.05rem;
  }
</style>
