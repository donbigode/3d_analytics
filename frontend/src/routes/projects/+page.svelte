<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { requireAuth } from "$lib/guard";
  import {
    CATEGORY_LABEL,
    PROJECT_SITES,
    TIER_LABEL,
    type ProjectSite,
    type SiteCategory,
    type Tier,
  } from "$lib/data/project-sites";

  type Filter = "all" | SiteCategory;
  let filter: Filter = "all";
  let active: ProjectSite | null = null;
  let modelUrl = "";

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

  function openSite(s: ProjectSite) {
    active = s;
    modelUrl = "";
  }

  function closeModal() {
    active = null;
    modelUrl = "";
  }

  function createQuoteFromSite() {
    if (!active) return;
    const params = new URLSearchParams();
    if (modelUrl.trim()) {
      params.set("model_source_url", modelUrl.trim());
    }
    params.set("model_source_site", active.name);
    goto(`/quotes/new?${params.toString()}`);
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
    <button class="site-card" type="button" on:click={() => openSite(s)}>
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
      <ul class="materials">
        {#each s.recommended_materials as m}<li>{m}</li>{/each}
      </ul>
      <footer>
        <span class="mono url">{s.url.replace(/^https?:\/\//, "")}</span>
        <span class="arrow" aria-hidden="true">↗</span>
      </footer>
    </button>
  {/each}
</section>

{#if active}
  <div class="modal-backdrop" role="dialog" aria-modal="true" on:click={closeModal}>
    <div class="modal" on:click|stopPropagation>
      <header class="modal-head">
        <div>
          <span class="cat">{CATEGORY_LABEL[active.category]}</span>
          <h2>{active.name}</h2>
          <p class="tagline">{active.tagline}</p>
        </div>
        <button class="ghost" type="button" on:click={closeModal} aria-label="Fechar">×</button>
      </header>

      <p class="desc">{active.description}</p>

      <div class="modal-row">
        <span class="page-eyebrow">Materiais que combinam</span>
        <ul class="materials big">
          {#each active.recommended_materials as m}<li>{m}</li>{/each}
        </ul>
      </div>

      <div class="modal-row">
        <span class="page-eyebrow">Link do modelo (opcional)</span>
        <input
          type="url"
          bind:value={modelUrl}
          placeholder={`Cole aqui o link do modelo no ${active.name}`}
        />
        <small class="hint">Se preencher, vai pro orçamento como atribuição (cita autor + licença no PDF).</small>
      </div>

      <div class="modal-actions">
        <a class="ghost" href={active.url} target="_blank" rel="noreferrer noopener">
          Abrir {active.name} ↗
        </a>
        <button type="button" on:click={createQuoteFromSite}>
          Criar orçamento →
        </button>
      </div>
    </div>
  </div>
{/if}

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
    text-align: left;
    color: var(--ink);
    cursor: pointer;
    font: inherit;
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

  .materials {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }
  .materials li {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 0.08rem 0.4rem;
    background: var(--brand);
    color: var(--paper);
    border-radius: 2px;
  }
  .materials.big li { font-size: 0.78rem; padding: 0.2rem 0.55rem; }

  /* ----- modal ----- */
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(12, 12, 14, 0.55);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 50;
    padding: 1rem;
  }
  .modal {
    background: var(--paper);
    border: 1px solid var(--line-strong);
    padding: 1.4rem;
    max-width: 520px;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
  }
  .modal-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.6rem;
  }
  .modal-head h2 {
    margin: 0.2rem 0 0.2rem;
    font-family: var(--font-display);
    font-weight: 600;
    font-size: 1.4rem;
    letter-spacing: -0.01em;
  }
  .modal-head button.ghost {
    background: transparent;
    border: 1px solid var(--line);
    width: 32px;
    height: 32px;
    font-size: 1.2rem;
    cursor: pointer;
  }
  .modal-row {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .modal-row input[type="url"] {
    padding: 0.45rem 0.6rem;
    border: 1px solid var(--line);
    font: inherit;
  }
  .modal-row .hint { color: var(--muted); font-size: 0.78rem; }
  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .modal-actions .ghost {
    background: transparent;
    border: 1px solid var(--line-strong);
    padding: 0.5rem 0.85rem;
    text-decoration: none;
    color: var(--ink);
  }
  .modal-actions button {
    padding: 0.5rem 1rem;
    background: var(--brand);
    color: var(--paper);
    border: 1px solid var(--brand);
    cursor: pointer;
  }
</style>
