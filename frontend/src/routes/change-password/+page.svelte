<script lang="ts">
  import { goto } from "$app/navigation";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { action } from "$lib/resource";
  import { onMount } from "svelte";

  let current = "";
  let next = "";
  let confirm = "";
  let error = "";

  const changePasswordAction = action(
    (currentPassword: string, newPassword: string) =>
      api("/auth/change-password", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      }),
    { errorMessage: "Falha ao trocar senha." },
  );

  onMount(() => requireAuth());

  async function submit() {
    error = "";
    if (next !== confirm) {
      error = "As senhas não conferem.";
      return;
    }
    await changePasswordAction.run(current, next);
    if ($changePasswordAction.error) {
      error = $changePasswordAction.error;
      return;
    }
    goto("/");
  }
</script>

<header class="page-head">
  <span class="page-eyebrow">Conta · 00</span>
  <h1 class="page-title">Trocar senha<em>.</em></h1>
  <p class="page-lede">
    Defina uma senha pessoal antes de continuar usando o sistema.
  </p>
</header>

<section class="panel">
  <form class="form-grid" on:submit|preventDefault={submit}>
    <label class="field full">
      Senha atual
      <input type="password" bind:value={current} autocomplete="current-password" required />
    </label>
    <label class="field full">
      Nova senha (mín. 8 chars, letras + números)
      <input type="password" bind:value={next} autocomplete="new-password" required />
    </label>
    <label class="field full">
      Confirmar nova senha
      <input type="password" bind:value={confirm} autocomplete="new-password" required />
    </label>
    {#if error}<p class="alert">{error}</p>{/if}
    <div class="actions">
      <button type="submit" disabled={$changePasswordAction.pending || !current || !next || !confirm}>
        {$changePasswordAction.pending ? "Salvando…" : "Salvar e continuar"}
      </button>
    </div>
  </form>
</section>

<style>
  .page-head { margin-bottom: 1.5rem; }
  .page-head em { color: var(--brand); font-style: italic; }
</style>
