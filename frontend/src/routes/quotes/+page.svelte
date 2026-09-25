<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import { money as fmtMoney, dateTime as fmtDate } from "$lib/format";
  import Table from "$lib/components/Table.svelte";
  import SearchBar from "$lib/components/SearchBar.svelte";
  import { countShown } from "$lib/table-search";
  import type { Client, Person, Quote, QuoteKind, QuoteStatus } from "$lib/types";
  import { quoteNumber } from "$lib/quote-number";

  // filters
  let fStatus: QuoteStatus | "" = "";
  let fKind: QuoteKind | "" = "";
  let fClient = "";

  $: quotesUrl = (() => {
    const qs = new URLSearchParams();
    if (fStatus) qs.set("status", fStatus);
    if (fKind) qs.set("kind", fKind);
    if (fClient) qs.set("client_id", fClient);
    return `/quotes${qs.toString() ? `?${qs}` : ""}`;
  })();
  const rows = resource(() => api<Quote[]>(quotesUrl), {
    initial: [], errorMessage: "Falha ao carregar orçamentos.", auto: false,
  });
  const clients = resource(() => api<Client[]>("/clients"), { initial: [], auto: false });
  const people = resource(() => api<Person[]>("/people"), { initial: [], auto: false });
  const togglePersonAction = action((quoteId: string, personIds: string[]) =>
    api<Quote>(`/quotes/${quoteId}/people`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ person_ids: personIds }),
    }),
  );

  // Clonar copia config comercial, peças (com gcode), fotos e pessoas — mas
  // nunca status/timeline/consumo. Copiar arquivos (fotos, gcode) leva tempo
  // perceptível: o `pending` do action() desabilita o botão enquanto a
  // requisição está em voo, senão um segundo clique impaciente cria um
  // segundo clone e a pessoa tem que caçar e apagar o duplicado.
  const clonar = action(
    (id: string) => api<Quote>(`/quotes/${id}/clone`, { method: "POST" }),
    { errorMessage: "Falha ao clonar o orçamento." },
  );

  // A `action()` é compartilhada pela lista inteira — só uma clonagem por
  // vez, de propósito. `cloningId` lembra qual linha disparou a que está em
  // voo, pra distinguir "esta linha está clonando" (rótulo já muda sozinho)
  // de "outra linha está clonando" (esta fica desabilitada sem nenhum sinal
  // visível — numa lista longa/filtrada a linha em voo pode nem estar na
  // tela — daí o `title` explicativo no botão das demais).
  let cloningId: string | null = null;

  async function clonarEAbrir(id: string) {
    cloningId = id;
    const novo = await clonar.run(id);
    cloningId = null;
    if (novo) await goto(`/quotes/${novo.id}`);
  }

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
    return ($clients.data ?? []).find((c) => c.id === id)?.name ?? "—";
  }

  function itemNames(q: Quote): string[] {
    return (q.items ?? []).map((it) => it.name).filter(Boolean);
  }

  // Resumo dos nomes das peças: até 3, depois "+N". Lista completa no title.
  function itemsSummary(q: Quote): string {
    const names = itemNames(q);
    if (names.length === 0) return "—";
    if (names.length <= 3) return names.join(" · ");
    return `${names.slice(0, 3).join(" · ")} +${names.length - 3}`;
  }

  // Linhas que a Table efetivamente recebe: mesmo objeto Quote, mais dois
  // campos derivados só pra virarem coluna — client_name (nome resolvido
  // do cliente, pro texto exibido/buscado E pra ordenação alfabética
  // correta; ordenar pela chave crua client_id ordenaria por UUID) e
  // items_summary (o resumo "até 3 + N" que já existia, agora como coluna
  // em vez de célula construída na mão). O resto dos campos do Quote
  // (id, kind, person_ids…) segue disponível pro slot "cell" da Table e
  // pro slot de ações.
  type ViewRow = Quote & { client_name: string; items_summary: string };
  $: viewRows = ($rows.data ?? []).map(
    (r): ViewRow => ({
      ...r,
      client_name: clientName(r.client_id),
      items_summary: itemsSummary(r),
    }),
  );

  let q = "";
  // seq/items_summary/kind/status marcam `cell: true` — a Table ainda usa
  // o `format` abaixo pra montar o texto de exibição/busca (é a base do
  // haystack, ver table-logic.ts), mas a apresentação real destas quatro
  // colunas vem do slot "cell" logo abaixo no template (tooltip com
  // UUID/lista completa, tag colorida de Tipo/Status, chips de pessoa).
  const columns = [
    {
      key: "seq",
      label: "#",
      mono: true,
      sortable: true,
      cell: true,
      format: (v: unknown) => quoteNumber(v as number),
    },
    { key: "items_summary", label: "Itens", width: "22rem", cell: true },
    {
      key: "kind",
      label: "Tipo",
      sortable: true,
      cell: true,
      format: (v: unknown) => (v === "commercial" ? "comercial" : "pessoal"),
    },
    {
      key: "status",
      label: "Status",
      sortable: true,
      cell: true,
      format: (v: unknown) => statusLabel(v as string),
    },
    { key: "client_name", label: "Cliente", sortable: true },
    {
      key: "total",
      label: "Total",
      mono: true,
      align: "right" as const,
      sortable: true,
      format: (v: unknown) => fmtMoney(v as string | number),
    },
    {
      key: "created_at",
      label: "Criado",
      mono: true,
      sortable: true,
      format: (v: unknown) => fmtDate(v as string),
    },
  ];
  // Notas não é coluna — entra na busca via searchExtra, igual ao combinado
  // no brief da tarefa.
  const searchExtra = (row: Record<string, unknown>) => (row as Quote).notes ?? "";
  $: mostrados = countShown(viewRows, q, columns, searchExtra);

  async function togglePerson(q: Quote, personId: string) {
    const current = new Set(q.person_ids ?? []);
    if (current.has(personId)) current.delete(personId);
    else current.add(personId);
    const updated = await togglePersonAction.run(q.id, [...current]);
    if (updated) rows.set(($rows.data ?? []).map((r) => (r.id === q.id ? updated : r)));
  }

  function resetFilters() {
    fStatus = "";
    fKind = "";
    fClient = "";
    rows.reload();
  }

  onMount(() => {
    if (requireAuth()) return;
    clients.reload();
    people.reload();
    rows.reload();
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
      <select bind:value={fStatus} on:change={() => rows.reload()}>
        <option value="">todos</option>
        {#each STATUS_OPTIONS as o}
          <option value={o.value}>{o.label}</option>
        {/each}
      </select>
    </label>
    <label class="field">
      Tipo
      <select bind:value={fKind} on:change={() => rows.reload()}>
        <option value="">todos</option>
        <option value="commercial">Comercial</option>
        <option value="personal">Pessoal</option>
      </select>
    </label>
    <label class="field">
      Cliente
      <select bind:value={fClient} on:change={() => rows.reload()}>
        <option value="">todos</option>
        {#each $clients.data ?? [] as c}
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
    <h2 class="section-title">Orçamentos <span class="count">· {($rows.data ?? []).length}</span></h2>
    <button class="tiny ghost" on:click={() => rows.reload()} disabled={$rows.loading}>
      {$rows.loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if $rows.error}<div class="alert">{$rows.error}</div>{/if}
  {#if $clonar.error}<div class="alert">{$clonar.error}</div>{/if}

  <SearchBar
    bind:value={q}
    total={($rows.data ?? []).length}
    shown={mostrados}
    placeholder="buscar por número, peça ou cliente…"
  />

  <Table
    {columns}
    rows={viewRows}
    searchText={q}
    {searchExtra}
    empty="Nenhum orçamento encontrado"
  >
    <!-- Slot "cell": restaura o markup rico que a Table (texto puro via
         format()) não conseguiria — tooltip com UUID/lista completa, tag
         colorida de Tipo/Status, e os chips de atribuição de pessoa, que
         precisam continuar dentro da célula Tipo pra manter o sentido de
         "este orçamento é destas pessoas" (não um botão de ação solto).
         `value` já é o mesmo texto formatado usado na busca (o format()
         de columns, acima) — os ramos abaixo só decidem como DESENHAR
         esse texto, nunca mudam o que a busca casa. Roda uma vez por
         coluna marcada `cell: true`, tanto no desktop quanto no card
         (é o mesmo slot da Table.svelte nos dois modos). -->
    <svelte:fragment slot="cell" let:row let:col let:value>
      {@const quote = row as ViewRow}
      {#if col.key === "seq"}
        <span title={quote.id}>{value}</span>
      {:else if col.key === "items_summary"}
        <span title={itemNames(quote).join(", ")}>{value}</span>
      {:else if col.key === "kind"}
        <span class="tag {quote.kind === 'commercial' ? 'brand' : 'muted'}">{value}</span>
        {#if quote.kind === "personal" && ($people.data ?? []).length > 0}
          <div class="people-chips">
            {#each ($people.data ?? []).filter((p) => p.active || (quote.person_ids ?? []).includes(p.id)) as p (p.id)}
              <button
                type="button"
                class="chip"
                class:on={(quote.person_ids ?? []).includes(p.id)}
                on:click={() => togglePerson(quote, p.id)}
              >
                {p.name}
              </button>
            {/each}
          </div>
        {/if}
      {:else if col.key === "status"}
        <span class="tag {statusClass(quote.status)}">{value}</span>
      {:else}
        {value}
      {/if}
    </svelte:fragment>
    <svelte:fragment slot="actions" let:row>
      {@const quote = row as ViewRow}
      <a class="tiny ghost btn" href={`/quotes/${quote.id}`}>abrir</a>
      <button
        type="button"
        class="tiny ghost"
        disabled={$clonar.pending}
        title={$clonar.pending && cloningId !== quote.id
          ? "Aguardando outra clonagem terminar…"
          : undefined}
        on:click={() => clonarEAbrir(quote.id)}
      >
        {$clonar.pending && cloningId === quote.id ? "clonando…" : "clonar"}
      </button>
    </svelte:fragment>
  </Table>
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
  .list-panel :global(.searchbar) {
    margin-bottom: 1rem;
  }
  .people-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    margin-top: 0.3rem;
  }
  /* .chip e .chip.on agora vivem em app.css (mesmos valores) */
  a.btn {
    text-decoration: none;
    display: inline-block;
  }
</style>
