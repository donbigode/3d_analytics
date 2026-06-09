<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import type { Asset, DownloadOut, RemoteSearchHit, SearchResponse } from "$lib/types";

  let rows: Asset[] = [];
  let loading = true;
  let listError = "";

  // upload
  let uploadFile: FileList | null = null;
  let uploadSourceUrl = "";
  let uploadAuthor = "";
  let uploadLicense = "";
  let uploading = false;
  let uploadError = "";
  let uploadBanner = "";

  // remote search
  let q = "";
  let searchHits: RemoteSearchHit[] = [];
  let searchErrors: string[] = [];
  let searching = false;
  let searchBanner = "";
  let downloadingId: string | null = null;

  async function load() {
    loading = true;
    listError = "";
    try {
      rows = await api<Asset[]>("/library");
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao carregar biblioteca.");
    } finally {
      loading = false;
    }
  }

  async function upload() {
    if (!uploadFile || uploadFile.length === 0) return;
    uploading = true;
    uploadError = "";
    uploadBanner = "";
    try {
      const fd = new FormData();
      fd.append("file", uploadFile[0]);
      if (uploadSourceUrl) fd.append("source_url", uploadSourceUrl);
      if (uploadAuthor) fd.append("source_author", uploadAuthor);
      if (uploadLicense) fd.append("source_license", uploadLicense);
      const res = await fetch("/api/library/upload", {
        method: "POST",
        body: fd,
        credentials: "include",
      });
      if (!res.ok) {
        const body = await res.text();
        let msg = `HTTP ${res.status}`;
        try {
          const j = JSON.parse(body);
          if (typeof j.detail === "string") msg = j.detail;
        } catch {}
        throw new Error(msg);
      }
      const out = (await res.json()) as DownloadOut;
      uploadBanner = out.duplicate
        ? `Arquivo já existia (hash duplicado) — reaproveitando ${out.asset.filename}`
        : `Adicionado: ${out.asset.filename}`;
      uploadFile = null;
      uploadSourceUrl = uploadAuthor = uploadLicense = "";
      const input = document.getElementById("libFile") as HTMLInputElement | null;
      if (input) input.value = "";
      await load();
    } catch (err) {
      uploadError = err instanceof Error ? err.message : "Falha no upload.";
    } finally {
      uploading = false;
    }
  }

  async function removeAsset(id: string, filename: string) {
    if (!confirm(`Remover ${filename} da biblioteca?`)) return;
    try {
      await api(`/library/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      handleApiError(err);
      listError = errorMessage(err, "Falha ao remover.");
    }
  }

  async function searchRemote() {
    if (!q.trim()) return;
    searching = true;
    searchBanner = "";
    searchErrors = [];
    try {
      const res = await api<SearchResponse>("/library/search", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ q: q.trim(), use_llm: true }),
      });
      searchHits = res.hits;
      searchErrors = res.errors;
      if (res.errors.length > 0 && res.hits.length === 0) {
        searchBanner = res.errors[0];
      }
    } catch (err) {
      handleApiError(err);
      searchBanner = errorMessage(err, "Falha na busca remota.");
    } finally {
      searching = false;
    }
  }

  async function downloadHit(hit: RemoteSearchHit) {
    downloadingId = hit.remote_id;
    try {
      const out = await api<DownloadOut>("/library/download", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          site: hit.site,
          remote_id: hit.remote_id,
          source_url: hit.source_url,
        }),
      });
      searchBanner = out.duplicate
        ? `Já estava na biblioteca: ${out.asset.filename}`
        : `Baixado: ${out.asset.filename}`;
      await load();
    } catch (err) {
      handleApiError(err);
      searchBanner = errorMessage(err, "Falha no download.");
    } finally {
      downloadingId = null;
    }
  }

  function fmtSize(b: number): string {
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 / 1024).toFixed(1)} MB`;
  }

  function fmtDur(s: number | null | undefined): string {
    if (!s) return "—";
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}min` : `${m}min`;
  }

  function fmtDate(s: string | null): string {
    if (!s) return "—";
    try {
      return new Date(s).toLocaleString("pt-BR");
    } catch {
      return s;
    }
  }

  onMount(() => {
    if (requireAuth()) return;
    load();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Recursos / 11 · acervo</span>
  <h1 class="page-title">Biblioteca<em>.</em></h1>
  <p class="page-lede">
    Arquivos de impressão (<span class="mono">.gcode</span>, <span class="mono">.3mf</span>,
    <span class="mono">.stl</span>, <span class="mono">.obj</span>, <span class="mono">.step</span>)
    e materiais complementares (PDF, foto, planilha, documento) que você fez upload
    ou baixou de Printables / Thingiverse. Deduplicados por SHA-256 — o mesmo arquivo
    nunca ocupa espaço duas vezes.
  </p>
</header>

<section class="panel">
  <div class="panel-head">
    <div>
      <span class="page-eyebrow">Buscar online</span>
      <h2 class="form-title">Procurar modelos em Printables / Thingiverse</h2>
    </div>
  </div>
  <form class="search-form" on:submit|preventDefault={searchRemote}>
    <input
      bind:value={q}
      placeholder="porta celular cabeceira"
      autocomplete="off"
    />
    <button type="submit" disabled={searching || !q.trim()}>
      {searching ? "Buscando…" : "Buscar"}
    </button>
  </form>
  {#if searchBanner}<p class="banner">{searchBanner}</p>{/if}
  {#if searchErrors.length > 1 || (searchErrors.length > 0 && searchHits.length > 0)}
    <details class="errors">
      <summary>{searchErrors.length} aviso{searchErrors.length === 1 ? "" : "s"} dos provedores</summary>
      <ul>
        {#each searchErrors as e}<li class="mono">{e}</li>{/each}
      </ul>
    </details>
  {/if}

  {#if searchHits.length > 0}
    <div class="hits">
      {#each searchHits as h (h.remote_id)}
        <article class="hit">
          {#if h.thumbnail_url}
            <img src={h.thumbnail_url} alt={h.title} loading="lazy" />
          {:else}
            <div class="thumb-empty">{h.site}</div>
          {/if}
          <div class="hit-body">
            <strong>{h.title}</strong>
            <p class="hit-meta">
              {#if h.author}por {h.author}{/if}
              {#if h.license} · <span class="mono">{h.license}</span>{/if}
              {#if h.downloads !== null && h.downloads !== undefined}
                · {h.downloads} downloads
              {/if}
            </p>
            {#if h.summary}<p class="hit-summary">{h.summary}</p>{/if}
            <div class="hit-actions">
              <a class="tiny ghost" href={h.source_url} target="_blank" rel="noreferrer">Abrir ↗</a>
              <button
                class="tiny"
                on:click={() => downloadHit(h)}
                disabled={downloadingId === h.remote_id}
              >
                {downloadingId === h.remote_id ? "Baixando…" : "↓ Baixar"}
              </button>
            </div>
          </div>
        </article>
      {/each}
    </div>
  {/if}
</section>

<section class="panel">
  <div class="panel-head">
    <div>
      <span class="page-eyebrow">Adicionar manualmente</span>
      <h2 class="form-title">Upload de arquivo</h2>
    </div>
  </div>
  <form class="form-grid" on:submit|preventDefault={upload}>
    <label class="field">
      Arquivo (imprimível ou complementar)
      <input
        id="libFile"
        type="file"
        accept=".gcode,.bgcode,.gco,.g,.3mf,.stl,.obj,.step,.stp,.pdf,.doc,.docx,.txt,.md,.rtf,.png,.jpg,.jpeg,.webp,.gif,.csv,.xlsx,.xls,.zip"
        bind:files={uploadFile}
        required
      />
      <small class="hint">
        Imprimíveis: .gcode .bgcode .3mf .stl .obj .step ·
        Complementares: .pdf .docx .txt .png .jpg .csv .xlsx .zip
      </small>
    </label>
    <label class="field">
      URL do modelo (opcional)
      <input type="url" bind:value={uploadSourceUrl} placeholder="https://printables.com/model/..." />
    </label>
    <label class="field">
      Autor (opcional)
      <input bind:value={uploadAuthor} />
    </label>
    <label class="field">
      Licença (opcional)
      <input bind:value={uploadLicense} placeholder="CC-BY, CC-BY-NC, ..." />
    </label>
    <div class="actions">
      <button type="submit" disabled={uploading || !uploadFile?.length}>
        {uploading ? "Enviando…" : "+ Adicionar"}
      </button>
    </div>
  </form>
  {#if uploadError}<p class="alert">{uploadError}</p>{/if}
  {#if uploadBanner}<p class="banner ok">{uploadBanner}</p>{/if}
</section>

<section class="panel">
  <div class="panel-head">
    <h2 class="section-title">Acervo local <span class="count">· {rows.length}</span></h2>
    <button class="tiny ghost" on:click={load} disabled={loading}>
      {loading ? "…" : "Atualizar"}
    </button>
  </div>
  {#if listError}<p class="alert">{listError}</p>{/if}
  {#if rows.length === 0 && !loading}
    <p class="empty">Nenhum arquivo na biblioteca. Faça upload acima ou busque online.</p>
  {:else}
    <div class="asset-list">
      {#each rows as a (a.id)}
        <article class="asset">
          <div class="asset-head">
            <strong>{a.filename}</strong>
            <span class="format mono">{a.format}</span>
            {#if a.source_site}<span class="source mono">{a.source_site}</span>{/if}
          </div>
          <div class="asset-meta mono">
            {fmtSize(a.size_bytes)}
            {#if a.parsed_meta?.time_s} · ⏱ {fmtDur(a.parsed_meta.time_s)}{/if}
            {#if a.parsed_meta?.filament_m} · {a.parsed_meta.filament_m.toFixed(2)}m{/if}
            {#if a.parsed_meta?.material} · {a.parsed_meta.material}{/if}
            · {fmtDate(a.created_at)}
          </div>
          {#if a.source_author || a.source_license}
            <div class="attribution mono">
              {#if a.source_author}por {a.source_author}{/if}
              {#if a.source_license} · {a.source_license}{/if}
              {#if a.source_url}· <a href={a.source_url} target="_blank" rel="noreferrer">link</a>{/if}
            </div>
          {/if}
          <div class="asset-actions">
            <a class="tiny ghost" href={`/api/library/${a.id}/file`} download>↓ Arquivo</a>
            <button class="tiny danger" on:click={() => removeAsset(a.id, a.filename)}>remover</button>
          </div>
        </article>
      {/each}
    </div>
  {/if}
</section>

<style>
  .page-head { margin-bottom: 1.5rem; }
  .page-head em { color: var(--brand); font-style: italic; }
  .panel { margin-bottom: 1.5rem; }
  .search-form {
    display: flex;
    gap: 0.5rem;
    margin: 0.5rem 0 0.8rem;
  }
  .search-form input {
    flex: 1;
    padding: 0.55rem 0.7rem;
    border: 1px solid var(--line);
    font: inherit;
  }
  .banner { color: var(--ink); margin: 0.4rem 0; }
  .banner.ok { color: var(--ok); }
  .alert { color: var(--danger); }
  .hint { color: var(--muted); font-size: 0.72rem; margin-top: 0.25rem; }
  .errors { margin: 0.5rem 0; }
  .errors summary { cursor: pointer; color: var(--muted); font-size: 0.85rem; }
  .errors ul { margin: 0.3rem 0; padding-left: 1.2rem; }

  .hits {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 0.8rem;
    margin-top: 0.6rem;
  }
  .hit {
    background: var(--paper);
    border: 1px solid var(--line-strong);
    display: flex;
    flex-direction: column;
  }
  .hit img { width: 100%; aspect-ratio: 1; object-fit: cover; }
  .thumb-empty {
    aspect-ratio: 1;
    background: var(--bg);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.78rem;
  }
  .hit-body { padding: 0.7rem 0.85rem; display: flex; flex-direction: column; gap: 0.3rem; flex: 1; }
  .hit-meta { color: var(--muted); font-size: 0.78rem; margin: 0; }
  .hit-summary {
    color: var(--ink);
    font-size: 0.85rem;
    margin: 0.2rem 0;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .hit-actions {
    display: flex;
    justify-content: space-between;
    gap: 0.4rem;
    margin-top: auto;
    padding-top: 0.5rem;
    border-top: 1px dashed var(--line);
  }

  .asset-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .asset {
    border: 1px solid var(--line);
    background: var(--paper);
    padding: 0.6rem 0.85rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .asset-head { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; }
  .format {
    font-size: 0.62rem;
    padding: 0.05rem 0.4rem;
    border: 1px solid var(--line-strong);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .source {
    font-size: 0.62rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .asset-meta { color: var(--muted); font-size: 0.78rem; }
  .attribution { color: var(--muted); font-size: 0.78rem; }
  .attribution a { color: var(--brand); }
  .asset-actions { display: flex; gap: 0.4rem; margin-top: 0.3rem; }
  .empty {
    color: var(--muted);
    padding: 1rem 0;
    font-style: italic;
  }
</style>
