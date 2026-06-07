<script lang="ts">
  export let slices: { label: string; value: number }[] = [];
  export let size: number = 180;

  const PALETTE = ["#111827", "#3b3b53", "#7a7596", "#b9b3c7"];

  $: total = slices.reduce((a, s) => a + Math.max(0, s.value), 0);
  $: cx = size / 2;
  $: cy = size / 2;
  $: r = size / 2 - 4;
  $: innerR = r * 0.55;

  function arcPath(startA: number, endA: number, outer: number, inner: number) {
    const sx1 = cx + outer * Math.cos(startA);
    const sy1 = cy + outer * Math.sin(startA);
    const ex1 = cx + outer * Math.cos(endA);
    const ey1 = cy + outer * Math.sin(endA);
    const sx2 = cx + inner * Math.cos(endA);
    const sy2 = cy + inner * Math.sin(endA);
    const ex2 = cx + inner * Math.cos(startA);
    const ey2 = cy + inner * Math.sin(startA);
    const large = endA - startA > Math.PI ? 1 : 0;
    return `M ${sx1} ${sy1} A ${outer} ${outer} 0 ${large} 1 ${ex1} ${ey1} L ${sx2} ${sy2} A ${inner} ${inner} 0 ${large} 0 ${ex2} ${ey2} Z`;
  }

  $: positiveSlices = slices.filter((s) => s.value > 0);
  $: arcs = (() => {
    if (total <= 0) return [];
    let acc = -Math.PI / 2;
    return positiveSlices.map((s, i) => {
      const frac = s.value / total;
      const start = acc;
      const end = acc + frac * Math.PI * 2;
      acc = end;
      return {
        d: arcPath(start, end, r, innerR),
        color: PALETTE[i % PALETTE.length],
        label: s.label,
        value: s.value,
        pct: frac * 100,
      };
    });
  })();
</script>

<div class="pie">
  {#if total > 0}
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="pizza">
      {#each arcs as a, i (a.label)}
        <path d={a.d} fill={a.color}>
          <title>{a.label}: {a.value.toFixed(2)} ({a.pct.toFixed(1)}%)</title>
        </path>
      {/each}
    </svg>
    <ul class="legend">
      {#each arcs as a}
        <li>
          <span class="dot" style:background={a.color}></span>
          <span class="label">{a.label}</span>
          <span class="value mono">{a.pct.toFixed(1)}%</span>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="empty">sem dados</p>
  {/if}
</div>

<style>
  .pie {
    display: flex;
    align-items: center;
    gap: 1.2rem;
    flex-wrap: wrap;
  }
  .legend {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    min-width: 0;
    flex: 1;
  }
  .legend li {
    display: grid;
    grid-template-columns: 12px 1fr auto;
    align-items: center;
    gap: 0.55rem;
    font-size: 0.85rem;
  }
  .dot {
    width: 10px;
    height: 10px;
    display: inline-block;
  }
  .label {
    color: var(--ink);
  }
  .value {
    color: var(--muted);
    font-size: 0.78rem;
  }
  .empty {
    margin: 0;
    padding: 2rem 1rem;
    text-align: center;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.74rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    flex: 1;
  }
</style>
