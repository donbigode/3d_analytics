<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
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

  const servicesRes = resource(() => api<Service[]>("/services"), {
    initial: [], errorMessage: "Falha ao carregar serviços.", auto: false,
  });
  $: rows = $servicesRes.data ?? [];
  const removeAction = action((id: string) => api(`/services/${id}`, { method: "DELETE" }), {
    errorMessage: "Falha ao remover serviço.",
  });
  // Um "Atualizar" bem-sucedido não pode deixar preso o erro de uma remoção
  // que falhou antes — os dois dividem o mesmo alerta do painel.
  $: listError = $servicesRes.error || $removeAction.error;
  function reloadServices() {
    removeAction.reset();
    return servicesRes.reload();
  }

  let name = "";
  let unit: ServiceUnit = "hour";
  let default_rate = "";
  let kind: ServiceKind = "labor";
  let is_active = true;
  const createAction = action(
    (body: Record<string, unknown>) =>
      api<Service>("/services", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Não foi possível criar o serviço." },
  );

  let editing: Service | null = null;
  const editAction = action(
    (id: string, body: Record<string, unknown>) =>
      api<Service>(`/services/${id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao salvar alterações." },
  );

  async function create() {
    const created = await createAction.run({ name, unit, default_rate, kind, is_active });
    if (!created) return;
    name = "";
    default_rate = "";
    unit = "hour";
    kind = "labor";
    is_active = true;
    await reloadServices();
  }

  async function saveEdit() {
    if (!editing) return;
    const updated = await editAction.run(editing.id, {
      name: editing.name,
      unit: editing.unit,
      default_rate: editing.default_rate,
      kind: editing.kind,
      is_active: editing.is_active,
    });
    if (!updated) return;
    editing = null;
    await reloadServices();
  }

  async function remove(id: string) {
    if (!confirm("Remover este serviço?")) return;
    await removeAction.run(id);
    if (!$removeAction.error) await servicesRes.reload();
  }

  function unitLabel(u: string): string {
    return UNITS.find((x) => x.value === u)?.label ?? u;
  }
  function kindLabel(k: string): string {
    return KINDS.find((x) => x.value === k)?.label ?? k;
  }

  onMount(() => {
    if (requireAuth()) return;
    reloadServices();
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
  submitting={$createAction.pending}
  error={$createAction.error}
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
    <button class="tiny ghost" on:click={reloadServices} disabled={$servicesRes.loading}>
      {$servicesRes.loading ? "Carregando…" : "Atualizar"}
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
      {#if $editAction.error}<div class="alert">{$editAction.error}</div>{/if}
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
          <button type="submit" disabled={$editAction.pending}>
            {$editAction.pending ? "Salvando…" : "Salvar"}
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
