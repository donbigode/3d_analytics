<script lang="ts">
  import { sortRows, filterRows, nextDir, type SortDir } from "$lib/table-logic";
  import { DASH } from "$lib/format";

  type Row = Record<string, unknown>;
  export let columns: {
    key: string;
    label: string;
    align?: "left" | "right" | "center";
    mono?: boolean;
    width?: string;
    format?: (v: unknown, row: Row) => string;
    sortable?: boolean;
    // Marca que esta coluna quer passar pelo slot "cell" em vez do
    // display() padrão — célula com conteúdo rico (tag colorida, chips
    // clicáveis, o que for) que texto puro não consegue expressar.
    // Colunas sem esta flag seguem 100% inalteradas: o Table.svelte de
    // hoje é o comportamento padrão, nenhuma página precisa mudar nada
    // pra continuar funcionando.
    cell?: boolean;
  }[];
  export let rows: Row[];
  export let rowKey: (r: Row) => string = (r) =>
    String((r as { id?: string }).id ?? JSON.stringify(r));
  export let empty: string = "Nenhum registro";
  export let dense = false;
  export let searchText = "";
  export let searchExtra: ((row: Row) => string) | undefined = undefined;
  // Abaixo de 700px a tabela vira uma pilha de cards — mesma `columns`,
  // sem markup duplicado. Nenhuma coluna some: o card mostra todas.
  export let stackOnMobile = true;

  let sortKey: string | null = null;
  let sortDir: SortDir = null;

  function toggleSort(key: string) {
    if (sortKey !== key) {
      sortKey = key;
      sortDir = "asc";
      return;
    }
    sortDir = nextDir(sortDir);
    if (sortDir === null) sortKey = null;
  }

  function display(col: (typeof columns)[number], row: Row): string {
    const v = (row as Record<string, unknown>)[col.key];
    if (col.format) {
      // `filterRows` mantém a linha visível mesmo quando o haystack (que
      // chama display()) lança — mas isso só honra a promessa se o
      // caminho de desenho tratar o mesmo erro. Sem este try/catch, a
      // linha que a busca preservou derruba a tabela inteira ao renderizar,
      // trocando um defeito localizado (célula com travessão) por um em
      // branco na tela toda.
      try {
        return col.format(v, row);
      } catch (err) {
        console.warn("Table: format() da coluna lançou; célula mostrada como DASH", col.key, err);
        return DASH;
      }
    }
    if (v === null || v === undefined || v === "") return DASH;
    return String(v);
  }

  // O filtro casa sobre o texto já formatado de todas as colunas, mais o
  // que searchExtra trouxer (notas e afins, que não são coluna).
  function haystack(row: Row): string {
    const cols = columns.map((c) => display(c, row)).join(" ");
    return searchExtra ? `${cols} ${searchExtra(row)}` : cols;
  }

  $: visible = sortRows(filterRows(rows, searchText, haystack), sortKey, sortDir);
</script>

<div class="table-responsive" class:stack={stackOnMobile}>
  <div class="table-wrap" class:dense>
  <table>
    <thead>
      <tr>
        {#each columns as c}
          <th
            class:right={c.align === "right"}
            class:center={c.align === "center"}
            style:width={c.width ?? "auto"}
            aria-sort={c.sortable
              ? sortKey === c.key
                ? sortDir === "asc"
                  ? "ascending"
                  : "descending"
                : "none"
              : undefined}
          >
            {#if c.sortable}
              <button type="button" class="sort" on:click={() => toggleSort(c.key)}>
                <span>{c.label}</span>
                <span class="dir" aria-hidden="true"
                  >{sortKey === c.key ? (sortDir === "asc" ? "↑" : "↓") : ""}</span
                >
              </button>
            {:else}
              <span>{c.label}</span>
            {/if}
          </th>
        {/each}
        {#if $$slots.actions}<th class="right actions-col"><span>Ações</span></th>{/if}
      </tr>
    </thead>
    <tbody>
      {#each visible as row (rowKey(row))}
        <tr>
          {#each columns as c}
            <td
              class:right={c.align === "right"}
              class:center={c.align === "center"}
              class:mono={c.mono}
            >
              {#if c.cell}
                <slot name="cell" {row} col={c} value={display(c, row)}>{display(c, row)}</slot>
              {:else}
                {display(c, row)}
              {/if}
            </td>
          {/each}
          {#if $$slots.actions}
            <td class="right actions-cell">
              <slot name="actions" {row} />
            </td>
          {/if}
        </tr>
      {/each}
      {#if visible.length === 0}
        <tr>
          <td colspan={columns.length + ($$slots.actions ? 1 : 0)}>
            <div class="empty">{searchText ? "Nada encontrado para a busca" : empty}</div>
          </td>
        </tr>
      {/if}
    </tbody>
  </table>
  </div>
  {#if stackOnMobile}
    <div class="cards">
      {#each visible as row (rowKey(row))}
        <article class="card">
          {#each columns as c}
            <div class="card-row">
              <span class="card-label mono">{c.label}</span>
              <span class="card-value" class:mono={c.mono}>
                {#if c.cell}
                  <slot name="cell" {row} col={c} value={display(c, row)}>{display(c, row)}</slot>
                {:else}
                  {display(c, row)}
                {/if}
              </span>
            </div>
          {/each}
          {#if $$slots.actions}
            <div class="card-actions">
              <slot name="actions" {row} />
            </div>
          {/if}
        </article>
      {/each}
      {#if visible.length === 0}
        <div class="empty">{searchText ? "Nada encontrado para a busca" : empty}</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .table-wrap {
    border: 1px solid var(--line);
    background: var(--paper);
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
    white-space: nowrap;
  }
  thead th.right {
    text-align: right;
  }
  thead th.center {
    text-align: center;
  }
  thead th .sort {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    min-height: 44px;
    padding: 0;
    border: none;
    background: transparent;
    color: inherit;
    font: inherit;
    font-family: inherit;
    font-weight: inherit;
    font-size: inherit;
    letter-spacing: inherit;
    text-transform: inherit;
    cursor: pointer;
  }
  thead th .sort:hover {
    color: var(--ink);
  }
  thead th .sort:active {
    transform: none;
  }
  thead th.right .sort {
    justify-content: flex-end;
  }
  thead th.center .sort {
    justify-content: center;
  }
  thead th .dir {
    font-family: var(--font-mono);
  }
  tbody td {
    padding: 0.7rem 0.85rem;
    border-bottom: 1px solid var(--line);
    vertical-align: middle;
  }
  tbody tr:last-child td {
    border-bottom: none;
  }
  tbody tr:hover td {
    background: rgba(26, 26, 29, 0.025);
  }
  td.right {
    text-align: right;
  }
  td.center {
    text-align: center;
  }
  td.mono {
    font-family: var(--font-mono);
    font-size: 0.86rem;
  }
  .dense thead th,
  .dense tbody td {
    padding: 0.45rem 0.75rem;
  }
  .actions-cell {
    white-space: nowrap;
  }
  .actions-cell :global(button + button) {
    margin-left: 0.35rem;
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

  /* ---------- Modo card (abaixo de 700px) ----------
     Mesma `columns` da tabela, sem markup duplicado. Toda coluna aparece
     — nada some por largura, quem confere no bancada precisa do número
     inteiro. Alternado por classe no wrapper (não por :has() de irmão),
     pra não depender da ordem dos elementos no DOM. */
  .cards {
    display: none;
  }
  @media (max-width: 700px) {
    .table-responsive.stack .table-wrap {
      display: none;
    }
    .table-responsive.stack .cards {
      display: grid;
      gap: 0.75rem;
    }
  }
  .card {
    border: 1px solid var(--line);
    background: var(--paper);
    padding: 0.85rem 0.95rem;
  }
  .card-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--line);
  }
  .card-row:last-of-type {
    border-bottom: none;
  }
  .card-label {
    font-size: 0.66rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    flex: 0 0 auto;
  }
  .card-value {
    text-align: right;
    word-break: break-word;
  }
  .card-value.mono {
    font-family: var(--font-mono);
    font-size: 0.86rem;
  }
  .card-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    justify-content: flex-end;
    margin-top: 0.7rem;
    padding-top: 0.7rem;
    border-top: 1px dashed var(--line);
  }
</style>
