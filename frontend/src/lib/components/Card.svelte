<script lang="ts">
  export let eyebrow: string = "";
  export let label: string;
  export let value: string;
  export let hint: string = "";
  export let accent: boolean = false;
  export let tone: "default" | "ok" | "warn" | "muted" = "default";
</script>

<article class="card" class:accent class:ok={tone === "ok"} class:warn={tone === "warn"} class:muted={tone === "muted"}>
  {#if eyebrow}<span class="card-eyebrow">{eyebrow}</span>{/if}
  <span class="card-label">{label}</span>
  <span class="card-value mono">{value}</span>
  {#if hint}<span class="card-hint">{hint}</span>{/if}
  <slot />
</article>

<style>
  .card {
    background: var(--paper);
    border: 1px solid var(--line);
    padding: 1.1rem 1.15rem 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
    position: relative;
    min-height: 124px;
  }
  .card::before {
    content: "";
    position: absolute;
    inset: 0 auto 0 0;
    width: 3px;
    background: transparent;
  }
  .card.accent::before {
    background: var(--brand);
  }
  .card.ok::before {
    background: var(--ok);
  }
  .card.warn::before {
    background: var(--danger);
  }
  .card-eyebrow {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .card-label {
    font-size: 0.78rem;
    color: var(--muted);
  }
  .card-value {
    font-family: var(--font-display);
    font-weight: 500;
    font-size: 1.7rem;
    line-height: 1;
    letter-spacing: -0.01em;
    color: var(--ink);
  }
  .card.warn .card-value {
    color: var(--danger);
  }
  .card.ok .card-value {
    color: var(--ok);
  }
  .card-hint {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--muted);
    letter-spacing: 0.04em;
  }
</style>
