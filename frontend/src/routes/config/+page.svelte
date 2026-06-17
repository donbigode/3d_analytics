<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { ExportConfig } from "$lib/types";

  type Providers = {
    preferred_llm_provider: string;
    llm_suggestions_enabled: boolean;
    digest_auto_enabled: boolean;
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
    reddit_configured: boolean;
    reddit_client_id_preview: string | null;
    reddit_secret_preview: string | null;
    reddit_token_active: boolean;
    youtube_configured: boolean;
    youtube_key_preview: string | null;
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
  let redditIdInput = "";
  let redditSecretInput = "";
  let youtubeInput = "";
  let preferred = "anthropic";
  let suggestionsEnabled = false;
  let digestAutoEnabled = true;
  let saving = false;
  let saveOk = false;
  let saveError = "";

  // Data Lake / export
  let exportCfg: ExportConfig | null = null;
  let exportDestination: "s3" | "databricks" = "s3";
  let exportEnabled = false;
  let s3BucketInput = "";
  let s3RegionInput = "";
  let s3PrefixInput = "";
  let s3AccessKeyInput = "";
  let s3SecretInput = "";
  let dbxHostInput = "";
  let dbxVolumeInput = "";
  let dbxTokenInput = "";
  let exportSaving = false;
  let exportRunning = false;
  let exportRunMsg = "";
  let exportRunOk = false;

  function syncExportDraft(c: ExportConfig) {
    exportDestination = c.destination;
    exportEnabled = c.enabled;
    s3BucketInput = c.s3_bucket ?? "";
    s3RegionInput = c.s3_region ?? "";
    s3PrefixInput = c.s3_prefix ?? "";
    s3AccessKeyInput = c.s3_access_key_id ?? "";
    dbxHostInput = c.databricks_host ?? "";
    dbxVolumeInput = c.databricks_volume_path ?? "";
    // segredos nunca voltam crus: mantém o input vazio (= não altera)
    s3SecretInput = "";
    dbxTokenInput = "";
  }

  async function load() {
    loading = true;
    pageError = "";
    try {
      providers = await api<Providers>("/config/providers");
      preferred = providers.preferred_llm_provider;
      suggestionsEnabled = providers.llm_suggestions_enabled;
      digestAutoEnabled = providers.digest_auto_enabled;
      exportCfg = await api<ExportConfig>("/config/export");
      syncExportDraft(exportCfg);
    } catch (err) {
      handleApiError(err);
      pageError = errorMessage(err, "Falha ao carregar configurações.");
    } finally {
      loading = false;
    }
  }

  async function saveExport() {
    exportSaving = true;
    saveError = "";
    saveOk = false;
    const payload: Record<string, unknown> = {
      enabled: exportEnabled,
      destination: exportDestination,
    };
    if (exportDestination === "s3") {
      payload.s3_bucket = s3BucketInput;
      payload.s3_region = s3RegionInput;
      payload.s3_prefix = s3PrefixInput;
      payload.s3_access_key_id = s3AccessKeyInput;
      if (s3SecretInput) payload.s3_secret_access_key = s3SecretInput;
    } else {
      payload.databricks_host = dbxHostInput;
      payload.databricks_volume_path = dbxVolumeInput;
      if (dbxTokenInput) payload.databricks_token = dbxTokenInput;
    }
    try {
      exportCfg = await api<ExportConfig>("/config/export", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      syncExportDraft(exportCfg);
      saveOk = true;
    } catch (err) {
      handleApiError(err);
      saveError = errorMessage(err, "Falha ao salvar o export.");
    } finally {
      exportSaving = false;
    }
  }

  async function runExportNow() {
    exportRunning = true;
    exportRunMsg = "";
    try {
      const res = await api<{ ok: boolean; detail?: string; counts?: Record<string, number> }>(
        "/config/export/run",
        { method: "POST" },
      );
      exportRunOk = res.ok;
      if (res.ok) {
        const total = res.counts
          ? Object.values(res.counts).reduce((a, b) => a + b, 0)
          : 0;
        exportRunMsg = `Export concluído — ${total} registros enviados.`;
      } else {
        exportRunMsg = res.detail ?? "Falha no export.";
      }
      exportCfg = await api<ExportConfig>("/config/export");
      syncExportDraft(exportCfg);
    } catch (err) {
      handleApiError(err);
      exportRunOk = false;
      exportRunMsg = errorMessage(err, "Falha ao rodar o export.");
    } finally {
      exportRunning = false;
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
      digestAutoEnabled = providers.digest_auto_enabled;
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
  async function saveReddit() {
    const payload: Record<string, unknown> = {};
    if (redditIdInput) payload.reddit_client_id = redditIdInput;
    if (redditSecretInput) payload.reddit_client_secret = redditSecretInput;
    if (Object.keys(payload).length === 0) return;
    await save(payload);
    if (!saveError) {
      redditIdInput = "";
      redditSecretInput = "";
    }
  }
  async function clearReddit() {
    await save({ reddit_client_id: "", reddit_client_secret: "" });
  }
  async function saveYoutube() {
    await save({ youtube_api_key: youtubeInput });
    if (!saveError) youtubeInput = "";
  }
  async function clearYoutube() {
    await save({ youtube_api_key: "" });
  }
  async function savePrefs() {
    await save({
      preferred_llm_provider: preferred,
      llm_suggestions_enabled: suggestionsEnabled,
      digest_auto_enabled: digestAutoEnabled,
    });
  }

  async function toggleDigestAuto() {
    await save({ digest_auto_enabled: digestAutoEnabled });
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
      <span class="page-eyebrow">Vídeo · YouTube</span>
      <h2 class="section-title">YouTube Data API</h2>
    </div>
    <p class="status mono">
      Status:
      <strong class:on={providers.youtube_configured}>
        {providers.youtube_configured ? "configurada" : "não configurada"}
      </strong>
      {#if providers.youtube_key_preview}· <span class="mask">{providers.youtube_key_preview}</span>{/if}
    </p>
    <p class="hint">
      Crie a chave em
      <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">console.cloud.google.com/apis/credentials</a>,
      habilite a <strong>YouTube Data API v3</strong>. Free tier dá 10.000
      unidades por dia — suficiente pra ~90 termos no nosso uso.
    </p>
    <div class="form-grid">
      <label class="field full">
        Nova chave de API
        <input bind:value={youtubeInput} type="password" placeholder="AIza..." autocomplete="off" />
      </label>
    </div>
    <div class="actions">
      <button on:click={saveYoutube} disabled={saving || !youtubeInput}>
        {saving ? "Salvando…" : "Salvar YouTube"}
      </button>
      {#if providers.youtube_configured}
        <button class="ghost danger" on:click={clearYoutube} disabled={saving}>Limpar</button>
      {/if}
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="page-eyebrow">Comunidade · Reddit</span>
      <h2 class="section-title">App OAuth (client_credentials)</h2>
    </div>
    <p class="status mono">
      Status:
      <strong class:on={providers.reddit_configured}>
        {providers.reddit_configured ? "configurado" : "não configurado"}
      </strong>
      {#if providers.reddit_client_id_preview}
        · Client ID <span class="mask">{providers.reddit_client_id_preview}</span>
      {/if}
      {#if providers.reddit_token_active}
        · <span class="mask token-on">token ativo</span>
      {/if}
    </p>
    <p class="hint">
      Reddit fechou a busca anônima em 2024-2025. Crie um app
      <strong>type=script</strong> em
      <a href="https://www.reddit.com/prefs/apps" target="_blank" rel="noreferrer">reddit.com/prefs/apps</a>,
      cole o <strong>client_id</strong> (string curta abaixo do nome do app) e o <strong>secret</strong>.
    </p>
    <div class="form-grid">
      <label class="field">
        Client ID
        <input bind:value={redditIdInput} placeholder="ex: ab1cd2EFgh3i" autocomplete="off" />
      </label>
      <label class="field">
        Client Secret
        <input bind:value={redditSecretInput} type="password" placeholder="cole o secret" autocomplete="off" />
      </label>
    </div>
    <div class="actions">
      <button on:click={saveReddit} disabled={saving || (!redditIdInput && !redditSecretInput)}>
        {saving ? "Salvando…" : "Salvar Reddit"}
      </button>
      {#if providers.reddit_configured}
        <button class="ghost danger" on:click={clearReddit} disabled={saving}>Limpar</button>
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
      <label class="field check">
        <input
          type="checkbox"
          bind:checked={digestAutoEnabled}
          on:change={toggleDigestAuto}
        />
        Gerar resumo diário automaticamente
        <small class="hint">
          Quando ligado, o dashboard regenera o digest na primeira visita do dia.
          Quando desligado, só roda quando você clicar em "atualizar" no card do dashboard.
        </small>
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

  {#if exportCfg}
    <section class="panel">
      <div class="panel-head">
        <span class="page-eyebrow">Data Lake · Export</span>
        <h2 class="section-title">Snapshot Parquet (S3 / Databricks)</h2>
      </div>
      <p class="status mono">
        Último envio:
        {#if exportCfg.last_run_at}
          <strong class:on={exportCfg.last_run_status === "ok"}>
            {exportCfg.last_run_status}
          </strong>
          · {new Date(exportCfg.last_run_at).toLocaleString("pt-BR")}
        {:else}
          <strong>nunca</strong>
        {/if}
      </p>
      {#if exportCfg.last_run_detail}
        <p class="hint mono">{exportCfg.last_run_detail}</p>
      {/if}
      <p class="hint">
        Exporta todas as entidades como Parquet bruto (uma pasta por timestamp).
        Segredos ficam mascarados após salvar — informe um novo pra trocar; deixe
        em branco pra manter o atual.
      </p>

      <div class="form-grid">
        <label class="field">
          Destino
          <select bind:value={exportDestination}>
            <option value="s3">Amazon S3</option>
            <option value="databricks">Databricks Volume</option>
          </select>
        </label>
      </div>

      {#if exportDestination === "s3"}
        <div class="form-grid">
          <label class="field">
            Bucket
            <input bind:value={s3BucketInput} placeholder="meu-bucket" autocomplete="off" />
          </label>
          <label class="field">
            Região
            <input bind:value={s3RegionInput} placeholder="us-east-1" autocomplete="off" />
          </label>
          <label class="field">
            Prefixo (opcional)
            <input bind:value={s3PrefixInput} placeholder="3d-analytics/export" autocomplete="off" />
          </label>
          <label class="field">
            Access Key ID
            <input bind:value={s3AccessKeyInput} placeholder="AKIA..." autocomplete="off" />
          </label>
          <label class="field">
            Secret Access Key
            {#if exportCfg.s3_secret_configured}
              <span class="status mono">
                atual: <span class="mask">{exportCfg.s3_secret_access_key_preview}</span>
              </span>
            {/if}
            <input bind:value={s3SecretInput} type="password" placeholder="novo secret (vazio = manter)" autocomplete="off" />
          </label>
        </div>
      {:else}
        <div class="form-grid">
          <label class="field">
            Host
            <input bind:value={dbxHostInput} placeholder="https://xxx.databricks.com" autocomplete="off" />
          </label>
          <label class="field">
            Volume path
            <input bind:value={dbxVolumeInput} placeholder="/Volumes/catalog/schema/vol/base" autocomplete="off" />
          </label>
          <label class="field full">
            Token
            {#if exportCfg.databricks_token_configured}
              <span class="status mono">
                atual: <span class="mask">{exportCfg.databricks_token_preview}</span>
              </span>
            {/if}
            <input bind:value={dbxTokenInput} type="password" placeholder="novo token (vazio = manter)" autocomplete="off" />
          </label>
        </div>
      {/if}

      <div class="form-grid">
        <label class="field check">
          <input type="checkbox" bind:checked={exportEnabled} />
          Enviar automaticamente 1x/dia
        </label>
      </div>

      <div class="actions">
        <button on:click={saveExport} disabled={exportSaving}>
          {exportSaving ? "Salvando…" : "Salvar destino"}
        </button>
        <button class="ghost" on:click={runExportNow} disabled={exportRunning}>
          {exportRunning ? "Exportando…" : "Exportar agora"}
        </button>
      </div>
      {#if exportRunMsg}
        <p class="status mono" class:run-ok={exportRunOk} class:run-err={!exportRunOk}>
          {exportRunMsg}
        </p>
      {/if}
    </section>
  {/if}
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
  .run-ok { color: var(--ok); }
  .run-err { color: var(--danger); }
</style>
