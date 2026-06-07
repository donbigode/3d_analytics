<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { Client, Quote, QuoteKind } from "$lib/types";

  let kind: QuoteKind = "commercial";
  let clientId = "";
  let clients: Client[] = [];
  let markup = 50;
  let minCharge = 0;
  let notes = "";

  let submitting = false;
  let error = "";

  async function loadClients() {
    try {
      clients = await api<Client[]>("/clients");
    } catch (err) {
      handleApiError(err);
    }
  }

  async function create() {
    error = "";
    submitting = true;
    try {
      const body: Record<string, unknown> = {
        kind,
        client_id: kind === "commercial" && clientId ? clientId : null,
        notes: notes || null,
      };
      if (kind === "commercial") {
        body.markup_pct = markup;
        body.min_charge = minCharge;
      } else {
        body.markup_pct = 0;
        body.min_charge = 0;
      }
      const q = await api<Quote>("/quotes", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      goto(`/quotes/${q.id}`);
    } catch (err) {
      handleApiError(err);
      error = errorMessage(err, "Não foi possível criar o orçamento.");
    } finally {
      submitting = false;
    }
  }

  onMount(() => {
    if (requireAuth()) return;
    loadClients();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Operação / 02 · Novo</span>
  <h1 class="page-title">Novo orçamento<em>.</em></h1>
  <p class="page-lede">
    Selecione o tipo do orçamento. Em comercial defina o cliente, markup e o
    valor mínimo; em pessoal o documento será uma ficha de custo sem preço de
    venda.
  </p>
</header>

<form class="panel" on:submit|preventDefault={create}>
  <div class="panel-head">
    <div class="heading">
      <span class="page-eyebrow">Início do fluxo</span>
      <h2 class="form-title">Configurar rascunho</h2>
    </div>
    <a href="/quotes" class="tiny ghost btn">voltar</a>
  </div>

  {#if error}<div class="alert">{error}</div>{/if}

  <div class="kind-row">
    <label class="kind-card" class:active={kind === "commercial"}>
      <input type="radio" bind:group={kind} value="commercial" />
      <span class="tag brand">comercial</span>
      <span class="kind-text">Para clientes — gera preço final com markup.</span>
    </label>
    <label class="kind-card" class:active={kind === "personal"}>
      <input type="radio" bind:group={kind} value="personal" />
      <span class="tag muted">pessoal</span>
      <span class="kind-text">Custo interno — sem preço de venda, ficha de custo.</span>
    </label>
  </div>

  <div class="form-grid">
    {#if kind === "commercial"}
      <label class="field">
        Cliente
        <select bind:value={clientId}>
          <option value="">— sem cliente —</option>
          {#each clients as c}
            <option value={c.id}>{c.name}</option>
          {/each}
        </select>
      </label>
      <label class="field">
        Markup (%)
        <input type="number" bind:value={markup} min="0" step="0.01" />
      </label>
      <label class="field">
        Cobrança mínima
        <input type="number" bind:value={minCharge} min="0" step="0.01" />
      </label>
    {/if}
    <label class="field full">
      Notas
      <input bind:value={notes} placeholder="Observações internas (opcional)" />
    </label>
    <div class="actions">
      <a href="/quotes" class="ghost btn">Cancelar</a>
      <button type="submit" disabled={submitting}>
        {submitting ? "Criando…" : "Criar rascunho"}
      </button>
    </div>
  </div>
</form>

<style>
  .page-head {
    margin-bottom: 2rem;
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
  a.btn {
    text-decoration: none;
    display: inline-block;
  }
  .kind-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 0.9rem;
    margin-bottom: 1.25rem;
  }
  .kind-card {
    border: 1px solid var(--line);
    padding: 0.95rem;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
    transition: border-color 120ms;
    background: var(--paper);
  }
  .kind-card:hover {
    border-color: var(--ink);
  }
  .kind-card.active {
    border-color: var(--ink);
    box-shadow: inset 0 0 0 1px var(--ink);
  }
  .kind-card input[type="radio"] {
    appearance: none;
    width: 14px;
    height: 14px;
    border: 1px solid var(--line-strong);
    border-radius: 50%;
    position: relative;
    margin: 0;
  }
  .kind-card.active input[type="radio"]::after {
    content: "";
    position: absolute;
    inset: 2px;
    background: var(--ink);
    border-radius: 50%;
  }
  .kind-text {
    font-size: 0.85rem;
    color: var(--muted);
  }
  .field.full {
    grid-column: 1 / -1;
  }
</style>
