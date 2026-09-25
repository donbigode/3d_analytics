<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import Table from "$lib/components/Table.svelte";
  import SearchBar from "$lib/components/SearchBar.svelte";
  import Form from "$lib/components/Form.svelte";
  import { countShown } from "$lib/table-search";
  import type { Client } from "$lib/types";

  const clientsRes = resource(() => api<Client[]>("/clients"), {
    initial: [], errorMessage: "Falha ao carregar clientes.", auto: false,
  });
  $: rows = $clientsRes.data ?? [];

  // Nome e contato (telefone/e-mail) — já são colunas da tabela, então a
  // busca padrão da Table já cobre os dois. `q` é só o texto do filtro.
  let q = "";
  const columns = [
    { key: "name", label: "Nome", sortable: true },
    { key: "phone", label: "Telefone", mono: true },
    { key: "email", label: "E-mail", mono: true },
    { key: "notes", label: "Notas" },
  ];
  $: mostrados = countShown(rows, q, columns);
  const removeAction = action((id: string) => api(`/clients/${id}`, { method: "DELETE" }), {
    errorMessage: "Falha ao remover cliente.",
  });
  // Um "Atualizar" bem-sucedido não pode deixar preso o erro de uma remoção
  // que falhou antes — os dois dividem o mesmo alerta do painel.
  $: listError = $clientsRes.error || $removeAction.error;
  function reloadClients() {
    removeAction.reset();
    return clientsRes.reload();
  }

  // create form
  let name = "";
  let phone = "";
  let email = "";
  let notes = "";
  const createAction = action(
    (body: Record<string, unknown>) =>
      api<Client>("/clients", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Não foi possível adicionar o cliente." },
  );

  // edit modal
  let editing: Client | null = null;
  const editAction = action(
    (id: string, body: Record<string, unknown>) =>
      api<Client>(`/clients/${id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao salvar alterações." },
  );

  async function create() {
    const created = await createAction.run({
      name,
      phone: phone || null,
      email: email || null,
      notes: notes || null,
    });
    if (!created) return;
    name = phone = email = notes = "";
    await reloadClients();
  }

  async function saveEdit() {
    if (!editing) return;
    const updated = await editAction.run(editing.id, {
      name: editing.name,
      phone: editing.phone || null,
      email: editing.email || null,
      notes: editing.notes || null,
    });
    if (!updated) return;
    editing = null;
    await reloadClients();
  }

  async function remove(id: string) {
    if (!confirm("Remover este cliente?")) return;
    await removeAction.run(id);
    if (!$removeAction.error) await clientsRes.reload();
  }

  onMount(() => {
    if (requireAuth()) return;
    reloadClients();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Cadastro / 01</span>
  <h1 class="page-title">Clientes<em>.</em></h1>
  <p class="page-lede">Pessoas e empresas para quem você emite orçamentos. Os dados aqui aparecem em PDFs e relatórios.</p>
</header>

<Form
  eyebrow="Novo registro"
  title="Adicionar cliente"
  submitLabel="Adicionar"
  submitting={$createAction.pending}
  error={$createAction.error}
  on:submit={create}
>
  <label class="field">
    Nome
    <input bind:value={name} placeholder="Nome ou razão social" required />
  </label>
  <label class="field">
    Telefone
    <input bind:value={phone} placeholder="(00) 00000-0000" />
  </label>
  <label class="field">
    E-mail
    <input bind:value={email} placeholder="contato@exemplo.com" type="email" />
  </label>
  <label class="field full">
    Notas
    <input bind:value={notes} placeholder="Observações internas" />
  </label>
</Form>

<section class="panel list-panel">
  <div class="panel-head">
    <h2 class="section-title">Cadastros <span class="count">· {rows.length}</span></h2>
    <button class="tiny ghost" on:click={reloadClients} disabled={$clientsRes.loading}>
      {$clientsRes.loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}
  <SearchBar
    bind:value={q}
    total={rows.length}
    shown={mostrados}
    placeholder="buscar por nome, telefone ou e-mail…"
  />
  <Table
    {columns}
    {rows}
    searchText={q}
    empty="Nenhum cliente cadastrado"
  >
    <svelte:fragment slot="actions" let:row>
      <button class="tiny ghost" on:click={() => (editing = { ...(row as Client) })}>Editar</button>
      <button class="tiny danger" on:click={() => remove((row as Client).id)}>Excluir</button>
    </svelte:fragment>
  </Table>
</section>

{#if editing}
  <div class="modal-backdrop" on:click|self={() => (editing = null)}>
    <div class="modal">
      <h2>Editar cliente</h2>
      {#if $editAction.error}<div class="alert">{$editAction.error}</div>{/if}
      <form on:submit|preventDefault={saveEdit} class="form-grid">
        <label class="field">
          Nome
          <input bind:value={editing.name} required />
        </label>
        <label class="field">
          Telefone
          <input bind:value={editing.phone} />
        </label>
        <label class="field">
          E-mail
          <input type="email" bind:value={editing.email} />
        </label>
        <label class="field">
          Notas
          <input bind:value={editing.notes} />
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
  .list-panel :global(.searchbar) {
    margin-bottom: 1rem;
  }
  .field.full {
    grid-column: 1 / -1;
  }
</style>
