<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type { Service, ServiceKind, ServiceUnit } from "$lib/types";

  const UNITS: { value: ServiceUnit; label: string }[] = [
    { value: "min", label: "minuto" },
    { value: "hour", label: "hora" },
    { value: "g", label: "grama" },
  ];
  const KINDS: { value: ServiceKind; label: string }[] = [
    { value: "labor", label: "Mão de obra" },
    { value: "purge", label: "Purga (material)" },
    { value: "other", label: "Outro" },
  ];

  let rows: Service[] = [];
  let loading = true;
  let listError = "";

  let name = "";
  let unit: ServiceUnit = "hour";
  let default_rate = "";
  let kind: ServiceKind = "labor";
  let is_active = true;
  let submitting = false;
  let formError = "";

  let editing: Service | null = null;
  let editError = "";
  let editSubmitting = false;

  async function load() {
    loading = true;
    listError = "";
    try {
      rows = await api<Service[]>("/services");
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar serviços.");
    } finally {
      loading = false;
    }
  }

  async function create() {
    formError = "";
    submitting = true;
    try {
      await api<Service>("/services", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, unit, default_rate, kind, is_active }),
      });
      name = "";
      default_rate = "";
      unit = "hour";
      kind = "labor";
      is_active = true;
      await load();
    } catch (err) {
      handleApiError(err);
      formError = errorMessage(err, "Não foi possível criar o serviço.");
    } finally {
      submitting = false;
    }
  }

  async function saveEdit() {
    if (!editing) return;
    editError = "";
    editSubmitting = true;
    try {
      await api<Service>(`/services/${editing.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: editing.name,
          unit: editing.unit,
          default_rate: editing.default_rate,
          kind: editing.kind,
          is_active: editing.is_active,
        }),
      });
      editing = null;
      await load();
    } catch (err) {
      handleApiError(err);
      editError = errorMessage(err, "Falha ao salvar alterações.");
    } finally {
      editSubmitting = false;
    }
  }

  async function remove(id: string) {
    if (!confirm("Remover este serviço?")) return;
    try {
      await api(`/services/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao remover serviço.");
    }
  }

  function unitLabel(u: string): string {
    return UNITS.find((x) => x.value === u)?.label ?? u;
  }
  function kindLabel(k: string): string {
    return KINDS.find((x) => x.value === k)?.label ?? k;
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Cadastro / 03</span>
  <h1 class="page-title">Serviços<em>.</em></h1>
  <p class="page-lede">
    Mão de obra, purga e outros custos por minuto, hora ou grama. O <em>kind</em> determina onde aparece nos orçamentos.
  </p>
</header>

<Form
  eyebrow="Novo serviço"
  title="Adicionar item de serviço"
  submitLabel="Adicionar"
  {submitting}
  error={formError}
  on:submit={create}
>
  <label class="field">
    Nome
    <input bind:value={name} placeholder="Modelagem, acabamento…" required />
  </label>
  <label class="field">
    Unidade
    <select bind:value={unit}>
      {#each UNITS as u}<option value={u.value}>{u.label}</option>{/each}
    </select>
  </label>
  <label class="field">
    Taxa padrão (R$)
    <input bind:value={default_rate} type="number" step="0.01" min="0" required />
  </label>
  <label class="field">
    Tipo
    <select bind:value={kind}>
      {#each KINDS as k}<option value={k.value}>{k.label}</option>{/each}
    </select>
  </label>
  <label class="field check">
    Ativo
    <input type="checkbox" bind:checked={is_active} />
  </label>
</Form>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">Catálogo <span class="count">· {rows.length}</span></h2>
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}
  <Table
    columns={[
      { key: "name", label: "Nome" },
      { key: "kind", label: "Tipo", format: (v) => kindLabel(v as string) },
      { key: "unit", label: "Unidade", mono: true, format: (v) => unitLabel(v as string) },
      {
        key: "default_rate",
        label: "Taxa",
        mono: true,
        align: "right",
        format: (v) => `R$ ${v}`,
      },
      {
        key: "is_active",
        label: "Status",
        align: "center",
        format: (v) => (v ? "ativo" : "inativo"),
      },
    ]}
    {rows}
    empty="Nenhum serviço cadastrado"
  >
    <svelte:fragment slot="actions" let:row>
      <button class="tiny ghost" on:click={() => (editing = { ...(row as Service) })}>Editar</button>
      <button class="tiny danger" on:click={() => remove((row as Service).id)}>Excluir</button>
    </svelte:fragment>
  </Table>
</section>

{#if editing}
  <div class="modal-backdrop" on:click|self={() => (editing = null)}>
    <div class="modal">
      <h2>Editar serviço</h2>
      {#if editError}<div class="alert">{editError}</div>{/if}
      <form on:submit|preventDefault={saveEdit} class="form-grid">
        <label class="field">
          Nome
          <input bind:value={editing.name} required />
        </label>
        <label class="field">
          Unidade
          <select bind:value={editing.unit}>
            {#each UNITS as u}<option value={u.value}>{u.label}</option>{/each}
          </select>
        </label>
        <label class="field">
          Taxa (R$)
          <input bind:value={editing.default_rate} type="number" step="0.01" min="0" required />
        </label>
        <label class="field">
          Tipo
          <select bind:value={editing.kind}>
            {#each KINDS as k}<option value={k.value}>{k.label}</option>{/each}
          </select>
        </label>
        <label class="field check">
          Ativo
          <input type="checkbox" bind:checked={editing.is_active} />
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
  .field.check {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }
  .field.check input {
    width: auto;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }
</style>
