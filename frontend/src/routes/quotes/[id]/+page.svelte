<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type {
    Client,
    Material,
    MarkupSuggestionOut,
    PricingOut,
    Quote,
    QuoteItem,
    Service,
    Spool,
    VarianceOut,
    VariantsOut,
  } from "$lib/types";

  $: id = $page.params.id;

  let quote: Quote | null = null;
  let loading = true;
  let pageError = "";

  let clients: Client[] = [];
  let services: Service[] = [];
  let spools: Spool[] = [];
  let materials: Material[] = [];

  // resolve pending material modal
  let resolveItem: QuoteItem | null = null;
  let resolveCode = "";
  let resolveError = "";
  let resolving = false;
  let showQuickCreateMaterial = false;
  let qcName = "";
  let qcDensity = "1.24";
  let qcPrice = "100";
  let qcFailure = "5";
  let qcSubmitting = false;
  let qcError = "";

  // add item form
  let itemFile: FileList | null = null;
  let itemName = "";
  let itemQty = 1;
  let itemModelUrl = "";
  let itemModelAuthor = "";
  let itemModelLicense = "";
  let addingItem = false;
  let itemError = "";

  // add service form
  let svcId = "";
  let svcQty = 1;
  let svcRate: string = "";
  let addingSvc = false;
  let svcError = "";

  // edit meta (markup/min/client/notes/produced services)
  let editMarkup = 0;
  let editMin = 0;
  let editClient: string = "";
  let editNotes = "";
  let savingMeta = false;
  let metaError = "";

  // ---- IA panel state ----
  let llmBusy: "markup" | "variance" | "pricing" | "variants" | null = null;
  let llmError = "";
  let markupSuggestion: MarkupSuggestionOut | null = null;
  let varianceResult: VarianceOut | null = null;
  let pricingResult: PricingOut | null = null;
  let variantsResult: VariantsOut | null = null;
  let variantsForItem = "";

  async function askMarkup() {
    if (!quote) return;
    llmBusy = "markup"; llmError = "";
    try {
      markupSuggestion = await api<MarkupSuggestionOut>(`/llm/markup/${quote.id}`, { method: "POST" });
    } catch (err) {
      handleApiError(err);
      llmError = errorMessage(err, "Falha ao consultar IA.");
    } finally { llmBusy = null; }
  }
  async function applyMarkup() {
    if (!quote || !markupSuggestion) return;
    const v = Number(markupSuggestion.suggested_markup_pct);
    if (!Number.isFinite(v)) return;
    editMarkup = v;
    await saveMeta();
  }

  async function askVariance() {
    if (!quote) return;
    llmBusy = "variance"; llmError = "";
    try {
      varianceResult = await api<VarianceOut>(`/llm/variance/${quote.id}`, { method: "POST" });
    } catch (err) {
      handleApiError(err);
      llmError = errorMessage(err, "Falha ao consultar IA.");
    } finally { llmBusy = null; }
  }

  async function askPricing() {
    if (!quote) return;
    llmBusy = "pricing"; llmError = "";
    try {
      pricingResult = await api<PricingOut>(`/llm/pricing/${quote.id}`, { method: "POST" });
    } catch (err) {
      handleApiError(err);
      llmError = errorMessage(err, "Falha ao consultar IA.");
    } finally { llmBusy = null; }
  }

  async function askVariants(itemId: string) {
    if (!quote) return;
    variantsForItem = itemId;
    llmBusy = "variants"; llmError = "";
    try {
      variantsResult = await api<VariantsOut>(`/llm/variants/items/${itemId}`, { method: "POST" });
    } catch (err) {
      handleApiError(err);
      llmError = errorMessage(err, "Falha ao consultar IA.");
    } finally { llmBusy = null; }
  }

  // transition state
  let transitioning = "";
  let txError = "";

  // produce modal
  let showProduceModal = false;
  let produceAssignments: Record<string, string> = {}; // quote_item_id -> spool_id
  let producing = false;
  let produceError = "";

  function fmtMoney(v: number | string | null | undefined): string {
    if (v === null || v === undefined) return "—";
    const n = typeof v === "string" ? parseFloat(v) : v;
    return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  function fmtNum(v: number | string | null | undefined, dec = 2): string {
    if (v === null || v === undefined) return "—";
    const n = typeof v === "string" ? parseFloat(v) : v;
    return n.toLocaleString("pt-BR", { maximumFractionDigits: dec });
  }
  function fmtDur(s: number | string | null | undefined): string {
    if (!s) return "—";
    const n = typeof s === "string" ? parseFloat(s) : s;
    if (!isFinite(n)) return "—";
    const h = Math.floor(n / 3600);
    const m = Math.floor((n % 3600) / 60);
    return h > 0 ? `${h}h ${m}min` : `${m}min`;
  }
  function fmtDate(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString("pt-BR");
    } catch {
      return s;
    }
  }
  function statusLabel(s: string): string {
    return (
      {
        draft: "Rascunho",
        orcado: "Orçado",
        aprovado: "Aprovado",
        produzido: "Produzido",
        entregue: "Entregue",
        cancelado: "Cancelado",
      } as Record<string, string>
    )[s] ?? s;
  }
  function statusClass(s: string): string {
    if (s === "entregue" || s === "produzido") return "ok";
    if (s === "cancelado") return "warn";
    if (s === "aprovado") return "brand";
    return "muted";
  }

  function clientName(cid: string | null): string {
    if (!cid) return "—";
    return clients.find((c) => c.id === cid)?.name ?? "—";
  }

  function serviceName(sid: string): string {
    return services.find((s) => s.id === sid)?.name ?? sid.slice(0, 8);
  }

  async function load() {
    loading = true;
    pageError = "";
    try {
      quote = await api<Quote>(`/quotes/${id}`);
      editMarkup = Number(quote.markup_pct ?? 0);
      editMin = Number(quote.min_charge ?? 0);
      editClient = quote.client_id ?? "";
      editNotes = quote.notes ?? "";
    } catch (err) {
      handleApiError(err);
      pageError = errorMessage(err, "Falha ao carregar orçamento.");
    } finally {
      loading = false;
    }
  }

  async function loadRefs() {
    try {
      [clients, services, spools, materials] = await Promise.all([
        api<Client[]>("/clients"),
        api<Service[]>("/services"),
        api<Spool[]>("/spools"),
        api<Material[]>("/materials"),
      ]);
    } catch (err) {
      handleApiError(err);
    }
  }

  $: filteredServices = quote
    ? services.filter(
        (s) =>
          s.is_active &&
          (quote!.kind === "commercial" ? true : s.kind !== "labor"),
      )
    : [];

  $: isDraft = quote?.status === "draft";
  $: canCancel =
    quote && quote.status !== "entregue" && quote.status !== "cancelado";

  async function saveMeta() {
    if (!quote) return;
    metaError = "";
    savingMeta = true;
    try {
      const body: Record<string, unknown> = {
        notes: editNotes || null,
      };
      if (quote.kind === "commercial") {
        body.client_id = editClient || null;
        body.markup_pct = editMarkup;
        body.min_charge = editMin;
      }
      quote = await api<Quote>(`/quotes/${id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (err) {
      handleApiError(err);
      metaError = errorMessage(err, "Falha ao salvar.");
    } finally {
      savingMeta = false;
    }
  }

  async function addItem() {
    if (!quote || !itemFile || itemFile.length === 0) return;
    itemError = "";
    addingItem = true;
    try {
      const fd = new FormData();
      fd.append("file", itemFile[0]);
      fd.append("name", itemName || itemFile[0].name);
      fd.append("quantity", String(itemQty));
      if (itemModelUrl) fd.append("model_source_url", itemModelUrl);
      if (itemModelAuthor) fd.append("model_source_author", itemModelAuthor);
      if (itemModelLicense) fd.append("model_source_license", itemModelLicense);
      const res = await fetch(`/api/quotes/${id}/items`, {
        method: "POST",
        body: fd,
        credentials: "include",
      });
      if (!res.ok) {
        const t = await res.text();
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(t);
          if (typeof j.detail === "string") msg = j.detail;
        } catch {}
        throw new Error(msg);
      }
      quote = (await res.json()) as Quote;
      itemFile = null;
      itemName = "";
      itemQty = 1;
      itemModelUrl = "";
      itemModelAuthor = "";
      itemModelLicense = "";
      const input = document.getElementById("itemFile") as HTMLInputElement | null;
      if (input) input.value = "";
    } catch (err) {
      itemError = err instanceof Error ? err.message : "Falha ao adicionar peça.";
    } finally {
      addingItem = false;
    }
  }

  function openResolve(it: QuoteItem) {
    resolveItem = it;
    resolveCode = it.pending_material_code || it.gcode_meta?.material || "";
    resolveError = "";
    showQuickCreateMaterial = false;
    qcName = resolveCode || "";
    qcDensity = "1.24";
    qcPrice = "100";
    qcFailure = "5";
    qcError = "";
  }

  async function confirmResolve() {
    if (!resolveItem || !resolveCode) return;
    resolveError = "";
    resolving = true;
    try {
      quote = await api<Quote>(`/quotes/${id}/items/${resolveItem.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ material_code: resolveCode }),
      });
      resolveItem = null;
    } catch (err) {
      handleApiError(err);
      resolveError = errorMessage(err, "Falha ao resolver material.");
    } finally {
      resolving = false;
    }
  }

  async function quickCreateMaterial() {
    if (!qcName) return;
    qcError = "";
    qcSubmitting = true;
    try {
      const mv = await api<Material>("/materials", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          material_code: qcName,
          name: qcName,
          density_g_cm3: qcDensity,
          price_per_kg_ref: qcPrice,
          failure_rate_pct: qcFailure,
        }),
      });
      // refresh local materials list and set resolveCode to the new one
      materials = [...materials, mv];
      resolveCode = mv.material_code;
      showQuickCreateMaterial = false;
    } catch (err) {
      handleApiError(err);
      qcError = errorMessage(err, "Não foi possível criar o material.");
    } finally {
      qcSubmitting = false;
    }
  }

  async function removeItem(itemId: string) {
    if (!confirm("Remover esta peça?")) return;
    try {
      quote = await api<Quote>(`/quotes/${id}/items/${itemId}`, {
        method: "DELETE",
      });
    } catch (err) {
      handleApiError(err);
      itemError = errorMessage(err, "Falha ao remover peça.");
    }
  }

  async function addService() {
    if (!quote || !svcId) return;
    svcError = "";
    addingSvc = true;
    try {
      const body: Record<string, unknown> = {
        service_id: svcId,
        quantity: svcQty,
      };
      if (svcRate !== "") body.rate = Number(svcRate);
      quote = await api<Quote>(`/quotes/${id}/services`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      svcId = "";
      svcQty = 1;
      svcRate = "";
    } catch (err) {
      handleApiError(err);
      svcError = errorMessage(err, "Falha ao adicionar serviço.");
    } finally {
      addingSvc = false;
    }
  }

  async function removeService(qsId: string) {
    if (!confirm("Remover este serviço?")) return;
    try {
      quote = await api<Quote>(`/quotes/${id}/services/${qsId}`, {
        method: "DELETE",
      });
    } catch (err) {
      handleApiError(err);
      svcError = errorMessage(err, "Falha ao remover serviço.");
    }
  }

  async function transition(t: "finalize" | "approve" | "deliver" | "cancel") {
    if (!quote) return;
    txError = "";
    transitioning = t;
    try {
      quote = await api<Quote>(`/quotes/${id}/transitions/${t}`, {
        method: "POST",
      });
    } catch (err) {
      handleApiError(err);
      txError = errorMessage(err, `Falha ao executar ${t}.`);
    } finally {
      transitioning = "";
    }
  }

  function openProduce() {
    if (!quote) return;
    produceAssignments = {};
    for (const it of quote.items) {
      const matCode = it.gcode_meta?.material ?? null;
      const candidate = spools.find(
        (sp) =>
          sp.status === "open" &&
          (matCode ? sp.material_code === matCode : true),
      );
      produceAssignments[it.id] = candidate?.id ?? "";
    }
    produceError = "";
    showProduceModal = true;
  }

  function spoolsForItem(matCode: string | null | undefined) {
    return spools.filter(
      (sp) => sp.status === "open" && (matCode ? sp.material_code === matCode : true),
    );
  }

  async function confirmProduce() {
    if (!quote) return;
    produceError = "";
    producing = true;
    try {
      const consumption = quote.items.map((it) => ({
        quote_item_id: it.id,
        spool_id: produceAssignments[it.id],
      }));
      if (consumption.some((c) => !c.spool_id)) {
        throw new Error("Selecione um spool para cada peça.");
      }
      quote = await api<Quote>(`/quotes/${id}/transitions/produce`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ consumption }),
      });
      showProduceModal = false;
    } catch (err) {
      handleApiError(err);
      produceError =
        err instanceof Error ? err.message : errorMessage(err, "Falha ao produzir.");
    } finally {
      producing = false;
    }
  }

  function openPdf() {
    window.open(`/api/quotes/${id}/pdf`, "_blank");
  }

  onMount(() => {
    if (requireAuth()) return;
    loadRefs();
    load();
  });
</script>

{#if loading}
  <p class="empty">Carregando…</p>
{:else if pageError}
  <div class="alert">{pageError}</div>
  <a href="/quotes" class="tiny ghost btn">voltar</a>
{:else if quote}
  <header class="page-head">
    <div class="head-row">
      <div>
        <span class="page-eyebrow">Orçamento · {quote.id.slice(0, 8)}</span>
        <h1 class="page-title">
          {quote.kind === "commercial" ? "Comercial" : "Pessoal"}<em>.</em>
        </h1>
        <p class="page-lede mono dim">
          criado {fmtDate(quote.created_at)} · cliente {clientName(quote.client_id)}
        </p>
      </div>
      <div class="head-tags">
        <span class="tag {quote.kind === 'commercial' ? 'brand' : 'muted'}">
          {quote.kind === "commercial" ? "comercial" : "pessoal"}
        </span>
        <span class="tag {statusClass(quote.status)}">{statusLabel(quote.status)}</span>
      </div>
    </div>
  </header>

  {#if txError}<div class="alert">{txError}</div>{/if}

  <div class="layout">
    <div class="main-col">
      <section class="panel">
        <div class="panel-head">
          <h2 class="section-title">Peças <span class="count">· {quote.items.length}</span></h2>
        </div>
        {#if itemError}<div class="alert">{itemError}</div>{/if}

        {#if isDraft}
          <form class="form-grid item-form" on:submit|preventDefault={addItem}>
            <label class="field">
              Arquivo G-code
              <input id="itemFile" type="file" accept=".gcode,.bgcode" bind:files={itemFile} required />
            </label>
            <label class="field">
              Nome
              <input bind:value={itemName} placeholder="Ex.: porta-caneta" />
            </label>
            <label class="field">
              Quantidade
              <input type="number" min="1" step="1" bind:value={itemQty} />
            </label>
            <label class="field">
              Modelo (URL — opcional)
              <input
                type="url"
                bind:value={itemModelUrl}
                placeholder="https://printables.com/model/..."
              />
            </label>
            <label class="field">
              Autor (opcional)
              <input bind:value={itemModelAuthor} placeholder="Nome do criador" />
            </label>
            <label class="field">
              Licença (opcional)
              <input bind:value={itemModelLicense} placeholder="CC-BY, CC-BY-NC, ..." />
            </label>
            <div class="actions">
              <button type="submit" disabled={addingItem || !itemFile?.length}>
                {addingItem ? "Enviando…" : "+ adicionar peça"}
              </button>
            </div>
          </form>
        {/if}

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Peça</th>
                <th>Material</th>
                <th class="right">Filamento</th>
                <th class="right">Tempo</th>
                <th class="right">Qtd</th>
                <th class="right">Subtotal</th>
                {#if isDraft}<th class="right">Ações</th>{/if}
              </tr>
            </thead>
            <tbody>
              {#each quote.items as it (it.id)}
                <tr class:pending={it.material_pending}>
                  <td>{it.name}</td>
                  <td class="mono">
                    {it.gcode_meta?.material ?? "—"}
                    {#if it.material_pending}
                      <span class="badge pending">pendente</span>
                    {/if}
                  </td>
                  <td class="right mono">{fmtNum(it.gcode_meta?.filament_m, 2)} m</td>
                  <td class="right mono">{fmtDur(it.gcode_meta?.time_s)}</td>
                  <td class="right mono">{it.quantity}</td>
                  <td class="right mono">{fmtMoney(it.subtotal)}</td>
                  {#if isDraft}
                    <td class="right">
                      {#if it.material_pending}
                        <button class="tiny" on:click={() => openResolve(it)}>resolver</button>
                      {/if}
                      <button class="tiny ghost" on:click={() => askVariants(it.id)}
                              disabled={llmBusy === "variants" && variantsForItem === it.id}>
                        {llmBusy === "variants" && variantsForItem === it.id ? "✨…" : "✨ variantes"}
                      </button>
                      <button class="tiny danger" on:click={() => removeItem(it.id)}>remover</button>
                    </td>
                  {/if}
                </tr>
              {/each}
              {#if quote.items.length === 0}
                <tr>
                  <td colspan={isDraft ? 7 : 6}>
                    <div class="empty">Nenhuma peça ainda</div>
                  </td>
                </tr>
              {/if}
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2 class="section-title">Serviços <span class="count">· {quote.services.length}</span></h2>
        </div>
        {#if svcError}<div class="alert">{svcError}</div>{/if}

        {#if isDraft}
          <form class="form-grid svc-form" on:submit|preventDefault={addService}>
            <label class="field">
              Serviço
              <select bind:value={svcId} required>
                <option value="">— escolher —</option>
                {#each filteredServices as s}
                  <option value={s.id}>{s.name} ({s.unit})</option>
                {/each}
              </select>
            </label>
            <label class="field">
              Quantidade
              <input type="number" min="0" step="0.01" bind:value={svcQty} />
            </label>
            <label class="field">
              Tarifa (override)
              <input type="number" min="0" step="0.01" bind:value={svcRate} placeholder="padrão do serviço" />
            </label>
            <div class="actions">
              <button type="submit" disabled={addingSvc || !svcId}>
                {addingSvc ? "Adicionando…" : "+ adicionar serviço"}
              </button>
            </div>
          </form>
        {/if}

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Serviço</th>
                <th class="right">Qtd</th>
                <th class="right">Tarifa</th>
                <th class="right">Subtotal</th>
                {#if isDraft}<th class="right">Ações</th>{/if}
              </tr>
            </thead>
            <tbody>
              {#each quote.services as sv (sv.id)}
                <tr>
                  <td>{serviceName(sv.service_id)}</td>
                  <td class="right mono">{fmtNum(sv.quantity, 2)}</td>
                  <td class="right mono">{fmtMoney(sv.rate)}</td>
                  <td class="right mono">{fmtMoney(sv.subtotal)}</td>
                  {#if isDraft}
                    <td class="right">
                      <button class="tiny danger" on:click={() => removeService(sv.id)}>remover</button>
                    </td>
                  {/if}
                </tr>
              {/each}
              {#if quote.services.length === 0}
                <tr>
                  <td colspan={isDraft ? 5 : 4}>
                    <div class="empty">Nenhum serviço adicionado</div>
                  </td>
                </tr>
              {/if}
            </tbody>
          </table>
        </div>
      </section>

      {#if isDraft && quote.kind === "commercial"}
        <section class="panel">
          <div class="panel-head">
            <h2 class="section-title">Metadados comerciais</h2>
          </div>
          {#if metaError}<div class="alert">{metaError}</div>{/if}
          <form class="form-grid" on:submit|preventDefault={saveMeta}>
            <label class="field">
              Cliente
              <select bind:value={editClient}>
                <option value="">— sem cliente —</option>
                {#each clients as c}
                  <option value={c.id}>{c.name}</option>
                {/each}
              </select>
            </label>
            <label class="field">
              Markup (%)
              <input type="number" min="0" step="0.01" bind:value={editMarkup} />
            </label>
            <label class="field">
              Cobrança mínima
              <input type="number" min="0" step="0.01" bind:value={editMin} />
            </label>
            <label class="field full">
              Notas
              <input bind:value={editNotes} />
            </label>
            <div class="actions">
              <button type="submit" disabled={savingMeta}>
                {savingMeta ? "Salvando…" : "Salvar metadados"}
              </button>
            </div>
          </form>
        </section>
      {/if}
    </div>

    <aside class="side-col">
      <section class="panel totals">
        <div class="panel-head">
          <h2 class="section-title">Totais</h2>
        </div>
        <dl class="kvs">
          <dt>Custo</dt><dd class="mono">{fmtMoney(quote.cost)}</dd>
          {#if quote.kind === "commercial"}
            <dt>Markup</dt><dd class="mono">{fmtNum(quote.markup_pct, 2)} %</dd>
            <dt>Mínimo</dt><dd class="mono">{fmtMoney(quote.min_charge)}</dd>
          {/if}
          <dt class="big">{quote.kind === "commercial" ? "Total" : "Custo total"}</dt>
          <dd class="big mono">{fmtMoney(quote.total)}</dd>
        </dl>
      </section>

      <section class="panel ai-panel">
        <div class="panel-head">
          <span class="page-eyebrow">Assistente IA</span>
          <h2 class="section-title">Sugestões</h2>
        </div>
        {#if llmError}<div class="alert">{llmError}</div>{/if}

        <div class="ai-actions">
          {#if quote.kind === "commercial" && isDraft}
            <button class="tiny ghost" on:click={askMarkup} disabled={llmBusy === "markup"}>
              {llmBusy === "markup" ? "Pensando…" : "F3 · Sugerir markup"}
            </button>
            <button class="tiny ghost" on:click={askPricing} disabled={llmBusy === "pricing"}>
              {llmBusy === "pricing" ? "Pensando…" : "F5 · Sugerir preço"}
            </button>
          {/if}
          {#if quote.status === "produzido" || quote.status === "entregue"}
            <button class="tiny ghost" on:click={askVariance} disabled={llmBusy === "variance"}>
              {llmBusy === "variance" ? "Pensando…" : "F4 · Analisar variância"}
            </button>
          {/if}
        </div>

        {#if markupSuggestion}
          <div class="ai-result">
            <strong>Markup sugerido: {fmtNum(markupSuggestion.suggested_markup_pct, 0)}%</strong>
            {#if markupSuggestion.complexity}
              <span class="tag muted">{markupSuggestion.complexity}</span>
            {/if}
            {#if markupSuggestion.rationale}<p class="dim">{markupSuggestion.rationale}</p>{/if}
            {#if isDraft && quote.kind === "commercial"}
              <button class="tiny" on:click={applyMarkup}>Aplicar</button>
            {/if}
          </div>
        {/if}

        {#if pricingResult}
          <div class="ai-result">
            <strong>Preço sugerido: {fmtMoney(pricingResult.suggested_price)}</strong>
            <span class="tag muted">faixa {fmtMoney(pricingResult.floor)}–{fmtMoney(pricingResult.ceiling)}</span>
            {#if pricingResult.rationale}<p class="dim">{pricingResult.rationale}</p>{/if}
          </div>
        {/if}

        {#if varianceResult}
          <div class="ai-result">
            <strong>Variância: {fmtNum(varianceResult.variance_pct, 1)}%</strong>
            <span class="tag muted">
              orçado {fmtMoney(varianceResult.orcado)} → real {fmtMoney(varianceResult.real)}
            </span>
            <p>{varianceResult.explanation}</p>
          </div>
        {/if}
      </section>

      {#if variantsResult && variantsResult.variants.length > 0}
        <section class="panel ai-panel">
          <div class="panel-head">
            <span class="page-eyebrow">Assistente IA · F6</span>
            <h2 class="section-title">Variantes sugeridas</h2>
          </div>
          <ul class="variants-list">
            {#each variantsResult.variants as v}
              <li>
                <strong>{v.name}</strong>
                {#if v.material}<span class="tag brand">{v.material}</span>{/if}
                {#if v.angle}<p class="dim">{v.angle}</p>{/if}
              </li>
            {/each}
          </ul>
        </section>
      {/if}

      <section class="panel actions-panel">
        <div class="panel-head">
          <h2 class="section-title">Ações</h2>
        </div>
        <div class="vbtns">
          {#if isDraft}
            <button
              on:click={() => transition("finalize")}
              disabled={transitioning === "finalize" || quote.items.length === 0 || (quote.pending_items ?? 0) > 0}
              title={(quote.pending_items ?? 0) > 0 ? `Resolva ${quote.pending_items} peça(s) com material pendente antes de finalizar` : ""}
            >
              {transitioning === "finalize" ? "Finalizando…" : "Finalizar"}
            </button>
            {#if (quote.pending_items ?? 0) > 0}
              <p class="hint warn">⚠ {quote.pending_items} peça(s) com material pendente</p>
            {/if}
          {/if}
          {#if quote.kind === "commercial" && quote.status === "orcado"}
            <button on:click={() => transition("approve")} disabled={transitioning === "approve"}>
              {transitioning === "approve" ? "Aprovando…" : "Aprovar"}
            </button>
          {/if}
          {#if quote.kind === "commercial" && quote.status === "aprovado"}
            <button on:click={openProduce} disabled={producing}>Produzir…</button>
          {/if}
          {#if quote.kind === "commercial" && quote.status === "produzido"}
            <button on:click={() => transition("deliver")} disabled={transitioning === "deliver"}>
              {transitioning === "deliver" ? "Entregando…" : "Entregar"}
            </button>
          {/if}

          <button class="ghost" on:click={openPdf}>Baixar PDF</button>

          {#if canCancel}
            <button class="danger" on:click={() => transition("cancel")} disabled={transitioning === "cancel"}>
              {transitioning === "cancel" ? "Cancelando…" : "Cancelar"}
            </button>
          {/if}
        </div>

        <dl class="timeline">
          <dt>Finalizado</dt><dd class="mono dim">{fmtDate(quote.finalized_at)}</dd>
          {#if quote.kind === "commercial"}
            <dt>Aprovado</dt><dd class="mono dim">{fmtDate(quote.approved_at)}</dd>
          {/if}
          <dt>Produzido</dt><dd class="mono dim">{fmtDate(quote.produced_at)}</dd>
          {#if quote.kind === "commercial"}
            <dt>Entregue</dt><dd class="mono dim">{fmtDate(quote.delivered_at)}</dd>
          {/if}
        </dl>
      </section>
    </aside>
  </div>
{/if}

{#if resolveItem}
  <div class="modal-backdrop" on:click|self={() => (resolveItem = null)}>
    <div class="modal">
      <h2>Resolver material pendente</h2>
      <p class="dim">
        O gcode declara material <strong class="mono">{resolveItem.pending_material_code ?? "?"}</strong>,
        que ainda não está cadastrado. Escolha um material existente ou crie um novo agora.
      </p>
      {#if resolveError}<div class="alert">{resolveError}</div>{/if}

      {#if !showQuickCreateMaterial}
        <label class="field">
          Material
          <select bind:value={resolveCode}>
            <option value="">— escolher —</option>
            {#each materials as m}
              <option value={m.material_code}>{m.name} ({m.material_code})</option>
            {/each}
          </select>
        </label>
        <p class="hint">
          Não está na lista? <button class="link" type="button" on:click={() => (showQuickCreateMaterial = true)}>Cadastrar {resolveItem.pending_material_code ?? "novo material"}</button>
        </p>
        <div class="modal-actions">
          <button class="ghost" on:click={() => (resolveItem = null)} disabled={resolving}>
            Cancelar
          </button>
          <button on:click={confirmResolve} disabled={resolving || !resolveCode}>
            {resolving ? "Salvando…" : "Aplicar"}
          </button>
        </div>
      {:else}
        <div class="form-grid">
          <label class="field">
            Código
            <input bind:value={qcName} placeholder="ex: PETG-CF" required />
          </label>
          <label class="field">
            Densidade (g/cm³)
            <input type="number" step="0.001" bind:value={qcDensity} required />
          </label>
          <label class="field">
            Preço por kg (R$)
            <input type="number" step="0.01" bind:value={qcPrice} required />
          </label>
          <label class="field">
            Taxa de falha (%)
            <input type="number" step="0.01" bind:value={qcFailure} required />
          </label>
        </div>
        {#if qcError}<div class="alert">{qcError}</div>{/if}
        <div class="modal-actions">
          <button class="ghost" on:click={() => (showQuickCreateMaterial = false)} disabled={qcSubmitting}>
            Voltar
          </button>
          <button on:click={quickCreateMaterial} disabled={qcSubmitting || !qcName}>
            {qcSubmitting ? "Criando…" : "Cadastrar"}
          </button>
        </div>
      {/if}
    </div>
  </div>
{/if}

{#if showProduceModal && quote}
  <div class="modal-backdrop" on:click|self={() => (showProduceModal = false)}>
    <div class="modal">
      <h2>Produzir orçamento</h2>
      <p class="dim">
        Atribua uma bobina (spool) por peça. O sistema vai debitar gramas e
        gravar o consumo real.
      </p>
      {#if produceError}<div class="alert">{produceError}</div>{/if}
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Peça</th><th>Material</th><th>Spool</th></tr>
          </thead>
          <tbody>
            {#each quote.items as it (it.id)}
              {@const matched = spoolsForItem(it.gcode_meta?.material)}
              <tr>
                <td>{it.name}</td>
                <td class="mono">{it.gcode_meta?.material ?? "—"}</td>
                <td>
                  <select bind:value={produceAssignments[it.id]}>
                    <option value="">—</option>
                    {#each matched as sp}
                      <option value={sp.id}>
                        {sp.material_code} · {fmtNum(sp.remaining_grams, 0)}g · {sp.supplier ?? "—"}
                      </option>
                    {/each}
                  </select>
                </td>
              </tr>
            {/each}
            {#if quote.items.length === 0}
              <tr><td colspan="3"><div class="empty">Nenhuma peça neste orçamento</div></td></tr>
            {/if}
          </tbody>
        </table>
      </div>
      <div class="modal-actions">
        <button class="ghost" on:click={() => (showProduceModal = false)} disabled={producing}>
          Cancelar
        </button>
        <button on:click={confirmProduce} disabled={producing || quote.items.length === 0}>
          {producing ? "Produzindo…" : "Confirmar produção"}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .page-head {
    margin-bottom: 1.5rem;
  }
  .head-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .head-tags {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.4rem;
  }
  .layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 1.5rem;
  }
  @media (max-width: 880px) {
    .layout {
      grid-template-columns: 1fr;
    }
  }
  .panel + .panel {
    margin-top: 1.5rem;
  }
  .side-col .panel + .panel {
    margin-top: 1.5rem;
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
  .empty {
    padding: 1.5rem 1rem;
    text-align: center;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.74rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }
  tr.pending td { background: rgba(245, 158, 11, 0.08); }
  .badge.pending {
    display: inline-block;
    margin-left: 0.4rem;
    padding: 0.05rem 0.4rem;
    border-radius: 999px;
    background: #fef3c7;
    color: #92400e;
    font-size: 0.7em;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
  }
  .hint.warn { color: #92400e; font-size: 0.85em; margin: 0.25rem 0 0; }
  .hint { color: #6b7280; font-size: 0.85em; }
  button.link {
    background: none;
    border: none;
    padding: 0;
    color: var(--brand, #111827);
    text-decoration: underline;
    cursor: pointer;
    font-size: inherit;
  }
  .ai-panel { border-left: 4px solid var(--brand); }
  .ai-actions { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0 0.6rem; }
  .ai-result {
    border-top: 1px dashed var(--line);
    padding-top: 0.6rem;
    margin-top: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .ai-result .tag {
    align-self: flex-start;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    padding: 0.1rem 0.4rem;
    border: 1px solid var(--line);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .ai-result .tag.muted { color: var(--muted); }
  .ai-result p { margin: 0; color: var(--ink); font-size: 0.92rem; }
  .ai-result .dim { color: var(--muted); }

  .variants-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .variants-list li {
    border-bottom: 1px dashed var(--line);
    padding-bottom: 0.4rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .variants-list .tag.brand {
    align-self: flex-start;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    padding: 0.1rem 0.4rem;
    background: var(--brand);
    color: var(--paper);
    text-transform: uppercase;
  }
  .variants-list .dim { color: var(--muted); font-size: 0.85em; }
  .item-form, .svc-form {
    grid-template-columns: 2fr 2fr 1fr;
  }
  .field.full {
    grid-column: 1 / -1;
  }
  .totals .kvs {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.5rem 1rem;
    margin: 0;
  }
  .totals .kvs dt {
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.7rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .totals .kvs dd {
    margin: 0;
    text-align: right;
  }
  .totals .kvs dt.big {
    color: var(--ink);
    font-family: var(--font-display);
    font-size: 1.05rem;
    text-transform: none;
    letter-spacing: -0.01em;
    border-top: 1px solid var(--line-strong);
    padding-top: 0.7rem;
    margin-top: 0.4rem;
  }
  .totals .kvs dd.big {
    font-size: 1.3rem;
    border-top: 1px solid var(--line-strong);
    padding-top: 0.7rem;
    margin-top: 0.4rem;
  }
  .vbtns {
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }
  .timeline {
    margin-top: 1.25rem;
    border-top: 1px dashed var(--line);
    padding-top: 1rem;
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0.45rem 1rem;
  }
  .timeline dt {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--muted);
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .timeline dd {
    margin: 0;
    text-align: right;
    font-size: 0.82rem;
  }
  .dim {
    color: var(--muted);
  }
  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 1.25rem;
  }
  a.btn {
    text-decoration: none;
    display: inline-block;
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
</style>
