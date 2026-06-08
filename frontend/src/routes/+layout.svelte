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

  type NavItem = { href: string; label: string; match: (p: string) => boolean };
  type NavGroup = { label: string; items: NavItem[] };

  const groups: NavGroup[] = [
    {
      label: "Operação",
      items: [
        { href: "/", label: "Dashboard", match: (p) => p === "/" },
        { href: "/quotes", label: "Orçamentos", match: (p) => p.startsWith("/quotes") },
        { href: "/inbox", label: "Inbox", match: (p) => p.startsWith("/inbox") },
        { href: "/capacity", label: "Capacidade", match: (p) => p.startsWith("/capacity") },
      ],
    },
    {
      label: "Cadastros",
      items: [
        { href: "/clients", label: "Clientes", match: (p) => p.startsWith("/clients") },
        { href: "/materials", label: "Materiais", match: (p) => p.startsWith("/materials") },
        { href: "/services", label: "Serviços", match: (p) => p.startsWith("/services") },
        { href: "/spools", label: "Estoque", match: (p) => p.startsWith("/spools") },
      ],
    },
    {
      label: "Inteligência",
      items: [
        { href: "/insights", label: "Insights", match: (p) => p.startsWith("/insights") },
        { href: "/trends", label: "Tendências", match: (p) => p.startsWith("/trends") },
      ],
    },
    {
      label: "Recursos",
      items: [
        { href: "/library", label: "Biblioteca", match: (p) => p.startsWith("/library") },
        { href: "/projects", label: "Sites de modelos", match: (p) => p.startsWith("/projects") },
      ],
    },
    {
      label: "Configuração",
      items: [
        { href: "/settings", label: "Ajustes", match: (p) => p.startsWith("/settings") },
        { href: "/config", label: "Integrações", match: (p) => p.startsWith("/config") },
      ],
    },
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

<div class="shell" style:--brand={color} class:authed={!!$user}>
  {#if $user}
    <aside class="side" aria-label="Navegação principal">
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

      <nav class="groups">
        {#each groups as group}
          <div class="group">
            <h2 class="group-label">{group.label}</h2>
            <div class="group-items">
              {#each group.items as item}
                <a href={item.href} class:active={item.match(path)}>{item.label}</a>
              {/each}
            </div>
          </div>
        {/each}
      </nav>

      <div class="user-pod">
        <span class="who">{$user.name}</span>
        <button class="tiny ghost" on:click={logout}>Sair</button>
      </div>
    </aside>
  {:else}
    <header class="masthead-anon">
      <a class="brand" href="/">
        {#if logo}<img src={logo} alt="" />{:else}<span class="brand-mark">◣◢</span>{/if}
        <span class="brand-name">{name}</span>
      </a>
      <a href="/login" class:active={path.startsWith("/login")} class="login-link">Entrar</a>
    </header>
  {/if}

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
  .shell.authed {
    display: grid;
    grid-template-columns: 240px 1fr;
    grid-template-rows: 1fr auto;
    grid-template-areas:
      "side main"
      "side footer";
  }
  .shell.authed > main { grid-area: main; }
  .shell.authed > .coda { grid-area: footer; }

  /* ---------- sidebar ---------- */
  .side {
    grid-area: side;
    background: var(--paper);
    border-right: 1px solid var(--line-strong);
    padding: 1.2rem 0.9rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 1.2rem;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
  }
  .brand {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    text-decoration: none;
    color: var(--ink);
    padding: 0 0.25rem;
  }
  .brand img { height: 36px; width: auto; display: block; }
  .brand-mark {
    display: inline-block;
    width: 36px; height: 36px; line-height: 36px;
    text-align: center;
    background: var(--brand);
    color: #fff;
    font-family: var(--font-mono);
    font-size: 0.9rem;
    letter-spacing: -0.05em;
  }
  .brand-text { display: flex; flex-direction: column; line-height: 1.05; }
  .brand-name {
    font-family: var(--font-display);
    font-weight: 600;
    font-size: 1.05rem;
    letter-spacing: -0.01em;
  }
  .brand-tag {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--muted);
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }

  .groups {
    display: flex;
    flex-direction: column;
    gap: 1.1rem;
    margin-top: 0.4rem;
  }
  .group { display: flex; flex-direction: column; gap: 0.45rem; }
  .group-label {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 500;
    margin: 0 0 0 0.25rem;
  }
  .group-items {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }
  .group-items a {
    text-decoration: none;
    font-family: var(--font-sans);
    font-size: 0.78rem;
    letter-spacing: 0.04em;
    color: var(--muted);
    padding: 0.32rem 0.55rem;
    border: 1px solid var(--line);
    border-radius: 2px;
    background: transparent;
    transition: color 120ms, border-color 120ms, background 120ms;
    white-space: nowrap;
  }
  .group-items a:hover {
    color: var(--ink);
    border-color: var(--line-strong);
  }
  .group-items a.active {
    color: var(--paper);
    background: var(--brand);
    border-color: var(--brand);
  }

  .user-pod {
    margin-top: auto;
    padding-top: 0.8rem;
    border-top: 1px dashed var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .who {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--muted);
    letter-spacing: 0.06em;
  }

  /* ---------- anon masthead (login screen) ---------- */
  .masthead-anon {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--line-strong);
    background: var(--paper);
  }
  .login-link {
    text-decoration: none;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }

  main { padding: 1.2rem 1.5rem; }

  .coda {
    border-top: 1px dashed var(--line);
    padding: 1rem 1.5rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.78rem;
    display: flex;
    justify-content: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .coda .dots { letter-spacing: 0.2em; color: var(--brand); }
  .coda .muted { color: var(--muted); }

  /* ---------- responsive: drop sidebar on small viewports ---------- */
  @media (max-width: 880px) {
    .shell.authed {
      grid-template-columns: 1fr;
      grid-template-areas:
        "side"
        "main"
        "footer";
    }
    .side {
      position: relative;
      height: auto;
      border-right: 0;
      border-bottom: 1px solid var(--line-strong);
      flex-direction: column;
    }
    .groups { flex-direction: row; flex-wrap: wrap; }
    .group { min-width: 160px; }
  }
</style>
