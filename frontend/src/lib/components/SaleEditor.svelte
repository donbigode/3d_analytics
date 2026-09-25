<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { Sale } from "$lib/types";

  // Popover de registro de venda: a data deixa de ser um efeito colateral do
  // clique (antes o PATCH gravava date.today() em silêncio) e vira um campo
  // que a pessoa vê e pode mudar antes de salvar.
  export let sale: Sale;
  export let pending = false;

  const dispatch = createEventDispatcher<{
    save: { sold_at: string; confirmed_revenue: string };
    cancel: void;
  }>();

  const hoje = new Date().toISOString().slice(0, 10);
  let soldAt = sale.sold_at ?? hoje;
  let receita = String(sale.confirmed_revenue ?? sale.quote_total);

  const mesCorrente = hoje.slice(0, 7);
  // Editar a data de uma venda para um mês anterior mexe num DRE já fechado.
  // É o comportamento pedido pelo usuário, mas a tela precisa avisar antes
  // de salvar — não só deixar acontecer.
  $: avisaRetroativo = soldAt.length > 0 && soldAt.slice(0, 7) < mesCorrente;

  function salvar() {
    if (pending || !soldAt) return;
    dispatch("save", { sold_at: soldAt, confirmed_revenue: receita });
  }
</script>

<div class="sale-editor" role="dialog" aria-label="Registrar venda">
  <label class="field">
    Data da venda
    <input type="date" bind:value={soldAt} required />
  </label>
  <label class="field">
    Receita confirmada
    <input type="number" step="0.01" min="0" bind:value={receita} />
  </label>
  {#if avisaRetroativo}
    <p class="hint warn mono">
      Data em mês anterior ao atual — o DRE daquele mês será recalculado.
    </p>
  {/if}
  <div class="actions">
    <button type="button" class="tiny ghost" disabled={pending} on:click={() => dispatch("cancel")}>
      cancelar
    </button>
    <button type="button" class="tiny" disabled={pending || !soldAt} on:click={salvar}>
      {pending ? "Salvando…" : "salvar"}
    </button>
  </div>
</div>

<style>
  .sale-editor {
    display: grid;
    gap: 0.55rem;
    padding: 0.85rem;
    border: 1px solid var(--line-strong);
    background: var(--paper);
    min-width: 15rem;
    text-align: left;
  }
  .sale-editor .field input {
    padding: 0.35rem 0.5rem;
    font-size: 0.82rem;
  }
  .actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
    margin-top: 0.15rem;
  }
  .hint {
    margin: 0;
    font-size: 0.66rem;
    letter-spacing: 0.04em;
    line-height: 1.4;
  }
  .hint.warn {
    color: var(--danger);
  }
</style>
