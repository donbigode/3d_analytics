<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { AutoNameOut, Client, InboxItem, QuoteKind } from "$lib/types";

  let rows: InboxItem[] = [];
  let clients: Client[] = [];
  let loading = true;
  let listError = "";

  let promoting: InboxItem | null = null;
  let pKind: QuoteKind = "commercial";
  let pClient = "";
  let pName = "";
  let pSubmitting = false;
  let pError = "";

  let namingId: string | null = null;
  let nameError = "";

  async function suggestName(r: InboxItem) {
    namingId = r.id;
    nameError = "";
    try {
      const out = await api<AutoNameOut>(`/llm/auto-name/${r.id}`, { method: "POST" });
      pName = out.name;
      if (!promoting) {
        // open the promote modal pre-filled with the suggestion
        promoting = r;
        pKind = "commercial";
        pClient = "";
        pError = "";
      }
    } catch (err) {
      handleApiError(err);
      nameError = errorMessage(err, "Falha ao gerar nome.");
    } finally {
      namingId = null;
    }
  }

  function basename(p: string): string {
    return p.split("/").pop() ?? p;
  }

  function fmtDate(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString("pt-BR");
    } catch {
      return s;
    }
  }

  function fmtNum(v: number | null | undefined, dec = 2): string {
    if (v === null || v === undefined) return "—";
    return Number(v).toLocaleString("pt-BR", { maximumFractionDigits: dec });
  }

  function fmtDur(s: number | null | undefined): string {
    if (!s) return "—";
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}min` : `${m}min`;
  }

  async function load() {
    loading = true;
    listError = "";
    try {
      rows = await api<InboxItem[]>("/inbox");
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar inbox.");
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

  function openPromote(r: InboxItem) {
    promoting = r;
    pKind = "commercial";
    pClient = "";
    pName = basename(r.original_path).replace(/\.(b?gcode)$/i, "");
    pError = "";
  }

  async function confirmPromote() {
    if (!promoting) return;
    pError = "";
    pSubmitting = true;
    try {
      const body: Record<string, unknown> = {
        kind: pKind,
        client_id: pKind === "commercial" ? pClient || null : null,
        name: pName || null,
      };
      const res = await api<{ id: string }>(`/inbox/${promoting.id}/promote`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      promoting = null;
      goto(`/quotes/${res.id}`);
    } catch (err) {
      handleApiError(err);
      pError = errorMessage(err, "Falha ao promover.");
    } finally {
      pSubmitting = false;
    }
  }

  async function discard(r: InboxItem) {
    if (!confirm(`Descartar "${basename(r.original_path)}"?`)) return;
    try {
      await api(`/inbox/${r.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao descartar.");
    }
  }

  onMount(() => {
    if (requireAuth()) return;
    loadClients();
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Captura / 03</span>
  <h1 class="page-title">Inbox<em>.</em></h1>
  <p class="page-lede">
    Arquivos <code class="mono">.gcode</code> capturados pelo watcher. Promova
    cada um para virar um orçamento — ou descarte se for ruído.
  </p>
</header>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">Pendentes <span class="count">· {rows.length}</span></h2>
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Arquivo</th>
          <th>Material</th>
          <th class="right">Filamento</th>
          <th class="right">Tempo</th>
          <th>Capturado</th>
          <th class="right">Ações</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as r (r.id)}
          <tr>
            <td class="mono">{basename(r.original_path)}</td>
            <td class="mono">{r.parsed_meta?.material ?? "—"}</td>
            <td class="right mono">{fmtNum(r.parsed_meta?.filament_m, 2)} m</td>
            <td class="right mono">{fmtDur(r.parsed_meta?.time_s)}</td>
            <td class="mono dim">{fmtDate(r.created_at)}</td>
            <td class="right">
              <button class="tiny ghost" on:click={() => suggestName(r)} disabled={namingId === r.id}>
                {namingId === r.id ? "✨ pensando…" : "✨ nome"}
              </button>
              <button class="tiny" on:click={() => openPromote(r)}>promover</button>
              <button class="tiny danger" on:click={() => discard(r)}>descartar</button>
            </td>
          </tr>
        {/each}
        {#if rows.length === 0}
          <tr>
            <td colspan="6"><div class="empty">Nenhum arquivo aguardando</div></td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>

{#if promoting}
  <div class="modal-backdrop" on:click|self={() => (promoting = null)}>
    <div class="modal">
      <h2>Promover arquivo</h2>
      <p class="dim mono">{basename(promoting.original_path)}</p>
      {#if pError}<div class="alert">{pError}</div>{/if}
      <form on:submit|preventDefault={confirmPromote} class="form-grid">
        <label class="field full">
          Tipo
          <div class="kind-row">
            <label class="kind-card" class:active={pKind === "commercial"}>
              <input type="radio" bind:group={pKind} value="commercial" />
              <span class="tag brand">comercial</span>
            </label>
            <label class="kind-card" class:active={pKind === "personal"}>
              <input type="radio" bind:group={pKind} value="personal" />
              <span class="tag muted">pessoal</span>
            </label>
          </div>
        </label>
        {#if pKind === "commercial"}
          <label class="field">
            Cliente
            <select bind:value={pClient}>
              <option value="">— sem cliente —</option>
              {#each clients as c}
                <option value={c.id}>{c.name}</option>
              {/each}
            </select>
          </label>
        {/if}
        <label class="field full">
          Nome da peça
          <input bind:value={pName} placeholder="Nome interno do item" />
        </label>
        <div class="actions">
          <button type="button" class="ghost" on:click={() => (promoting = null)} disabled={pSubmitting}>
            Cancelar
          </button>
          <button type="submit" disabled={pSubmitting}>
            {pSubmitting ? "Promovendo…" : "Promover"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<style>
  .page-head {
    margin-bottom: 2rem;
  }
  .table-wrap {
    border: 1px solid var(--line);
    overflow-x: auto;
    margin-top: 1rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
  }
  thead th {
    text-align: left;
    padding: 0.6rem 0.75rem;
    font-family: var(--font-mono);
    font-weight: 500;
    font-size: 0.68rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--line-strong);
  }
  thead th.right, td.right {
    text-align: right;
  }
  tbody td {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--line);
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
  .kind-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.6rem;
    margin-top: 0.35rem;
  }
  .kind-card {
    border: 1px solid var(--line);
    padding: 0.7rem;
    display: flex;
    align-items: center;
    gap: 0.55rem;
    cursor: pointer;
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
  .field.full {
    grid-column: 1 / -1;
  }
  .section-title {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--ink);
    margin: 0;
  }
  .section-title .count {
    color: var(--muted);
    font-weight: 400;
  }
  .dim {
    color: var(--muted);
  }
</style>
