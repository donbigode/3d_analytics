<script lang="ts">
  import "../app.css";
  import { appSettings } from "$lib/stores/settings";
  import { user } from "$lib/stores/user";
  import {
    brandName,
    brandColor,
    brandLogoUrl,
  } from "$lib/branding";

  $: settings = $appSettings;
  $: name = brandName(settings);
  $: color = brandColor(settings);
  $: logo = brandLogoUrl(settings);
</script>

<header style:--brand={color}>
  <div class="brand">
    {#if logo}
      <img src={logo} alt="logo" />
    {/if}
    <span>{name}</span>
  </div>
  <nav>
    {#if $user}
      <a href="/">Dashboard</a>
      <a href="/quotes">Orçamentos</a>
      <a href="/clients">Clientes</a>
      <a href="/materials">Materiais</a>
      <a href="/spools">Estoque</a>
      <a href="/settings">Ajustes</a>
    {:else}
      <a href="/login">Entrar</a>
    {/if}
  </nav>
</header>

<main><slot /></main>

<style>
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--brand);
    color: white;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
  }
  .brand img {
    height: 28px;
  }
  nav a {
    color: white;
    margin-right: 1rem;
    text-decoration: none;
  }
  nav a:last-child {
    margin-right: 0;
  }
</style>
