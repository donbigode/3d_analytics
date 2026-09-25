<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { requireAuth } from "$lib/guard";
  import { resource, action } from "$lib/resource";
  import { appSettings } from "$lib/stores/settings";
  import type { Person, Settings } from "$lib/types";

  const settingsRes = resource(
    async () => {
      const s = await api<Settings>("/settings");
      appSettings.set(s);
      return s;
    },
    { errorMessage: "Falha ao carregar configurações.", auto: false },
  );
  // Cópia mutável local: os campos do formulário usam bind:value diretamente
  // nela (edição livre antes de salvar), então não pode ser o próprio dado
  // do resource() — reatribuir aqui só acontece quando o resource troca de
  // referência de verdade (reload()/set() bem-sucedidos), nunca a cada
  // digitação do usuário.
  let settings: Settings | null = null;
  $: if ($settingsRes.data) settings = $settingsRes.data;

  let saveOk = false;
  const saveAction = action(
    (body: Record<string, unknown>) =>
      api<Settings>("/settings", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      }),
    { errorMessage: "Falha ao salvar configurações." },
  );

  let logoFile: FileList | null = null;
  let logoVersion = 0; // bust cache after upload
  const uploadLogoAction = action(
    async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/settings/logo", {
        method: "POST",
        body: fd,
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as Settings;
    },
    { errorMessage: "Falha ao enviar o logo." },
  );
  const removeLogoAction = action(() => api<Settings>("/settings/logo", { method: "DELETE" }), {
    errorMessage: "Falha ao remover o logo.",
  });
  // Upload e remoção dividem o mesmo alerta de logo — um bem-sucedido não
  // pode deixar preso o erro do outro (cada função zera o irmão antes de
  // rodar, igual ao logoError = "" único que existia antes daqui).
  $: logoError = $uploadLogoAction.error || $removeLogoAction.error;
  $: logoSubmitting = $uploadLogoAction.pending || $removeLogoAction.pending;

  $: autoDepRate = (() => {
    if (!settings) return "0,00";
    const price = Number(settings.printer_purchase_price ?? 0);
    const hours = Number(settings.printer_useful_life_hours ?? 0);
    if (price <= 0 || hours <= 0) return "0,00";
    return (price / hours).toFixed(2).replace(".", ",");
  })();

  function autoDepreciation() {
    if (!settings) return;
    const price = Number(settings.printer_purchase_price ?? 0);
    const hours = Number(settings.printer_useful_life_hours ?? 0);
    if (price <= 0 || hours <= 0) return;
    settings.printer_depreciation_per_hour = +(price / hours).toFixed(2);
  }

  async function save() {
    if (!settings) return;
    saveOk = false;
    const updated = await saveAction.run({
      energy_kwh_price: settings.energy_kwh_price,
      printer_power_w: settings.printer_power_w,
      printer_purchase_price: settings.printer_purchase_price,
      printer_useful_life_hours: settings.printer_useful_life_hours,
      printer_depreciation_per_hour: settings.printer_depreciation_per_hour,
      printer_maintenance_per_hour: settings.printer_maintenance_per_hour,
      printer_hours_per_day: settings.printer_hours_per_day,
      revenue_tax_pct: settings.revenue_tax_pct,
      currency: settings.currency,
      business_name: settings.business_name,
      business_tagline: settings.business_tagline,
      brand_color_primary: settings.brand_color_primary,
      stalled_quote_alert_days: settings.stalled_quote_alert_days,
      low_spool_threshold_g: settings.low_spool_threshold_g,
    });
    if (!updated) return;
    settingsRes.set(updated);
    appSettings.set(updated);
    saveOk = true;
  }

  async function uploadLogo() {
    if (!logoFile || logoFile.length === 0) return;
    removeLogoAction.reset();
    const updated = await uploadLogoAction.run(logoFile[0]);
    if (!updated) return;
    settingsRes.set(updated);
    appSettings.set(updated);
    logoFile = null;
    logoVersion += 1;
  }

  async function removeLogo() {
    if (!confirm("Remover o logo atual?")) return;
    uploadLogoAction.reset();
    const updated = await removeLogoAction.run();
    if (!updated) return;
    settingsRes.set(updated);
    appSettings.set(updated);
    logoVersion += 1;
  }

  // Pessoas (projetos pessoais)
  const peopleRes = resource(() => api<Person[]>("/people"), { initial: [], auto: false });
  $: people = $peopleRes.data ?? [];
  let newPersonName = "";
  const addPersonAction = action(
    (name: string) =>
      api<Person>("/people", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name }),
      }),
    { errorMessage: "Falha ao adicionar pessoa." },
  );
  const togglePersonActiveAction = action((p: Person) =>
    api<Person>(`/people/${p.id}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ active: !p.active }),
    }),
  );
  const deletePersonAction = action((p: Person) => api(`/people/${p.id}`, { method: "DELETE" }));

  async function addPerson() {
    const name = newPersonName.trim();
    if (!name) return;
    const created = await addPersonAction.run(name);
    if (!created) return;
    newPersonName = "";
    await peopleRes.reload();
  }

  async function togglePersonActive(p: Person) {
    await togglePersonActiveAction.run(p);
    if (!$togglePersonActiveAction.error) await peopleRes.reload();
  }

  async function deletePerson(p: Person) {
    await deletePersonAction.run(p);
    if (!$deletePersonAction.error) await peopleRes.reload();
  }

  onMount(() => {
    if (requireAuth()) return;
    settingsRes.reload();
    peopleRes.reload();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Configuração / 05</span>
  <h1 class="page-title">Ajustes<em>.</em></h1>
  <p class="page-lede">Parâmetros globais usados nos cálculos de custo e na identidade visual dos orçamentos.</p>
</header>

{#if $settingsRes.loading}
  <p>Carregando…</p>
{:else if $settingsRes.error}
  <div class="alert">{$settingsRes.error}</div>
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

    <form class="form-grid cost-form" on:submit|preventDefault={save}>
      <label class="field">
        Energia (R$/kWh)
        <input type="number" step="0.0001" min="0" bind:value={settings.energy_kwh_price} required />
      </label>
      <label class="field">
        Potência média da impressora (W)
        <input type="number" step="0.01" min="0" bind:value={settings.printer_power_w} required />
        <small class="hint">K2 Plus médio FDM gira em torno de 150–250 W.</small>
      </label>
      <label class="field">
        Preço da impressora (R$)
        <input type="number" step="0.01" min="0" bind:value={settings.printer_purchase_price} required />
        <small class="hint">Valor pago. Usado só pra te ajudar a calcular a depreciação.</small>
      </label>
      <label class="field">
        Vida útil estimada (horas)
        <input type="number" step="1" min="0" bind:value={settings.printer_useful_life_hours} required />
        <small class="hint">~7.300 h ≈ 4 h/dia × 5 anos. Use mais se imprimir muito.</small>
      </label>
      <label class="field">
        Depreciação por hora (R$/h)
        <div class="inline-actions">
          <input type="number" step="0.01" min="0" bind:value={settings.printer_depreciation_per_hour} required />
          <button type="button" class="tiny ghost" on:click={autoDepreciation}>
            ↻ calcular
          </button>
        </div>
        <small class="hint">
          Sugerido: preço ÷ vida útil = R$ {autoDepRate}/h
        </small>
      </label>
      <label class="field">
        Manutenção por hora (R$/h)
        <input type="number" step="0.01" min="0" bind:value={settings.printer_maintenance_per_hour} required />
        <small class="hint">Bicos, correias, build plates, lubrificação. Tipicamente R$ 0,30–0,80/h.</small>
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
      <label class="field">
        Imposto sobre receita (%)
        <input type="number" step="0.01" min="0" bind:value={settings.revenue_tax_pct} required />
        <small class="hint">Aplicado sobre a receita bruta no DRE (Simples, MEI, etc.). Use 0 se não recolhe.</small>
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

  <section class="panel">
    <div class="panel-head">
      <h2 class="section-title">Pessoas (projetos pessoais)</h2>
    </div>
    <p class="hint">
      Quem aparece pra marcar nos projetos pessoais (Otávio, Ana…). Inativar
      mantém o histórico; excluir remove as atribuições.
    </p>
    {#if $addPersonAction.error}<div class="alert">{$addPersonAction.error}</div>{/if}
    <ul class="people-list">
      {#each people as p (p.id)}
        <li class:inactive={!p.active}>
          <span class="name">{p.name}</span>
          <span class="row-actions">
            <button type="button" class="ghost tiny" on:click={() => togglePersonActive(p)}>
              {p.active ? "inativar" : "ativar"}
            </button>
            <button type="button" class="ghost tiny danger" on:click={() => deletePerson(p)}>excluir</button>
          </span>
        </li>
      {/each}
      {#if people.length === 0}
        <li class="empty-row">Nenhuma pessoa cadastrada</li>
      {/if}
    </ul>
    <form class="add-person" on:submit|preventDefault={addPerson}>
      <input bind:value={newPersonName} placeholder="Nome da pessoa" />
      <button type="submit" disabled={!newPersonName.trim()}>+ adicionar</button>
    </form>
  </section>

  <div class="bottom-actions">
    {#if $saveAction.error}<div class="alert">{$saveAction.error}</div>{/if}
    {#if saveOk}<div class="ok">Configurações salvas.</div>{/if}
    <button type="button" on:click={save} disabled={$saveAction.pending}>
      {$saveAction.pending ? "Salvando…" : "Salvar todas as alterações"}
    </button>
  </div>
{/if}

<style>
  .panel { margin-bottom: 1.5rem; }
  .people-list { list-style: none; margin: 0.5rem 0; padding: 0; }
  .people-list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--line);
  }
  .people-list li.inactive .name { color: var(--muted); text-decoration: line-through; }
  .people-list .row-actions { display: flex; gap: 0.4rem; }
  .people-list .empty-row { color: var(--muted); font-size: 0.85rem; }
  .add-person { display: flex; gap: 0.5rem; margin-top: 0.6rem; }
  .add-person input { flex: 1; }
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
  /* Cost-form panel: hints under inputs ruin the default `align-items: end`
     because labels with a hint end up taller than labels without one. Pin
     each cell to the top of its grid row, push the hint to the bottom with
     auto-margin, and force inputs onto a single shared baseline. */
  .form-grid.cost-form {
    align-items: stretch;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }
  .form-grid.cost-form .field {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .form-grid.cost-form .field input,
  .form-grid.cost-form .field .inline-actions {
    align-self: stretch;
  }
  .form-grid.cost-form .field small.hint {
    margin-top: auto;
    min-height: 2.4em;
    line-height: 1.2;
  }
  /* Override local: .hint aqui nunca teve cor própria (cinza-mudo é novo em
     app.css); mantém herdada pra não mudar a aparência desta página */
  .hint { color: inherit; }
  .inline-actions {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .inline-actions input { flex: 1; }
  .inline-actions button { white-space: nowrap; flex-shrink: 0; }
  .bottom-actions {
    display: flex; flex-direction: column; gap: 0.5rem;
    align-items: flex-end; margin-top: 1.5rem;
  }
  .ok { color: #047857; font-size: 0.9em; }
  /* Override local: tom de vermelho e tamanho próprios, diferentes do
     padrão global (mantém aparência já existente nesta página) */
  .alert { color: #b91c1c; font-size: 0.9em; }
  @media (max-width: 600px) {
    .logo-block { grid-template-columns: 1fr; }
    .logo-preview { width: 100%; }
  }
</style>
