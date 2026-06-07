<script lang="ts">
  import { createEventDispatcher } from "svelte";

  export let title: string = "";
  export let eyebrow: string = "";
  export let submitLabel: string = "Salvar";
  export let submitting: boolean = false;
  export let error: string = "";
  export let success: string = "";
  export let allowSubmit: boolean = true;

  const dispatch = createEventDispatcher<{ submit: void }>();

  function onSubmit() {
    if (!allowSubmit || submitting) return;
    dispatch("submit");
  }
</script>

<form on:submit|preventDefault={onSubmit} class="panel">
  {#if title || eyebrow}
    <div class="panel-head">
      <div class="heading">
        {#if eyebrow}<span class="page-eyebrow">{eyebrow}</span>{/if}
        {#if title}<h2 class="form-title">{title}</h2>{/if}
      </div>
      <slot name="head-extra" />
    </div>
  {/if}

  {#if error}<div class="alert">{error}</div>{/if}
  {#if success}<div class="alert ok">{success}</div>{/if}

  <div class="form-grid">
    <slot />
    <div class="actions">
      <slot name="actions">
        <button type="submit" disabled={submitting || !allowSubmit}>
          {submitting ? "Salvando…" : submitLabel}
        </button>
      </slot>
    </div>
  </div>
</form>

<style>
  .heading {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .form-title {
    margin: 0;
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.25rem;
    letter-spacing: -0.01em;
  }
</style>
