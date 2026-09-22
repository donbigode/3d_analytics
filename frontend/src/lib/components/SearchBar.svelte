<script lang="ts">
  export let value = "";
  export let total = 0;
  export let shown = 0;
  export let placeholder = "buscar…";

  let raw = value;
  let timer: ReturnType<typeof setTimeout>;

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
