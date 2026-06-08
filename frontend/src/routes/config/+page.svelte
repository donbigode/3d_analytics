<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";

  type Providers = {
    preferred_llm_provider: string;
    llm_suggestions_enabled: boolean;
    anthropic_configured: boolean;
    anthropic_key_preview: string | null;
    gemini_configured: boolean;
    gemini_key_preview: string | null;
    openai_configured: boolean;
    openai_key_preview: string | null;
    meli_configured: boolean;
    meli_app_id_preview: string | null;
    meli_secret_preview: string | null;
    meli_token_active: boolean;
  };

  let providers: Providers | null = null;
  let loading = true;
  let pageError = "";

  // form drafts
  let anthropicInput = "";
  let geminiInput = "";
  let openaiInput = "";
  let meliAppIdInput = "";
  let meliSecretInput = "";
  let preferred = "anthropic";
  let suggestionsEnabled = false;
  let saving = false;
  let saveOk = false;
  let saveError = "";

  async function load() {
    loading = true;
    pageError = "";
    try {
      providers = await api<Providers>("/config/providers");
      preferred = providers.preferred_llm_provider;
      suggestionsEnabled = providers.llm_suggestions_enabled;
    } catch (err) {
      handleApiError(err);
      pageError = errorMessage(err, "Falha ao carregar configurações.");
    } finally {
      loading = false;
    }
  }

  async function save(updates: Record<string, unknown>) {
    saving = true;
    saveError = "";
    saveOk = false;
    try {
      providers = await api<Providers>("/config/providers", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(updates),
      });
      preferred = providers.preferred_llm_provider;
      suggestionsEnabled = providers.llm_suggestions_enabled;
      saveOk = true;
    } catch (err) {
      handleApiError(err);
      saveError = errorMessage(err, "Falha ao salvar.");
    } finally {
      saving = false;
    }
  }

  async function saveAnthropic() {
    await save({ anthropic_api_key: anthropicInput });
    if (!saveError) anthropicInput = "";
  }
  async function clearAnthropic() {
    await save({ anthropic_api_key: "" });
  }
  async function saveGemini() {
    await save({ gemini_api_key: geminiInput });
    if (!saveError) geminiInput = "";
  }
  async function clearGemini() {
    await save({ gemini_api_key: "" });
  }
  async function saveOpenai() {
    await save({ openai_api_key: openaiInput });
    if (!saveError) openaiInput = "";
  }
  async function clearOpenai() {
    await save({ openai_api_key: "" });
  }
  async function saveMeli() {
    const payload: Record<string, unknown> = {};
    if (meliAppIdInput) payload.meli_app_id = meliAppIdInput;
    if (meliSecretInput) payload.meli_client_secret = meliSecretInput;
    if (Object.keys(payload).length === 0) return;
    await save(payload);
    if (!saveError) {
      meliAppIdInput = "";
      meliSecretInput = "";
    }
  }
  async function clearMeli() {
    await save({ meli_app_id: "", meli_client_secret: "" });
  }
  async function savePrefs() {
    await save({
      preferred_llm_provider: preferred,
      llm_suggestions_enabled: suggestionsEnabled,
    });
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Configuração / 09 · integrações</span>
  <h1 class="page-title">Integrações<em>.</em></h1>
  <p class="page-lede">
    Chaves de API dos provedores LLM e fontes externas usadas pelo radar
    de tendências. Os valores ficam mascarados após salvar — informe a chave
    nova pra trocar; deixe em branco e clique "Limpar" pra remover.
  </p>
</header>

{#if pageError}<div class="banner alert">{pageError}</div>{/if}
{#if saveOk}<div class="banner ok">Salvo.</div>{/if}
{#if saveError}<div class="banner alert">{saveError}</div>{/if}

{#if loading}
  <p class="empty">Carregando…</p>
{:else if providers}
  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">LLM · Anthropic</span>
      <h2 class="section-title">Claude</h2>
    </div>
    <p class="status mono">
      Status:
      <strong class:on={providers.anthropic_configured}>
        {providers.anthropic_configured ? "configurada" : "não configurada"}
      </strong>
      {#if providers.anthropic_key_preview}· <span class="mask">{providers.anthropic_key_preview}</span>{/if}
    </p>
    <div class="form-grid">
      <label class="field full">
        Nova chave de API
        <input bind:value={anthropicInput} type="password" placeholder="sk-ant-..." autocomplete="off" />
      </label>
    </div>
    <div class="actions">
      <button on:click={saveAnthropic} disabled={saving || !anthropicInput}>
        {saving ? "Salvando…" : "Salvar Anthropic"}
      </button>
      {#if providers.anthropic_configured}
        <button class="ghost danger" on:click={clearAnthropic} disabled={saving}>Limpar</button>
      {/if}
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">LLM · Google</span>
      <h2 class="section-title">Gemini</h2>
    </div>
    <p class="status mono">
      Status:
      <strong class:on={providers.gemini_configured}>
        {providers.gemini_configured ? "configurada" : "não configurada"}
      </strong>
      {#if providers.gemini_key_preview}· <span class="mask">{providers.gemini_key_preview}</span>{/if}
    </p>
    <div class="form-grid">
      <label class="field full">
        Nova chave de API
        <input bind:value={geminiInput} type="password" placeholder="AIza..." autocomplete="off" />
      </label>
    </div>
    <div class="actions">
      <button on:click={saveGemini} disabled={saving || !geminiInput}>
        {saving ? "Salvando…" : "Salvar Gemini"}
      </button>
      {#if providers.gemini_configured}
        <button class="ghost danger" on:click={clearGemini} disabled={saving}>Limpar</button>
      {/if}
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">LLM · OpenAI</span>
      <h2 class="section-title">GPT</h2>
    </div>
    <p class="status mono">
      Status:
      <strong class:on={providers.openai_configured}>
        {providers.openai_configured ? "configurada" : "não configurada"}
      </strong>
      {#if providers.openai_key_preview}· <span class="mask">{providers.openai_key_preview}</span>{/if}
    </p>
    <div class="form-grid">
      <label class="field full">
        Nova chave de API
        <input bind:value={openaiInput} type="password" placeholder="sk-..." autocomplete="off" />
      </label>
    </div>
    <div class="actions">
      <button on:click={saveOpenai} disabled={saving || !openaiInput}>
        {saving ? "Salvando…" : "Salvar OpenAI"}
      </button>
      {#if providers.openai_configured}
        <button class="ghost danger" on:click={clearOpenai} disabled={saving}>Limpar</button>
      {/if}
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">Marketplace · Mercado Livre</span>
      <h2 class="section-title">App OAuth (client_credentials)</h2>
    </div>
    <p class="status mono">
      Status:
      <strong class:on={providers.meli_configured}>
        {providers.meli_configured ? "configurado" : "não configurado"}
      </strong>
      {#if providers.meli_app_id_preview}
        · App ID <span class="mask">{providers.meli_app_id_preview}</span>
      {/if}
      {#if providers.meli_token_active}
        · <span class="mask token-on">token ativo</span>
      {/if}
    </p>
    <p class="hint">
      A API pública do ML exige OAuth desde 2024. Crie uma app em
      <a href="https://developers.mercadolivre.com.br/devcenter" target="_blank" rel="noreferrer">developers.mercadolivre.com.br/devcenter</a>
      e cole o <strong>App ID</strong> + <strong>Client Secret</strong> aqui.
      O sistema obtém o access token automaticamente.
    </p>
    <div class="form-grid">
      <label class="field">
        App ID
        <input bind:value={meliAppIdInput} placeholder="ex: 1234567890" autocomplete="off" />
      </label>
      <label class="field">
        Client Secret
        <input bind:value={meliSecretInput} type="password" placeholder="cole o secret" autocomplete="off" />
      </label>
    </div>
    <div class="actions">
      <button on:click={saveMeli} disabled={saving || (!meliAppIdInput && !meliSecretInput)}>
        {saving ? "Salvando…" : "Salvar Mercado Livre"}
      </button>
      {#if providers.meli_configured}
        <button class="ghost danger" on:click={clearMeli} disabled={saving}>Limpar</button>
      {/if}
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">Preferências</span>
      <h2 class="section-title">Coleta diária do radar</h2>
    </div>
    <div class="form-grid">
      <label class="field">
        Provider preferido
        <select bind:value={preferred}>
          <option value="anthropic">Anthropic (Claude)</option>
          <option value="gemini">Google Gemini</option>
          <option value="openai">OpenAI (GPT)</option>
        </select>
      </label>
      <label class="field check">
        <input type="checkbox" bind:checked={suggestionsEnabled} />
        Coletar sugestões automaticamente (1x/dia)
      </label>
    </div>
    <div class="actions">
      <button on:click={savePrefs} disabled={saving}>
        {saving ? "Salvando…" : "Salvar preferências"}
      </button>
    </div>
    <p class="hint">
      Mesmo com a coleta desligada, você pode forçar uma rodada manual pelo
      botão "Coletar agora" em <a href="/trends">Tendências</a>.
    </p>
  </section>
{/if}

<style>
  .page-head { margin-bottom: 1.5rem; }
  .page-head em { color: var(--brand); font-style: italic; }
  .banner {
    padding: 0.7rem 0.95rem;
    border: 1px solid var(--line-strong);
    margin-bottom: 1rem;
    background: var(--paper);
    font-size: 0.88rem;
  }
  .banner.ok { border-left: 4px solid var(--ok); }
  .banner.alert { border-left: 4px solid var(--danger); color: var(--danger); }
  .panel { margin-bottom: 1.5rem; }
  .status { margin: 0.3rem 0 0.8rem; color: var(--muted); }
  .status strong { color: var(--muted); }
  .status strong.on { color: var(--ok); }
  .mask {
    font-family: var(--font-mono);
    background: var(--bg);
    padding: 0.05rem 0.4rem;
    border: 1px solid var(--line);
  }
  .actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
  .field.full { grid-column: 1 / -1; }
  .field.check {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }
  .empty {
    padding: 1.5rem 0;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 0.78rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .hint { color: var(--muted); font-size: 0.85rem; margin-top: 0.5rem; }
</style>
