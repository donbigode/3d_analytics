<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import { date as fmtDate } from "$lib/format";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type { Material } from "$lib/types";
  import { MATERIAL_TYPES } from "$lib/types";

  const materialsRes = resource(() => api<Material[]>("/materials"), {
    initial: [], errorMessage: "Falha ao carregar materiais.", auto: false,
  });
  $: rows = $materialsRes.data ?? [];
  const removeAction = action((id: string) => api(`/materials/${id}`, { method: "DELETE" }), {
    errorMessage: "Não foi possível remover o material.",
  });
  // Um "Atualizar" bem-sucedido não pode deixar preso o erro de uma remoção
  // que falhou antes — os dois dividem o mesmo alerta do painel.
  $: listError = $materialsRes.error || $removeAction.error;
  function reloadMaterials() {
    removeAction.reset();
    return materialsRes.reload();
  }

  // create form
  let material_type = "PLA";
  let name = "";
  let manufacturer = "";
  let color = "";
  let density_g_cm3 = "";
  let price_per_kg_ref = "";
  let failure_rate_pct = "0";
  let single_color_waste_pct = "2";
  let multi_color_waste_pct = "20";
  const createAction = action(
    (body: Record<string, unknown>) =>
      api<Material>("/materials", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Não foi possível criar o material." },
  );

  // edit (creates new SCD2 version) modal
  let editing: Material | null = null;
  const editAction = action(
    (id: string, body: Record<string, unknown>) =>
      api<Material>(`/materials/${id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao registrar nova versão." },
  );

  // history modal
  let historyFor: Material | null = null;
  let history: Material[] = [];
  const historyAction = action((id: string) => api<Material[]>(`/materials/${id}/history`), {
    errorMessage: "Falha ao carregar histórico.",
  });

  async function create() {
    const created = await createAction.run({
      material_type,
      name: name || `${material_type}${manufacturer ? " " + manufacturer : ""}${color ? " " + color : ""}`,
      manufacturer: manufacturer || null,
      color: color || null,
      density_g_cm3,
      price_per_kg_ref,
      failure_rate_pct: failure_rate_pct || "0",
      single_color_waste_pct: single_color_waste_pct || "2",
      multi_color_waste_pct: multi_color_waste_pct || "20",
    });
    if (!created) return;
    name = manufacturer = color = density_g_cm3 = price_per_kg_ref = "";
    failure_rate_pct = "0";
    single_color_waste_pct = "2";
    multi_color_waste_pct = "20";
    await reloadMaterials();
  }

  async function saveEdit() {
    if (!editing) return;
    const updated = await editAction.run(editing.id, {
      name: editing.name,
      manufacturer: editing.manufacturer || null,
      color: editing.color || null,
      density_g_cm3: editing.density_g_cm3,
      price_per_kg_ref: editing.price_per_kg_ref,
      failure_rate_pct: editing.failure_rate_pct,
      single_color_waste_pct: editing.single_color_waste_pct,
      multi_color_waste_pct: editing.multi_color_waste_pct,
    });
    if (!updated) return;
    editing = null;
    await reloadMaterials();
  }

  async function remove(m: Material) {
    const label = `${m.material_type}${m.manufacturer ? " · " + m.manufacturer : ""}${m.color ? " · " + m.color : ""}`;
    if (!confirm(`Remover ${label}? Só funciona se nunca tiver sido usado em orçamentos.`)) return;
    await removeAction.run(m.id);
    if (!$removeAction.error) await materialsRes.reload();
  }

  async function openHistory(m: Material) {
    historyFor = m;
    history = [];
    const res = await historyAction.run(m.id);
    if (res) history = res;
  }

  function fmtMaterial(m: Material): string {
    const parts = [m.material_type];
    if (m.manufacturer) parts.push(m.manufacturer);
    if (m.color) parts.push(m.color);
    return parts.join(" · ");
  }

  onMount(() => {
    if (requireAuth()) return;
    reloadMaterials();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Cadastro / 02</span>
  <h1 class="page-title">Materiais<em>.</em></h1>
  <p class="page-lede">
    Cada material é único por <strong>tipo + fabricante + cor</strong>. O tipo
    é o que casa com o gcode (PLA, PETG…); fabricante e cor distinguem
    produtos físicos diferentes. Edições mantém histórico via
    <span class="mono">SCD2</span>: a versão vigente é encerrada e uma nova é
    aberta, preservando o preço dos orçamentos antigos.
  </p>
</header>

<Form
  eyebrow="Novo material"
  title="Cadastrar produto"
  submitLabel="Criar versão inicial"
  submitting={$createAction.pending}
  error={$createAction.error}
  on:submit={create}
>
  <label class="field">
    Tipo
    <select bind:value={material_type} required>
      {#each MATERIAL_TYPES as t}
        <option value={t}>{t}</option>
      {/each}
    </select>
  </label>
  <label class="field">
    Fabricante
    <input bind:value={manufacturer} placeholder="Voolt, Esun, 3DFila…" />
  </label>
  <label class="field">
    Cor
    <input bind:value={color} placeholder="Preto, Branco, Translúcido, Galaxy…" />
  </label>
  <label class="field">
    Nome (opcional — preenchido por padrão)
    <input bind:value={name} placeholder="PLA Voolt Preto" />
  </label>
  <label class="field">
    Densidade (g/cm³)
    <input bind:value={density_g_cm3} type="number" step="0.001" min="0" placeholder="1.24" required />
  </label>
  <label class="field">
    Preço de referência (R$/kg)
    <input bind:value={price_per_kg_ref} type="number" step="0.01" min="0" placeholder="120.00" required />
  </label>
  <label class="field">
    Taxa de falha (%)
    <input bind:value={failure_rate_pct} type="number" step="0.1" min="0" max="100" />
  </label>
  <label class="field">
    Refugo · 1 cor (%)
    <input bind:value={single_color_waste_pct} type="number" step="0.1" min="0" max="100" />
    <small class="hint">Brim + skirt + 1ª camada. Tipicamente 1–4%.</small>
  </label>
  <label class="field">
    Refugo · multicolor (%)
    <input bind:value={multi_color_waste_pct} type="number" step="0.1" min="0" max="100" />
    <small class="hint">Purga/wipe tower a cada troca de cor. 15–35%.</small>
  </label>
</Form>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">Versões atuais <span class="count">· {rows.length}</span></h2>
    <button class="tiny ghost" on:click={reloadMaterials} disabled={$materialsRes.loading}>
      {$materialsRes.loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}
  <Table
    columns={[
      { key: "material_type", label: "Tipo", mono: true, width: "10ch" },
      { key: "manufacturer", label: "Fabricante" },
      { key: "color", label: "Cor" },
      { key: "density_g_cm3", label: "Densidade", mono: true, align: "right", format: (v) => `${v} g/cm³` },
      { key: "price_per_kg_ref", label: "Preço ref.", mono: true, align: "right", format: (v) => `R$ ${v}/kg` },
      { key: "failure_rate_pct", label: "Falha", mono: true, align: "right", format: (v) => `${v}%` },
      { key: "effective_from", label: "Vigente desde", mono: true, format: (v) => fmtDate(v as string) },
    ]}
    {rows}
    rowKey={(r) => (r as Material).id}
    empty="Nenhum material cadastrado"
  >
    <svelte:fragment slot="actions" let:row>
      <button class="tiny ghost" on:click={() => openHistory(row as Material)}>Histórico</button>
      <button class="tiny ghost" on:click={() => (editing = { ...(row as Material) })}>Editar</button>
      <button class="tiny danger" on:click={() => remove(row as Material)}>Excluir</button>
    </svelte:fragment>
  </Table>
</section>

{#if editing}
  <div class="modal-backdrop" on:click|self={() => (editing = null)}>
    <div class="modal">
      <h2>Nova versão · <span class="mono">{fmtMaterial(editing)}</span></h2>
      <p class="page-lede">
        Salvar criará uma nova versão SCD2. A vigente é encerrada agora.
      </p>
      {#if $editAction.error}<div class="alert">{$editAction.error}</div>{/if}
      <form on:submit|preventDefault={saveEdit} class="form-grid">
        <label class="field">
          Nome
          <input bind:value={editing.name} required />
        </label>
        <label class="field">
          Fabricante
          <input bind:value={editing.manufacturer} />
        </label>
        <label class="field">
          Cor
          <input bind:value={editing.color} />
        </label>
        <label class="field">
          Densidade (g/cm³)
          <input bind:value={editing.density_g_cm3} type="number" step="0.001" min="0" required />
        </label>
        <label class="field">
          Preço ref. (R$/kg)
          <input bind:value={editing.price_per_kg_ref} type="number" step="0.01" min="0" required />
        </label>
        <label class="field">
          Taxa de falha (%)
          <input bind:value={editing.failure_rate_pct} type="number" step="0.1" min="0" max="100" required />
        </label>
        <label class="field">
          Refugo · 1 cor (%)
          <input bind:value={editing.single_color_waste_pct} type="number" step="0.1" min="0" max="100" required />
        </label>
        <label class="field">
          Refugo · multicolor (%)
          <input bind:value={editing.multi_color_waste_pct} type="number" step="0.1" min="0" max="100" required />
        </label>
        <div class="actions">
          <button type="button" class="ghost" on:click={() => (editing = null)}>Cancelar</button>
          <button type="submit" disabled={$editAction.pending}>
            {$editAction.pending ? "Salvando…" : "Criar nova versão"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if historyFor}
  <div class="modal-backdrop" on:click|self={() => (historyFor = null)}>
    <div class="modal">
      <h2>Histórico · <span class="mono">{fmtMaterial(historyFor)}</span></h2>
      {#if $historyAction.error}<div class="alert">{$historyAction.error}</div>{/if}
      {#if $historyAction.pending}
        <p class="empty">Carregando…</p>
      {:else}
        <Table
          dense
          columns={[
            { key: "name", label: "Nome" },
            { key: "density_g_cm3", label: "Densidade", mono: true, align: "right" },
            { key: "price_per_kg_ref", label: "Preço (R$/kg)", mono: true, align: "right" },
            { key: "failure_rate_pct", label: "Falha %", mono: true, align: "right" },
            { key: "effective_from", label: "Desde", mono: true, format: (v) => fmtDate(v as string) },
            { key: "effective_to", label: "Até", mono: true, format: (v) => fmtDate(v as string) },
            {
              key: "is_current",
              label: "Status",
              align: "center",
              format: (v) => (v ? "vigente" : "histórica"),
            },
          ]}
          rows={history}
          empty="Sem versões"
        />
        <div class="actions" style="margin-top: 1rem;">
          <button class="ghost" on:click={() => (historyFor = null)}>Fechar</button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .page-head { margin-bottom: 2rem; }
  .list-panel { margin-top: 2rem; }
  .actions { display: flex; justify-content: flex-end; }
  /* Override local: .hint aqui nunca teve cor própria (cinza-mudo é novo em
     app.css); mantém herdada pra não mudar a aparência desta página */
  .hint { color: inherit; }
</style>
