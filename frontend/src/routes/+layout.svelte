<script lang="ts">
  import "../app.css";
  import { page } from "$app/stores";
  import { appSettings } from "$lib/stores/settings";
  import { user } from "$lib/stores/user";
  import { brandName, brandTagline, brandColor, brandLogoUrl } from "$lib/branding";
  import { api } from "$lib/api";
  import { goto } from "$app/navigation";

  $: settings = $appSettings;
  $: name = brandName(settings);
  $: tagline = brandTagline(settings);
  $: color = brandColor(settings);
  $: logo = brandLogoUrl(settings);
  $: path = $page.url.pathname;

  const nav = [
    { href: "/", label: "Dashboard", match: (p: string) => p === "/" },
    { href: "/quotes", label: "Orçamentos", match: (p: string) => p.startsWith("/quotes") },
    { href: "/clients", label: "Clientes", match: (p: string) => p.startsWith("/clients") },
    { href: "/materials", label: "Materiais", match: (p: string) => p.startsWith("/materials") },
    { href: "/services", label: "Serviços", match: (p: string) => p.startsWith("/services") },
    { href: "/spools", label: "Estoque", match: (p: string) => p.startsWith("/spools") },
    { href: "/insights", label: "Insights", match: (p: string) => p.startsWith("/insights") },
    { href: "/capacity", label: "Capacidade", match: (p: string) => p.startsWith("/capacity") },
    { href: "/trends", label: "Tendências", match: (p: string) => p.startsWith("/trends") },
    { href: "/settings", label: "Ajustes", match: (p: string) => p.startsWith("/settings") },
  ];

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    user.set(null);
    goto("/login");
  }
</script>

<svelte:head>
  <title>{name}</title>
</svelte:head>

<div class="shell" style:--brand={color}>
  <header class="masthead">
    <a class="brand" href="/">
      {#if logo}
        <img src={logo} alt="" />
      {:else}
        <span class="brand-mark" aria-hidden="true">◣◢</span>
      {/if}
      <span class="brand-text">
        <span class="brand-name">{name}</span>
        {#if tagline}<span class="brand-tag">{tagline}</span>{/if}
      </span>
    </a>

    {#if $user}
      <nav class="primary-nav" aria-label="Principal">
        {#each nav as item}
          <a href={item.href} class:active={item.match(path)}>{item.label}</a>
        {/each}
      </nav>
      <div class="user-pod">
        <span class="who">{$user.name}</span>
        <button class="tiny ghost" on:click={logout}>Sair</button>
      </div>
    {:else}
      <nav class="primary-nav" aria-label="Principal">
        <a href="/login" class:active={path.startsWith("/login")}>Entrar</a>
      </nav>
    {/if}
  </header>

  <main>
    <slot />
  </main>

  <footer class="coda">
    <span class="mono">{name}</span>
    <span class="dots">· · ·</span>
    <span class="mono muted">Orçamento &amp; analítico · MVP</span>
  </footer>
</div>

<style>
  .shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .masthead {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 2rem;
    padding: 1.1rem 1.5rem;
    border-bottom: 1px solid var(--line-strong);
    background: var(--paper);
    position: sticky;
    top: 0;
    z-index: 20;
    backdrop-filter: saturate(140%) blur(6px);
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 0.65rem;
    text-decoration: none;
    color: var(--ink);
  }
  .brand img {
    height: 36px;
    width: auto;
    display: block;
  }
  .brand-mark {
    display: inline-block;
    width: 36px;
    height: 36px;
    line-height: 36px;
    text-align: center;
    background: var(--brand);
    color: #fff;
    font-family: var(--font-mono);
    font-size: 0.9rem;
    letter-spacing: -0.05em;
  }
  .brand-text {
    display: flex;
    flex-direction: column;
    line-height: 1.05;
  }
  .brand-name {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.15rem;
    letter-spacing: -0.01em;
  }
  .brand-tag {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--muted);
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }
  .primary-nav {
    display: flex;
    gap: 0.25rem;
    justify-content: center;
    flex-wrap: wrap;
  }
  .primary-nav a {
    text-decoration: none;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 0.45rem 0.7rem;
    border: 1px solid transparent;
    transition: color 120ms, border-color 120ms, background 120ms;
  }
  .primary-nav a:hover {
    color: var(--ink);
  }
  .primary-nav a.active {
    color: var(--ink);
    border-color: var(--ink);
    background: var(--paper);
  }
  .user-pod {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
  }
  .who {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--muted);
    letter-spacing: 0.06em;
  }
  main {
    flex: 1;
  }
  .coda {
    border-top: 1px dashed var(--line);
    padding: 1.4rem 1.5rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.78rem;
    display: flex;
    justify-content: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .coda .dots {
    letter-spacing: 0.2em;
    color: var(--brand);
  }
  .coda .muted {
    color: var(--muted);
  }
  @media (max-width: 760px) {
    .masthead {
      grid-template-columns: 1fr auto;
      gap: 0.6rem;
    }
    .primary-nav {
      grid-column: 1 / -1;
      justify-content: flex-start;
    }
  }
</style>
