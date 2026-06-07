<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import Table from "$lib/components/Table.svelte";
  import Form from "$lib/components/Form.svelte";
  import type { Client } from "$lib/types";

  let rows: Client[] = [];
  let loading = true;
  let listError = "";

  // create form
  let name = "";
  let phone = "";
  let email = "";
  let notes = "";
  let submitting = false;
  let formError = "";

  // edit modal
  let editing: Client | null = null;
  let editError = "";
  let editSubmitting = false;

  async function load() {
    loading = true;
    listError = "";
    try {
      rows = await api<Client[]>("/clients");
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar clientes.");
    } finally {
      loading = false;
    }
  }

  async function create() {
    formError = "";
    submitting = true;
    try {
      await api<Client>("/clients", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name,
          phone: phone || null,
          email: email || null,
          notes: notes || null,
        }),
      });
      name = phone = email = notes = "";
      await load();
    } catch (err) {
      handleApiError(err);
      formError = errorMessage(err, "Não foi possível adicionar o cliente.");
    } finally {
      submitting = false;
    }
  }

  async function saveEdit() {
    if (!editing) return;
    editError = "";
    editSubmitting = true;
    try {
      await api<Client>(`/clients/${editing.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          name: editing.name,
          phone: editing.phone || null,
          email: editing.email || null,
          notes: editing.notes || null,
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
    if (!confirm("Remover este cliente?")) return;
    try {
      await api(`/clients/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao remover cliente.");
    }
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
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
  {submitting}
  error={formError}
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
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "Carregando…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<div class="alert">{listError}</div>{/if}
  <Table
    columns={[
      { key: "name", label: "Nome" },
      { key: "phone", label: "Telefone", mono: true },
      { key: "email", label: "E-mail", mono: true },
      { key: "notes", label: "Notas" },
    ]}
    {rows}
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
      {#if editError}<div class="alert">{editError}</div>{/if}
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
</style>
