<script lang="ts">
  import { onDestroy } from "svelte";

  export let value = "";
  export let total = 0;
  export let shown = 0;
  export let placeholder = "buscar…";

  let raw = value;
  let timer: ReturnType<typeof setTimeout>;

  // Resincroniza `raw` quando `value` muda por fora (ex.: um botão
  // "limpar filtros" da página escrevendo direto no valor bindado) — sem
  // isso o input ficaria mostrando texto que já não é mais o filtro
  // ativo. Como o próprio debounce escreve em `value` o mesmo texto que
  // já está em `raw`, essa atribuição é um no-op no caminho normal de
  // digitação.
  $: raw = value;

  function onInput(e: Event) {
    raw = (e.currentTarget as HTMLInputElement).value;
    clearTimeout(timer);
    timer = setTimeout(() => (value = raw), 150);
  }
  function limpar() {
    raw = "";
    clearTimeout(timer);
    value = "";
  }

  // Um timer pendente que dispara depois que o componente saiu de cena
  // escreveria em `value` de um pai que já navegou — daí o clearTimeout.
  onDestroy(() => clearTimeout(timer));
</script>

<div class="searchbar">
  <input type="search" {placeholder} value={raw} on:input={onInput} aria-label={placeholder} />
  {#if value}
    <span class="counter mono">{shown} de {total}</span>
    <button type="button" class="tiny ghost" on:click={limpar}>limpar</button>
  {/if}
</div>

<style>
  .searchbar {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .searchbar input {
    flex: 1 1 14rem;
    min-height: 44px;
    padding: 0.5rem 0.7rem;
    border: 1px solid var(--line-strong);
    background: var(--paper);
    font-family: inherit;
    font-size: 0.92rem;
  }
  .counter {
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    white-space: nowrap;
  }
</style>
