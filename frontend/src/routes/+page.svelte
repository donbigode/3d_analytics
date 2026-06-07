<script lang="ts">
  import { user } from "$lib/stores/user";
</script>

{#if !$user}
  <p>Faça login: <a href="/login">/login</a></p>
{:else}
  <h1>Dashboard</h1>
  <p>Bem-vindo, {$user.name}.</p>
  <p>Conteúdo virá na Wave 3.</p>
{/if}
