<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type { Material } from "$lib/types";
  import { MATERIAL_TYPES } from "$lib/types";

  let rows: Material[] = [];
  let loading = true;
  let listError = "";

  // create form
  let material_type = "PLA";
  let name = "";
  let manufacturer = "";
  let color = "";
  let density_g_cm3 = "";
  let price_per_kg_ref = "";
  let failure_rate_pct = "0";
  let submitting = false;
  let formError = "";

  // edit (creates new SCD2 version) modal
  let editing: Material | null = null;
  let editError = "";
  let editSubmitting = false;

  // history modal
  let historyFor: Material | null = null;
  let history: Material[] = [];
  let historyLoading = false;
  let historyError = "";

  async function load() {
    loading = true;
    listError = "";
    try {
      rows = await api<Material[]>("/materials");
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar materiais.");
    } finally {
      loading = false;
    }
  }

  async function create() {
    formError = "";
    submitting = true;
    try {
      await api<Material>("/materials", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          material_type,
          name: name || `${material_type}${manufacturer ? " " + manufacturer : ""}${color ? " " + color : ""}`,
          manufacturer: manufacturer || null,
          color: color || null,
          density_g_cm3,
          price_per_kg_ref,
          failure_rate_pct: failure_rate_pct || "0",
        }),
      });
      name = manufacturer = color = density_g_cm3 = price_per_kg_ref = "";
      failure_rate_pct = "0";
      await load();
    } catch (err) {
      handleApiError(err);
      formError = errorMessage(err, "Não foi possível criar o material.");
    } finally {
      submitting = false;
    }
  }

  async function saveEdit() {
    if (!editing) return;
    editError = "";
    editSubmitting = true;
    try {
      await api<Material>(`/materials/${editing.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: editing.name,
          manufacturer: editing.manufacturer || null,
          color: editing.color || null,
          density_g_cm3: editing.density_g_cm3,
          price_per_kg_ref: editing.price_per_kg_ref,
          failure_rate_pct: editing.failure_rate_pct,
        }),
      });
      editing = null;
      await load();
    } catch (err) {
      handleApiError(err);
      editError = errorMessage(err, "Falha ao registrar nova versão.");
    } finally {
      editSubmitting = false;
    }
  }

  async function remove(m: Material) {
    const label = `${m.material_type}${m.manufacturer ? " · " + m.manufacturer : ""}${m.color ? " · " + m.color : ""}`;
    if (!confirm(`Remover ${label}? Só funciona se nunca tiver sido usado em orçamentos.`)) return;
    try {
      await api(`/materials/${m.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Não foi possível remover o material.");
    }
  }

  async function openHistory(m: Material) {
    historyFor = m;
    historyLoading = true;
    historyError = "";
    history = [];
    try {
      history = await api<Material[]>(`/materials/${m.id}/history`);
    } catch (err) {
      handleApiError(err);
      historyError = errorMessage(err, "Falha ao carregar histórico.");
    } finally {
      historyLoading = false;
    }
  }

  function fmtDate(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleDateString("pt-BR");
    } catch {
      return s;
    }
  }

  function fmtMaterial(m: Material): string {
    const parts = [m.material_type];
    if (m.manufacturer) parts.push(m.manufacturer);
    if (m.color) parts.push(m.color);
    return parts.join(" · ");
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
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
  {submitting}
  error={formError}
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
</Form>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">Versões atuais <span class="count">· {rows.length}</span></h2>
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "Carregando…" : "Atualizar"}
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
      {#if editError}<div class="alert">{editError}</div>{/if}
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
        <div class="actions">
          <button type="button" class="ghost" on:click={() => (editing = null)}>Cancelar</button>
          <button type="submit" disabled={editSubmitting}>
            {editSubmitting ? "Salvando…" : "Criar nova versão"}
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
      {#if historyError}<div class="alert">{historyError}</div>{/if}
      {#if historyLoading}
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
</style>
