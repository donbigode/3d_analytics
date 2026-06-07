<script lang="ts">
  export let stages: { label: string; value: number }[] = [];

  $: max = Math.max(1, ...stages.map((s) => s.value));
</script>

<div class="funnel" role="list">
  {#each stages as s, i (s.label)}
    {@const w = Math.max(0.04, s.value / max)}
    <div class="row" role="listitem">
      <div class="bar-wrap">
        <div class="bar" style:--w={`${(w * 100).toFixed(2)}%`}>
          <span class="bar-value mono">{s.value}</span>
        </div>
      </div>
      <div class="meta">
        <span class="step mono">{String(i + 1).padStart(2, "0")}</span>
        <span class="label">{s.label}</span>
      </div>
    </div>
  {/each}
  {#if stages.length === 0}
    <p class="empty">sem dados</p>
  {/if}
</div>

<style>
  .funnel {
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }
  .row {
    display: grid;
    grid-template-columns: 1fr 160px;
    gap: 0.85rem;
    align-items: center;
  }
  .bar-wrap {
    background: rgba(26, 26, 29, 0.04);
    border: 1px solid var(--line);
    height: 32px;
    position: relative;
    overflow: hidden;
  }
  .bar {
    background: var(--brand);
    height: 100%;
    width: var(--w);
    transition: width 240ms ease;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding-right: 0.6rem;
  }
  .bar-value {
    color: #fff;
    font-size: 0.78rem;
    letter-spacing: 0.05em;
  }
  .meta {
    display: flex;
    align-items: baseline;
    gap: 0.55rem;
  }
  .step {
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    color: var(--muted);
  }
  .label {
    font-size: 0.85rem;
    color: var(--ink);
  }
  .empty {
    margin: 0;
    padding: 1.2rem;
    text-align: center;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.74rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
  }
  @media (max-width: 540px) {
    .row {
      grid-template-columns: 1fr;
      gap: 0.25rem;
    }
  }
</style>
