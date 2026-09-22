<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import { appSettings } from "$lib/stores/settings";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type { Spool, SpoolStatus, Material } from "$lib/types";

  const STATUS: { value: SpoolStatus; label: string }[] = [
    { value: "open", label: "Aberto" },
    { value: "empty", label: "Vazio" },
    { value: "discarded", label: "Descartado" },
  ];

  type SpoolsData = { spools: Spool[]; materials: Material[] };
  const dataRes = resource<SpoolsData>(
    async () => {
      const [s, m] = await Promise.all([api<Spool[]>("/spools"), api<Material[]>("/materials")]);
      return { spools: s, materials: m };
    },
    { initial: { spools: [], materials: [] }, errorMessage: "Falha ao carregar bobinas.", auto: false },
  );
  $: rows = $dataRes.data?.spools ?? [];
  $: materials = $dataRes.data?.materials ?? [];
  // Pré-seleciona o primeiro material do catálogo no formulário de criação
  // assim que a carga chegar — mesmo efeito que o load() fazia antes.
  $: if (!material_id && materials[0]) material_id = materials[0].id;

  const deleteAction = action((id: string) => api(`/spools/${id}`, { method: "DELETE" }), {
    errorMessage: "Não foi possível excluir a bobina.",
  });
  // O alerta da lista e o alerta do modal de edição dividem o erro de
  // exclusão (a exclusão pode ser disparada da linha OU de dentro do modal
  // aberto) — mostra em só um lugar por vez, igual ao if/else original.
  $: listError = $dataRes.error || (editing ? "" : $deleteAction.error);
  $: busy = $editAction.pending || $deleteAction.pending;
  function reloadSpools() {
    deleteAction.reset();
    return dataRes.reload();
  }

  let material_id = "";
  let purchased_from = "";
  let purchase_url = "";
  let purchased_at = new Date().toISOString().slice(0, 10);
  let purchased_price = "";
  let initial_grams = "";
  let remaining_grams = "";
  let status: SpoolStatus = "open";
  let notes = "";
  const createAction = action(
    (body: Record<string, unknown>) =>
      api<Spool>("/spools", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Não foi possível registrar a bobina." },
  );

  let editing: Spool | null = null;
  let editMaterialId = "";
  const editAction = action(
    (id: string, body: Record<string, unknown>) =>
      api<Spool>(`/spools/${id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao salvar bobina." },
  );

  function openEdit(row: Spool) {
    editing = { ...row };
    editAction.reset();
    deleteAction.reset();
    // Pre-select the catalog material that best matches this spool's snapshot
    // (type + color + manufacturer), so editing carries the full identity.
    const exact = materials.find(
      (m) =>
        m.material_type === row.material_type &&
        (m.color ?? null) === (row.color ?? null) &&
        (m.manufacturer ?? null) === (row.manufacturer ?? null),
    );
    editMaterialId =
      exact?.id ?? materials.find((m) => m.material_type === row.material_type)?.id ?? "";
  }

  function applyEditMaterial() {
    const mat = materials.find((m) => m.id === editMaterialId);
    if (!editing || !mat) return;
    editing.material_type = mat.material_type;
    editing.color = mat.color ?? null;
    editing.manufacturer = mat.manufacturer ?? null;
  }

  $: lowThreshold = Number($appSettings?.low_spool_threshold_g ?? 0);

  async function create() {
    const mat = materials.find((m) => m.id === material_id);
    const created = await createAction.run({
      material_type: mat?.material_type ?? "",
      color: mat?.color ?? null,
      manufacturer: mat?.manufacturer ?? null,
      purchased_from: purchased_from || null,
      purchase_url: purchase_url || null,
      purchased_at: new Date(purchased_at).toISOString(),
      purchased_price,
      initial_grams,
      remaining_grams: remaining_grams || initial_grams,
      status,
      notes: notes || null,
    });
    if (!created) return;
    purchased_from = purchase_url = purchased_price = initial_grams = remaining_grams = notes = "";
    status = "open";
    purchased_at = new Date().toISOString().slice(0, 10);
    await reloadSpools();
  }

  async function saveEdit() {
    if (!editing) return;
    const updated = await editAction.run(editing.id, {
      material_type: editing.material_type,
      color: editing.color || null,
      manufacturer: editing.manufacturer || null,
      purchased_from: editing.purchased_from || null,
      purchase_url: editing.purchase_url || null,
      purchased_at: editing.purchased_at,
      purchased_price: editing.purchased_price,
      initial_grams: editing.initial_grams,
      remaining_grams: editing.remaining_grams,
      status: editing.status,
      notes: editing.notes || null,
    });
    if (!updated) return;
    editing = null;
    await reloadSpools();
  }

  async function deleteSpool(sp: Spool) {
    if (!confirm("Excluir esta bobina? Se ela já foi consumida em uma produção, prefira marcá-la como Descartada.")) return;
    await deleteAction.run(sp.id);
    if ($deleteAction.error) return;
    if (editing?.id === sp.id) editing = null;
    await dataRes.reload();
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
    reloadSpools();
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
  submitting={$createAction.pending}
  error={$createAction.error}
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
    <button class="tiny ghost" on:click={reloadSpools} disabled={$dataRes.loading}>
      {$dataRes.loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}
  <Table
    columns={[
      {
        key: "material_type",
        label: "Material",
        mono: true,
        format: (_v, row) =>
          `${row.material_type}${row.manufacturer ? ` · ${row.manufacturer}` : ""}`,
      },
      { key: "color", label: "Cor" },
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
      <button class="tiny ghost" on:click={() => openEdit(row as Spool)}>Ajustar</button>
      <button class="tiny danger" on:click={() => deleteSpool(row as Spool)} disabled={busy}>Excluir</button>
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
            <span class="muted">· {r.color ?? r.purchased_from ?? "—"}</span>
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
      {#if $editAction.error || $deleteAction.error}<div class="alert">{$editAction.error || $deleteAction.error}</div>{/if}
      <form on:submit|preventDefault={saveEdit} class="form-grid">
        <label class="field">
          Material
          <select bind:value={editMaterialId} on:change={applyEditMaterial}>
            {#each materials as m}
              <option value={m.id}>
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
          <button type="button" class="danger" on:click={() => editing && deleteSpool(editing)} disabled={busy}>
            Excluir
          </button>
          <span class="spacer"></span>
          <button type="button" class="ghost" on:click={() => (editing = null)}>Cancelar</button>
          <button type="submit" disabled={busy}>
            {busy ? "Salvando…" : "Salvar"}
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
  .actions .spacer {
    flex: 1;
  }
</style>
