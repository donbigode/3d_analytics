<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import { appSettings } from "$lib/stores/settings";
  import type { Settings } from "$lib/types";

  let settings: Settings | null = null;
  let loading = true;
  let loadError = "";

  let submitting = false;
  let saveError = "";
  let saveOk = false;

  let logoFile: FileList | null = null;
  let logoError = "";
  let logoSubmitting = false;
  let logoVersion = 0; // bust cache after upload

  async function load() {
    loading = true;
    loadError = "";
    try {
      settings = await api<Settings>("/settings");
      appSettings.set(settings);
    } catch (err) {
      handleApiError(err);
      loadError = errorMessage(err, "Falha ao carregar configurações.");
    } finally {
      loading = false;
    }
  }

  async function save() {
    if (!settings) return;
    saveError = "";
    saveOk = false;
    submitting = true;
    try {
      const updated = await api<Settings>("/settings", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          energy_kwh_price: settings.energy_kwh_price,
          printer_power_w: settings.printer_power_w,
          printer_depreciation_per_hour: settings.printer_depreciation_per_hour,
          printer_hours_per_day: settings.printer_hours_per_day,
          currency: settings.currency,
          business_name: settings.business_name,
          business_tagline: settings.business_tagline,
          brand_color_primary: settings.brand_color_primary,
          stalled_quote_alert_days: settings.stalled_quote_alert_days,
          low_spool_threshold_g: settings.low_spool_threshold_g,
        }),
      });
      settings = updated;
      appSettings.set(updated);
      saveOk = true;
    } catch (err) {
      handleApiError(err);
      saveError = errorMessage(err, "Falha ao salvar configurações.");
    } finally {
      submitting = false;
    }
  }

  async function uploadLogo() {
    if (!logoFile || logoFile.length === 0) return;
    logoError = "";
    logoSubmitting = true;
    try {
      const fd = new FormData();
      fd.append("file", logoFile[0]);
      const res = await fetch("/api/settings/logo", {
        method: "POST",
        body: fd,
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = (await res.json()) as Settings;
      settings = updated;
      appSettings.set(updated);
      logoFile = null;
      logoVersion += 1;
    } catch (err) {
      handleApiError(err);
      logoError = errorMessage(err, "Falha ao enviar o logo.");
    } finally {
      logoSubmitting = false;
    }
  }

  async function removeLogo() {
    if (!confirm("Remover o logo atual?")) return;
    logoError = "";
    logoSubmitting = true;
    try {
      const updated = await api<Settings>("/settings/logo", { method: "DELETE" });
      settings = updated;
      appSettings.set(updated);
      logoVersion += 1;
    } catch (err) {
      handleApiError(err);
      logoError = errorMessage(err, "Falha ao remover o logo.");
    } finally {
      logoSubmitting = false;
    }
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Configuração / 05</span>
  <h1 class="page-title">Ajustes<em>.</em></h1>
  <p class="page-lede">Parâmetros globais usados nos cálculos de custo e na identidade visual dos orçamentos.</p>
</header>

{#if loading}
  <p>Carregando…</p>
{:else if loadError}
  <div class="alert">{loadError}</div>
{:else if settings}
  <section class="panel">
    <div class="panel-head">
      <span class="panel-eyebrow">Identidade visual</span>
      <h2 class="section-title">Marca</h2>
    </div>

    <form class="form-grid" on:submit|preventDefault={save}>
      <label class="field">
        Nome do negócio
        <input bind:value={settings.business_name} required />
      </label>
      <label class="field">
        Slogan / tagline
        <input bind:value={settings.business_tagline} placeholder="Opcional" />
      </label>
      <label class="field">
        Cor primária (hex)
        <input bind:value={settings.brand_color_primary} placeholder="#111827" />
      </label>
      <label class="field">
        Moeda
        <input bind:value={settings.currency} maxlength={3} />
      </label>
    </form>

    <div class="logo-block">
      <div class="logo-preview">
        {#if settings.logo_path}
          <img
            src={`/api/settings/logo?v=${logoVersion}`}
            alt="logo atual"
          />
        {:else}
          <div class="logo-placeholder">sem logo</div>
        {/if}
      </div>
      <div class="logo-controls">
        <label class="field">
          Enviar logo (PNG/JPG/SVG)
          <input type="file" accept="image/png,image/jpeg,image/svg+xml" bind:files={logoFile} />
        </label>
        <div class="actions">
          <button type="button" on:click={uploadLogo} disabled={!logoFile || logoSubmitting}>
            {logoSubmitting ? "Enviando…" : "Enviar"}
          </button>
          {#if settings.logo_path}
            <button type="button" class="ghost danger" on:click={removeLogo} disabled={logoSubmitting}>
              Remover logo
            </button>
          {/if}
        </div>
        {#if logoError}<div class="alert">{logoError}</div>{/if}
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="panel-eyebrow">Custo de produção</span>
      <h2 class="section-title">Energia &amp; depreciação</h2>
    </div>

    <form class="form-grid" on:submit|preventDefault={save}>
      <label class="field">
        Energia (R$/kWh)
        <input type="number" step="0.0001" min="0" bind:value={settings.energy_kwh_price} required />
      </label>
      <label class="field">
        Potência média da impressora (W)
        <input type="number" step="0.01" min="0" bind:value={settings.printer_power_w} required />
      </label>
      <label class="field">
        Depreciação por hora (R$/h)
        <input type="number" step="0.01" min="0" bind:value={settings.printer_depreciation_per_hour} required />
      </label>
      <label class="field">
        Horas úteis de impressão por dia
        <input
          type="number"
          step="1"
          min="1"
          max="24"
          bind:value={settings.printer_hours_per_day}
          required
        />
        <small class="hint">Usado pelo planejador de capacidade (/capacity) — quantas horas você consegue manter a impressora rodando por dia.</small>
      </label>
    </form>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span class="panel-eyebrow">Alertas</span>
      <h2 class="section-title">Limiares do dashboard</h2>
    </div>

    <form class="form-grid" on:submit|preventDefault={save}>
      <label class="field">
        Orçamentos parados após (dias)
        <input type="number" min="1" bind:value={settings.stalled_quote_alert_days} required />
      </label>
      <label class="field">
        Spool com pouco filamento (g)
        <input type="number" step="0.01" min="0" bind:value={settings.low_spool_threshold_g} required />
      </label>
    </form>
  </section>

  <div class="bottom-actions">
    {#if saveError}<div class="alert">{saveError}</div>{/if}
    {#if saveOk}<div class="ok">Configurações salvas.</div>{/if}
    <button type="button" on:click={save} disabled={submitting}>
      {submitting ? "Salvando…" : "Salvar todas as alterações"}
    </button>
  </div>
{/if}

<style>
  .panel { margin-bottom: 1.5rem; }
  .panel + .panel { margin-top: 1.5rem; }
  .logo-block {
    display: grid;
    grid-template-columns: 160px 1fr;
    gap: 1rem;
    align-items: start;
    margin-top: 1rem;
  }
  .logo-preview {
    width: 160px; height: 160px;
    border: 1px dashed var(--border, #d1d5db);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    background: #f9fafb;
    overflow: hidden;
  }
  .logo-preview img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .logo-placeholder { color: #9ca3af; font-size: 0.85em; }
  .logo-controls { display: flex; flex-direction: column; gap: 0.75rem; }
  .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .bottom-actions {
    display: flex; flex-direction: column; gap: 0.5rem;
    align-items: flex-end; margin-top: 1.5rem;
  }
  .ok { color: #047857; font-size: 0.9em; }
  .alert { color: #b91c1c; font-size: 0.9em; }
  @media (max-width: 600px) {
    .logo-block { grid-template-columns: 1fr; }
    .logo-preview { width: 100%; }
  }
</style>
