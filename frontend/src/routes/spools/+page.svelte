<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import { appSettings } from "$lib/stores/settings";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type { Spool, SpoolStatus, Material } from "$lib/types";

  const STATUS: { value: SpoolStatus; label: string }[] = [
    { value: "open", label: "Aberto" },
    { value: "empty", label: "Vazio" },
    { value: "discarded", label: "Descartado" },
  ];

  let rows: Spool[] = [];
  let materials: Material[] = [];
  let loading = true;
  let listError = "";

  let material_id = "";
  let purchased_from = "";
  let purchase_url = "";
  let purchased_at = new Date().toISOString().slice(0, 10);
  let purchased_price = "";
  let initial_grams = "";
  let remaining_grams = "";
  let status: SpoolStatus = "open";
  let notes = "";
  let submitting = false;
  let formError = "";

  let editing: Spool | null = null;
  let editError = "";
  let editSubmitting = false;

  $: lowThreshold = Number($appSettings?.low_spool_threshold_g ?? 0);

  async function load() {
    loading = true;
    listError = "";
    try {
      const [s, m] = await Promise.all([
        api<Spool[]>("/spools"),
        api<Material[]>("/materials"),
      ]);
      rows = s;
      materials = m;
      if (!material_id && materials[0]) material_id = materials[0].id;
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar bobinas.");
    } finally {
      loading = false;
    }
  }

  async function create() {
    formError = "";
    submitting = true;
    try {
      const mat = materials.find((m) => m.id === material_id);
      await api<Spool>("/spools", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          material_type: mat?.material_type ?? "",
          purchased_from: purchased_from || null,
          purchase_url: purchase_url || null,
          purchased_at: new Date(purchased_at).toISOString(),
          purchased_price,
          initial_grams,
          remaining_grams: remaining_grams || initial_grams,
          status,
          notes: notes || null,
        }),
      });
      purchased_from = purchase_url = purchased_price = initial_grams = remaining_grams = notes = "";
      status = "open";
      purchased_at = new Date().toISOString().slice(0, 10);
      await load();
    } catch (err) {
      handleApiError(err);
      formError = errorMessage(err, "Não foi possível registrar a bobina.");
    } finally {
      submitting = false;
    }
  }

  async function saveEdit() {
    if (!editing) return;
    editError = "";
    editSubmitting = true;
    try {
      await api<Spool>(`/spools/${editing.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          material_type: editing.material_type,
          purchased_from: editing.purchased_from || null,
          purchase_url: editing.purchase_url || null,
          purchased_at: editing.purchased_at,
          purchased_price: editing.purchased_price,
          initial_grams: editing.initial_grams,
          remaining_grams: editing.remaining_grams,
          status: editing.status,
          notes: editing.notes || null,
        }),
      });
      editing = null;
      await load();
    } catch (err) {
      handleApiError(err);
      editError = errorMessage(err, "Falha ao salvar bobina.");
    } finally {
      editSubmitting = false;
    }
  }

  function pctRemaining(r: Spool): number {
    const init = Number(r.initial_grams) || 1;
    const left = Number(r.remaining_grams) || 0;
    return Math.max(0, Math.min(100, (left / init) * 100));
  }

  function statusLabel(v: string): string {
    return STATUS.find((s) => s.value === v)?.label ?? v;
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Cadastro / 04</span>
  <h1 class="page-title">Estoque de bobinas<em>.</em></h1>
  <p class="page-lede">
    Cada bobina física entra aqui com peso inicial e preço pago. O consumo real registrado pelos orçamentos é
    descontado de <span class="mono">remaining_grams</span>.
  </p>
</header>

<Form
  eyebrow="Nova bobina"
  title="Registrar bobina"
  submitLabel="Adicionar"
  {submitting}
  error={formError}
  allowSubmit={materials.length > 0}
  on:submit={create}
>
  <label class="field">
    Material
    <select bind:value={material_id} required>
      {#each materials as m}
        <option value={m.id}>
          {m.material_type}{m.manufacturer ? ` · ${m.manufacturer}` : ""}{m.color ? ` · ${m.color}` : ""}
        </option>
      {/each}
    </select>
  </label>
  <label class="field">
    Onde comprou
    <input bind:value={purchased_from} placeholder="3D Lab, Voolt, MercadoLivre…" />
  </label>
  <label class="field full">
    Link da compra (opcional)
    <input bind:value={purchase_url} type="url" placeholder="https://…" />
  </label>
  <label class="field">
    Comprado em
    <input type="date" bind:value={purchased_at} required />
  </label>
  <label class="field">
    Preço pago (R$)
    <input bind:value={purchased_price} type="number" step="0.01" min="0" required />
  </label>
  <label class="field">
    Peso inicial (g)
    <input bind:value={initial_grams} type="number" step="1" min="0" required />
  </label>
  <label class="field">
    Restante agora (g)
    <input bind:value={remaining_grams} type="number" step="1" min="0" placeholder="igual ao inicial" />
  </label>
  <label class="field">
    Status
    <select bind:value={status}>
      {#each STATUS as s}<option value={s.value}>{s.label}</option>{/each}
    </select>
  </label>
  <label class="field full">
    Notas
    <input bind:value={notes} />
  </label>
  {#if materials.length === 0}
    <div class="alert" style="grid-column: 1 / -1;">
      Cadastre ao menos um <a href="/materials">material</a> antes de registrar bobinas.
    </div>
  {/if}
</Form>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">
      Bobinas <span class="count">· {rows.length}</span>
      {#if lowThreshold > 0}
        <span class="threshold mono">limiar: {lowThreshold}g</span>
      {/if}
    </h2>
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}
  <Table
    columns={[
      { key: "material_type", label: "Material", mono: true, width: "10ch" },
      { key: "purchased_from", label: "Comprado em" },
      {
        key: "remaining_grams",
        label: "Restante (g)",
        mono: true,
        align: "right",
        format: (v) => String(v),
      },
      {
        key: "initial_grams",
        label: "Inicial (g)",
        mono: true,
        align: "right",
        format: (v) => String(v),
      },
      { key: "status", label: "Status", align: "center", format: (v) => statusLabel(v as string) },
    ]}
    {rows}
    empty="Nenhuma bobina registrada"
  >
    <svelte:fragment slot="actions" let:row>
      <button class="tiny ghost" on:click={() => (editing = { ...(row as Spool) })}>Ajustar</button>
    </svelte:fragment>
  </Table>

  {#if rows.length > 0}
    <div class="bars">
      {#each rows as r (r.id)}
        {@const pct = pctRemaining(r)}
        {@const low = lowThreshold > 0 && Number(r.remaining_grams) <= lowThreshold}
        <div class="bar-row" class:low>
          <div class="bar-label">
            <span class="mono">{r.material_type}</span>
            <span class="muted">· {r.purchased_from ?? "—"}</span>
          </div>
          <div class="bar-track" aria-hidden="true">
            <div class="bar-fill" style:width="{pct}%"></div>
          </div>
          <div class="bar-value mono">{r.remaining_grams}g · {pct.toFixed(0)}%</div>
        </div>
      {/each}
    </div>
  {/if}
</section>

{#if editing}
  <div class="modal-backdrop" on:click|self={() => (editing = null)}>
    <div class="modal">
      <h2>Ajustar bobina</h2>
      {#if editError}<div class="alert">{editError}</div>{/if}
      <form on:submit|preventDefault={saveEdit} class="form-grid">
        <label class="field">
          Material
          <select bind:value={editing.material_type}>
            {#each materials as m}
              <option value={m.material_type}>
                {m.material_type}{m.manufacturer ? ` · ${m.manufacturer}` : ""}{m.color ? ` · ${m.color}` : ""}
              </option>
            {/each}
          </select>
        </label>
        <label class="field">
          Onde comprou
          <input bind:value={editing.purchased_from} />
        </label>
        <label class="field full">
          Link da compra
          <input bind:value={editing.purchase_url} type="url" />
        </label>
        <label class="field">
          Comprado em
          <input
            type="date"
            value={editing.purchased_at?.slice(0, 10)}
            on:input={(e) => editing && (editing.purchased_at = new Date((e.target as HTMLInputElement).value).toISOString())}
          />
        </label>
        <label class="field">
          Preço pago (R$)
          <input bind:value={editing.purchased_price} type="number" step="0.01" min="0" />
        </label>
        <label class="field">
          Peso inicial (g)
          <input bind:value={editing.initial_grams} type="number" step="1" min="0" />
        </label>
        <label class="field">
          Restante (g)
          <input bind:value={editing.remaining_grams} type="number" step="1" min="0" />
        </label>
        <label class="field">
          Status
          <select bind:value={editing.status}>
            {#each STATUS as s}<option value={s.value}>{s.label}</option>{/each}
          </select>
        </label>
        <label class="field full">
          Notas
          <input bind:value={editing.notes} />
        </label>
        <div class="actions">
          <button type="button" class="ghost" on:click={() => (editing = null)}>Cancelar</button>
          <button type="submit" disabled={editSubmitting}>
            {editSubmitting ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<style>
  .page-head {
    margin-bottom: 2rem;
  }
  .list-panel {
    margin-top: 2rem;
  }
  .field.full {
    grid-column: 1 / -1;
  }
  .threshold {
    margin-left: 0.6rem;
    font-size: 0.65rem;
    color: var(--muted);
    text-transform: none;
    letter-spacing: 0.08em;
  }
  .bars {
    display: grid;
    gap: 0.4rem;
    margin-top: 1.5rem;
    padding-top: 1.25rem;
    border-top: 1px dashed var(--line);
  }
  .bar-row {
    display: grid;
    grid-template-columns: minmax(180px, 1fr) minmax(120px, 2fr) auto;
    gap: 0.75rem;
    align-items: center;
  }
  .bar-label {
    font-size: 0.85rem;
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
  }
  .bar-label .muted {
    color: var(--muted);
    font-size: 0.78rem;
  }
  .bar-track {
    background: var(--line);
    height: 6px;
    position: relative;
  }
  .bar-fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: var(--ink);
    transition: width 250ms ease;
  }
  .bar-row.low .bar-fill {
    background: var(--danger);
  }
  .bar-value {
    font-size: 0.78rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .bar-row.low .bar-value {
    color: var(--danger);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }
</style>
