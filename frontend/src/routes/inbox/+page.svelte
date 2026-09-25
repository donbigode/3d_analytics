<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import { dateTime as fmtDate, num as fmtNum, dur as fmtDur } from "$lib/format";
  import { quoteNumber } from "$lib/quote-number";
  import type {
    AutoNameOut,
    Client,
    InboxItem,
    PrinterJobItem,
    Quote,
    QuoteKind,
    Spool,
  } from "$lib/types";

  const rows = resource(() => api<InboxItem[]>("/inbox"), {
    initial: [], errorMessage: "Falha ao carregar inbox.", auto: false,
  });
  const discardAction = action((id: string) => api(`/inbox/${id}`, { method: "DELETE" }), {
    errorMessage: "Falha ao descartar.",
  });
  // Um "Atualizar" bem-sucedido não pode deixar preso o erro de um descarte
  // que falhou antes — os dois dividem o mesmo alerta do painel.
  $: listError = $rows.error || $discardAction.error;
  function reloadRows() {
    discardAction.reset();
    return rows.reload();
  }

  const clients = resource(() => api<Client[]>("/clients"), { initial: [], auto: false });

  // Impressora: jobs capturados do Moonraker (via agente local), atachados a
  // um orçamento que o usuário criou. Atachar só vincula + grava as gramas
  // reais; a baixa de estoque acontece depois, no "Produzir" do orçamento.
  const pjRows = resource(() => api<PrinterJobItem[]>("/printer-jobs"), {
    initial: [], errorMessage: "Falha ao carregar impressos.", auto: false,
  });
  const discardPjAction = action((id: string) => api(`/printer-jobs/${id}`, { method: "DELETE" }), {
    errorMessage: "Falha ao descartar.",
  });
  // Mesmo raciocínio: attach bem-sucedido também não pode deixar preso o
  // erro de um descarte anterior que falhou (mesmo alerta do painel).
  $: pjError = $pjRows.error || $discardPjAction.error;
  function reloadPjRows() {
    discardPjAction.reset();
    return pjRows.reload();
  }

  const spools = resource(() => api<Spool[]>("/spools"), { initial: [], auto: false });
  const quotes = resource(() => api<Quote[]>("/quotes"), { initial: [], auto: false });

  let attaching: PrinterJobItem | null = null;
  let aQuote = "";
  let aSpool = "";
  let aDone = "";
  const attachAction = action(
    (id: string, quoteId: string, spoolId: string) =>
      api(`/printer-jobs/${id}/link`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ quote_id: quoteId, spool_id: spoolId }),
      }),
    { errorMessage: "Falha ao atachar." },
  );

  let promoting: InboxItem | null = null;
  let pKind: QuoteKind = "commercial";
  let pClient = "";
  let pName = "";
  const promoteAction = action(
    (id: string, body: Record<string, unknown>) =>
      api<{ id: string }>(`/inbox/${id}/promote`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao promover." },
  );

  let namingId: string | null = null;
  const suggestNameAction = action(
    (id: string) => api<AutoNameOut>(`/llm/auto-name/${id}`, { method: "POST" }),
    { errorMessage: "Falha ao gerar nome." },
  );

  async function suggestName(r: InboxItem) {
    namingId = r.id;
    const out = await suggestNameAction.run(r.id);
    namingId = null;
    if (!out) return;
    pName = out.name;
    if (!promoting) {
      // open the promote modal pre-filled with the suggestion
      promoting = r;
      pKind = "commercial";
      pClient = "";
      promoteAction.reset();
    }
  }

  function basename(p: string): string {
    return p.split("/").pop() ?? p;
  }

  function openPromote(r: InboxItem) {
    promoting = r;
    pKind = "commercial";
    pClient = "";
    pName = basename(r.original_path).replace(/\.(b?gcode)$/i, "");
    promoteAction.reset();
  }

  async function confirmPromote() {
    if (!promoting) return;
    const body: Record<string, unknown> = {
      kind: pKind,
      client_id: pKind === "commercial" ? pClient || null : null,
      name: pName || null,
    };
    const res = await promoteAction.run(promoting.id, body);
    if (!res) return;
    promoting = null;
    goto(`/quotes/${res.id}`);
  }

  async function discard(r: InboxItem) {
    if (!confirm(`Descartar "${basename(r.original_path)}"?`)) return;
    await discardAction.run(r.id);
    if (!$discardAction.error) await rows.reload();
  }

  function openAttach(r: PrinterJobItem) {
    attaching = r;
    aQuote = "";
    aSpool = "";
    aDone = "";
    attachAction.reset();
  }

  async function confirmAttach() {
    if (!attaching || !aQuote || !aSpool) return;
    await attachAction.run(attaching.id, aQuote, aSpool);
    if ($attachAction.error) return;
    attaching = null;
    // Orienta o próximo passo manual: produzir o orçamento (baixa o estoque).
    aDone = aQuote;
    await reloadPjRows();
  }

  async function discardPrinterJob(r: PrinterJobItem) {
    if (!confirm(`Descartar impresso "${r.filename ?? r.machine}"?`)) return;
    await discardPjAction.run(r.id);
    if (!$discardPjAction.error) await pjRows.reload();
  }

  function mmToM(mm: number | null | undefined): number | null {
    if (mm === null || mm === undefined) return null;
    return mm / 1000;
  }

  onMount(() => {
    if (requireAuth()) return;
    clients.reload();
    rows.reload();
    pjRows.reload();
    spools.reload();
    quotes.reload();
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
    <h2 class="section-title">Pendentes <span class="count">· {($rows.data ?? []).length}</span></h2>
    <button class="tiny ghost" on:click={reloadRows} disabled={$rows.loading}>
      {$rows.loading ? "Carregando…" : "Atualizar"}
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
        {#each $rows.data ?? [] as r (r.id)}
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
        {#if ($rows.data ?? []).length === 0}
          <tr>
            <td colspan="6"><div class="empty">Nenhum arquivo aguardando</div></td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">Impressora <span class="count">· {($pjRows.data ?? []).length}</span></h2>
    <button class="tiny ghost" on:click={reloadPjRows}>Atualizar</button>
  </div>
  <p class="pj-lede">
    Impressos capturados da impressora. <strong>Atachar</strong> vincula a um
    orçamento que você criou e registra as gramas reais — a baixa de estoque
    acontece depois, quando você <strong>Produzir</strong> o orçamento.
  </p>
  {#if pjError}<div class="alert">{pjError}</div>{/if}
  {#if aDone}
    <div class="ok">
      Atachado. Agora abra o
      <a href={`/quotes/${aDone}`}>orçamento</a> e clique em <strong>Produzir</strong>
      para baixar o estoque pelas gramas reais (selecione o mesmo spool que você atachou).
    </div>
  {/if}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Arquivo</th>
          <th>Máquina</th>
          <th class="right">Filamento</th>
          <th class="right">Tempo</th>
          <th>Status</th>
          <th class="right">Ações</th>
        </tr>
      </thead>
      <tbody>
        {#each $pjRows.data ?? [] as r (r.id)}
          <tr>
            <td class="mono">{r.filename ?? "—"}</td>
            <td class="mono">{r.machine}</td>
            <td class="right mono">{fmtNum(mmToM(r.filament_used_mm), 2)} m</td>
            <td class="right mono">{fmtDur(r.time_s)}</td>
            <td class="mono">{r.status}</td>
            <td class="right">
              <button class="tiny" on:click={() => openAttach(r)}>atachar</button>
              <button class="tiny danger" on:click={() => discardPrinterJob(r)}>descartar</button>
            </td>
          </tr>
        {/each}
        {#if ($pjRows.data ?? []).length === 0}
          <tr>
            <td colspan="6"><div class="empty">Nenhum impresso aguardando</div></td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>

{#if attaching}
  <div class="modal-backdrop" on:click|self={() => (attaching = null)}>
    <div class="modal">
      <h2>Atachar impresso</h2>
      <p class="dim mono">{attaching.filename ?? attaching.machine}</p>
      {#if $attachAction.error}<div class="alert">{$attachAction.error}</div>{/if}
      <form on:submit|preventDefault={confirmAttach} class="form-grid">
        <label class="field full">
          Orçamento
          <select bind:value={aQuote}>
            <option value="">— escolha —</option>
            {#each $quotes.data ?? [] as q}
              <option value={q.id}>{quoteNumber(q.seq)} · {q.kind} · {q.status}</option>
            {/each}
          </select>
        </label>
        <label class="field full">
          Filamento usado (spool)
          <select bind:value={aSpool}>
            <option value="">— escolha —</option>
            {#each $spools.data ?? [] as sp}
              <option value={sp.id}>
                {sp.material_type}{sp.color ? ` ${sp.color}` : ""} · {fmtNum(Number(sp.remaining_grams), 0)}g
              </option>
            {/each}
          </select>
        </label>
        <div class="actions">
          <button type="button" class="ghost" on:click={() => (attaching = null)} disabled={$attachAction.pending}>
            Cancelar
          </button>
          <button type="submit" disabled={$attachAction.pending || !aQuote || !aSpool}>
            {$attachAction.pending ? "Atachando…" : "Atachar"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if promoting}
  <div class="modal-backdrop" on:click|self={() => (promoting = null)}>
    <div class="modal">
      <h2>Promover arquivo</h2>
      <p class="dim mono">{basename(promoting.original_path)}</p>
      {#if $promoteAction.error}<div class="alert">{$promoteAction.error}</div>{/if}
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
              {#each $clients.data ?? [] as c}
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
          <button type="button" class="ghost" on:click={() => (promoting = null)} disabled={$promoteAction.pending}>
            Cancelar
          </button>
          <button type="submit" disabled={$promoteAction.pending}>
            {$promoteAction.pending ? "Promovendo…" : "Promover"}
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
  /* .table-wrap agora vive em app.css (mesmos valores) */
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
  /* Override local: padding/letter-spacing diferentes do padrão global
     (mantém aparência já existente nesta página) */
  .empty {
    padding: 2rem 1rem;
    text-align: center;
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
  /* Override local: sem o flex/gap/margem-inferior padrão de app.css —
     o espaçamento entre título e contador aqui vem só do espaço no texto
     (mantém aparência já existente antes desta classe virar global) */
  .section-title {
    display: block;
    gap: 0;
    margin: 0;
  }
  .dim {
    color: var(--muted);
  }
  .pj-lede {
    margin: 0.4rem 0 0.2rem;
    font-size: 0.86rem;
    color: var(--muted);
    max-width: 60ch;
  }
  .ok {
    margin-top: 0.75rem;
    padding: 0.6rem 0.75rem;
    border: 1px solid var(--line-strong);
    background: color-mix(in srgb, var(--ink) 4%, transparent);
    font-size: 0.88rem;
  }
  .ok a {
    text-decoration: underline;
  }
</style>
