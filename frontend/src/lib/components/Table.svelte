<script lang="ts">
  type Row = Record<string, unknown>;
  export let columns: {
    key: string;
    label: string;
    align?: "left" | "right" | "center";
    mono?: boolean;
    width?: string;
    format?: (v: unknown, row: Row) => string;
  }[];
  export let rows: Row[];
  export let rowKey: (r: Row) => string = (r) =>
    String((r as { id?: string }).id ?? JSON.stringify(r));
  export let empty: string = "Nenhum registro";
  export let dense = false;

  function display(col: (typeof columns)[number], row: Row): string {
    const v = (row as Record<string, unknown>)[col.key];
    if (col.format) return col.format(v, row);
    if (v === null || v === undefined || v === "") return "—";
    return String(v);
  }
</script>

<div class="table-wrap" class:dense>
  <table>
    <thead>
      <tr>
        {#each columns as c}
          <th class:right={c.align === "right"} class:center={c.align === "center"} style:width={c.width ?? "auto"}>
            <span>{c.label}</span>
          </th>
        {/each}
        {#if $$slots.actions}<th class="right actions-col"><span>Ações</span></th>{/if}
      </tr>
    </thead>
    <tbody>
      {#each rows as row (rowKey(row))}
        <tr>
          {#each columns as c}
            <td
              class:right={c.align === "right"}
              class:center={c.align === "center"}
              class:mono={c.mono}
            >
              {display(c, row)}
            </td>
          {/each}
          {#if $$slots.actions}
            <td class="right actions-cell">
              <slot name="actions" {row} />
            </td>
          {/if}
        </tr>
      {/each}
      {#if rows.length === 0}
        <tr>
          <td colspan={columns.length + ($$slots.actions ? 1 : 0)}>
            <div class="empty">{empty}</div>
          </td>
        </tr>
      {/if}
    </tbody>
  </table>
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
</style>
