<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { Client, Quote, QuoteKind, QuoteStatus } from "$lib/types";

  let rows: Quote[] = [];
  let clients: Client[] = [];
  let loading = true;
  let listError = "";

  // filters
  let fStatus: QuoteStatus | "" = "";
  let fKind: QuoteKind | "" = "";
  let fClient = "";

  const STATUS_OPTIONS: { value: QuoteStatus; label: string }[] = [
    { value: "draft", label: "Rascunho" },
    { value: "orcado", label: "Orçado" },
    { value: "aprovado", label: "Aprovado" },
    { value: "produzido", label: "Produzido" },
    { value: "entregue", label: "Entregue" },
    { value: "cancelado", label: "Cancelado" },
  ];

  function statusLabel(s: string): string {
    return STATUS_OPTIONS.find((o) => o.value === s)?.label ?? s;
  }

  function statusClass(s: string): string {
    switch (s) {
      case "entregue":
      case "produzido":
        return "ok";
      case "cancelado":
        return "warn";
      case "aprovado":
        return "brand";
      default:
        return "muted";
    }
  }

  function clientName(id: string | null): string {
    if (!id) return "—";
    return clients.find((c) => c.id === id)?.name ?? "—";
  }

  function fmtMoney(v: number | string): string {
    const n = typeof v === "string" ? parseFloat(v) : v;
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function fmtDate(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return s;
    }
  }

  async function load() {
    loading = true;
    listError = "";
    try {
      const qs = new URLSearchParams();
      if (fStatus) qs.set("status", fStatus);
      if (fKind) qs.set("kind", fKind);
      if (fClient) qs.set("client_id", fClient);
      const path = `/quotes${qs.toString() ? `?${qs}` : ""}`;
      rows = await api<Quote[]>(path);
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar orçamentos.");
    } finally {
      loading = false;
    }
  }

  async function loadClients() {
    try {
      clients = await api<Client[]>("/clients");
    } catch (err) {
      handleApiError(err);
    }
  }

  function resetFilters() {
    fStatus = "";
    fKind = "";
    fClient = "";
    load();
  }

  onMount(() => {
    if (requireAuth()) return;
    loadClients();
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Operação / 02</span>
  <h1 class="page-title">Orçamentos<em>.</em></h1>
  <p class="page-lede">
    Fluxo comercial e pessoal: do rascunho à entrega. Filtre por status, tipo ou
    cliente; abra um para editar, finalizar, produzir ou gerar o PDF.
  </p>
</header>

<section class="panel filters">
  <div class="panel-head">
    <div class="heading">
      <span class="page-eyebrow">Filtros</span>
      <h2 class="form-title">Refinar lista</h2>
    </div>
    <a class="btn" href="/quotes/new">+ novo orçamento</a>
  </div>
  <div class="form-grid filter-grid">
    <label class="field">
      Status
      <select bind:value={fStatus} on:change={load}>
        <option value="">todos</option>
        {#each STATUS_OPTIONS as o}
          <option value={o.value}>{o.label}</option>
        {/each}
      </select>
    </label>
    <label class="field">
      Tipo
      <select bind:value={fKind} on:change={load}>
        <option value="">todos</option>
        <option value="commercial">Comercial</option>
        <option value="personal">Pessoal</option>
      </select>
    </label>
    <label class="field">
      Cliente
      <select bind:value={fClient} on:change={load}>
        <option value="">todos</option>
        {#each clients as c}
          <option value={c.id}>{c.name}</option>
        {/each}
      </select>
    </label>
    <div class="actions">
      <button type="button" class="ghost tiny" on:click={resetFilters}>limpar</button>
    </div>
  </div>
</section>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">Orçamentos <span class="count">· {rows.length}</span></h2>
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Tipo</th>
          <th>Status</th>
          <th>Cliente</th>
          <th class="right">Total</th>
          <th>Criado</th>
          <th class="right">Ações</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as q (q.id)}
          <tr>
            <td class="mono">{q.id.slice(0, 8)}</td>
            <td>
              <span class="tag {q.kind === 'commercial' ? 'brand' : 'muted'}">
                {q.kind === "commercial" ? "comercial" : "pessoal"}
              </span>
            </td>
            <td>
              <span class="tag {statusClass(q.status)}">{statusLabel(q.status)}</span>
            </td>
            <td>{clientName(q.client_id)}</td>
            <td class="right mono">{fmtMoney(q.total)}</td>
            <td class="mono dim">{fmtDate(q.created_at)}</td>
            <td class="right">
              <a class="tiny ghost btn" href={`/quotes/${q.id}`}>abrir</a>
            </td>
          </tr>
        {/each}
        {#if rows.length === 0}
          <tr>
            <td colspan="7"><div class="empty">Nenhum orçamento encontrado</div></td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>

<style>
  .page-head {
    margin-bottom: 2rem;
  }
  .filters {
    margin-bottom: 1.5rem;
  }
  .filter-grid {
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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
  .table-wrap {
    border: 1px solid var(--line);
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
  }
  thead th {
    text-align: left;
    padding: 0.7rem 0.85rem;
    font-family: var(--font-mono);
    font-weight: 500;
    font-size: 0.68rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--line-strong);
    background: var(--paper);
  }
  thead th.right,
  td.right {
    text-align: right;
  }
  tbody td {
    padding: 0.7rem 0.85rem;
    border-bottom: 1px solid var(--line);
    vertical-align: middle;
  }
  tbody tr:hover td {
    background: rgba(26, 26, 29, 0.025);
  }
  td.mono {
    font-family: var(--font-mono);
    font-size: 0.86rem;
  }
  td.dim {
    color: var(--muted);
  }
  .empty {
    padding: 2rem 1rem;
    text-align: center;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.74rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }
  a.btn {
    text-decoration: none;
    display: inline-block;
  }
</style>
