<script lang="ts">
  import { api } from "$lib/api";

  let email = "";
  let password = "";
  let err = "";

  async function submit() {
    err = "";
    try {
      await api("/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      location.href = "/";
    } catch {
      err = "credenciais inválidas";
    }
  }
</script>

<form on:submit|preventDefault={submit}>
  <h1>Entrar</h1>
  <input bind:value={email} type="email" placeholder="email" autocomplete="email" required />
  <input bind:value={password} type="password" placeholder="senha" autocomplete="current-password" required />
  <button type="submit">Entrar</button>
  {#if err}<p class="err">{err}</p>{/if}
</form>

<style>
  form {
    max-width: 320px;
    margin: 4rem auto;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  h1 {
    margin: 0 0 0.5rem 0;
  }
  .err {
    color: #b91c1c;
    margin: 0;
  }
</style>
