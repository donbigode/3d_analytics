<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import {
    delta,
    gcodeGrams,
    sumGrams,
    toGrams,
    whyNotSendable,
    withoutIndex,
  } from "$lib/filament-lines";
  import { num as fmtNum, DASH } from "$lib/format";
  import type { Material, QuoteItemFilament } from "$lib/types";

  /** Editor das linhas de filamento de um item — uma linha por cor.
   *
   *  A lista inteira é substituída num PUT só (Task 7): a ordem da lista É a
   *  posição, e `material_id` não pode viajar no mesmo payload que
   *  `filaments`. Este componente não fala com a API — despacha `save` com a
   *  lista pronta e o pai devolve em `filaments` o que o servidor respondeu. */

  export let filaments: QuoteItemFilament[] = [];
  export let materials: Material[] = [];
  export let gcodeMeta: Record<string, unknown> = {};
  /** PUT em voo — trava os campos para não sobrepor dois salvamentos. */
  export let saving = false;

  const dispatch = createEventDispatcher<{
    save: { filaments: { material_id: string; grams_unit?: string }[] };
  }>();

  /** O rascunho guarda as gramas como o TEXTO do campo, não como número: o
   *  que a pessoa digitou é o que fica no input, sem reformatar embaixo do
   *  cursor. `toGrams` faz a leitura ("" e 0 são ausência, não zero grama). */
  type Rascunho = { material_id: string; gramasRaw: string; position: number };
  type Normal = { material_id: string; grams_unit: number | null };

  function doServidor(vindas: QuoteItemFilament[]): Rascunho[] {
    // Item sem linha nenhuma (`material_pending`) começa com uma linha em
    // branco: é onde a pessoa escolhe o material, como o seletor único fazia.
    if (vindas.length === 0) return [{ material_id: "", gramasRaw: "", position: 1 }];
    return vindas.map((f, i) => ({
      material_id: f.material_id,
      gramasRaw: f.grams_unit === null || f.grams_unit === undefined ? "" : String(f.grams_unit),
      // A API já devolve ordenado por position; no rascunho a posição é o
      // índice + 1, que é exatamente o que o PUT vai gravar (a ordem da lista
      // É a posição).
      position: i + 1,
    }));
  }

  function normaliza(atuais: Rascunho[]): Normal[] {
    return atuais.map((l) => ({ material_id: l.material_id, grams_unit: toGrams(l.gramasRaw) }));
  }

  // Ressincroniza o rascunho quando o servidor responde. `filaments` aparece
  // textualmente e é o único gatilho: mexer no rascunho localmente (digitar,
  // + cor, ×) não muda a prop, então a linha nova em branco sobrevive até o
  // PUT acontecer — e quando ele acontece, o servidor volta a ser a verdade.
  $: linhas = doServidor(filaments);

  // ARMADILHA CONHECIDA DESTE PROJETO: a descoberta de dependências de um
  // `$:` é uma varredura TEXTUAL do statement. Variável lida de dentro de uma
  // função chamada é invisível e o bloco nunca re-roda. Por isso cada
  // dependência abaixo (`linhas`, `normalizadas`, `materials`, `gcodeMeta`,
  // `densidade`, `soma`, `gcodeTotal`) é passada como ARGUMENTO, aparecendo
  // textualmente no próprio statement.
  $: normalizadas = normaliza(linhas);
  $: soma = sumGrams(normalizadas);
  $: bloqueio = whyNotSendable(normalizadas);

  // Densidade do material da linha 1: é ela que define o material do item
  // (`material_version_id` vem da position 1), e é a única densidade que faz
  // sentido para um número de gcode que é do item inteiro.
  $: densidade = densidadeDe(materials, linhas[0]?.material_id ?? "");
  $: gcodeTotal = gcodeGrams(gcodeMeta, densidade);
  $: diferenca = delta(soma, gcodeTotal);

  // Invariante 3 do servidor: mais de uma cor exige gramas em TODAS. Com uma
  // cor só, campo vazio é legítimo — significa "derive do gcode".
  $: exigeGramas = linhas.length > 1;

  function densidadeDe(lista: Material[], materialId: string): number {
    const m = lista.find((x) => x.id === materialId);
    const d = Number(m?.density_g_cm3);
    return Number.isFinite(d) && d > 0 ? d : 1.24;
  }

  function nomeDe(lista: Material[], materialId: string): string {
    const m = lista.find((x) => x.id === materialId);
    return m ? `${m.name}${m.color ? ` · ${m.color}` : ""}` : "esta cor";
  }

  /** Só despacha quando a lista é aceitável pelo servidor. Rascunho
   *  incompleto (cor sem material, segunda cor sem gramas) fica na tela com o
   *  campo marcado, em vez de virar um 400 previsível.
   *
   *  Recalcula a partir do argumento de propósito: os handlers rodam ANTES do
   *  próximo flush reativo, então `normalizadas` e `bloqueio` ainda valem o
   *  que valiam antes desta mutação. */
  function talvezSalvar(atuais: Rascunho[]) {
    const norm = normaliza(atuais);
    if (whyNotSendable(norm) !== null) return;
    dispatch("save", {
      filaments: norm.map((l) =>
        // Gramas ausentes = chave omitida: o servidor mantém NULL e segue
        // derivando do gcode (spec 3.4). Mandar 0 seria 422.
        l.grams_unit === null
          ? { material_id: l.material_id }
          : { material_id: l.material_id, grams_unit: String(l.grams_unit) },
      ),
    });
  }

  function trocaMaterial(i: number, materialId: string) {
    linhas = linhas.map((l, idx) => (idx === i ? { ...l, material_id: materialId } : l));
    talvezSalvar(linhas);
  }

  /** Digitar só mexe no rascunho — salvar no `change` (blur/Enter) evita um
   *  PUT por tecla. */
  function digitaGramas(i: number, texto: string) {
    linhas = linhas.map((l, idx) => (idx === i ? { ...l, gramasRaw: texto } : l));
  }

  function adiciona() {
    linhas = [...linhas, { material_id: "", gramasRaw: "", position: linhas.length + 1 }];
  }

  function remove(i: number) {
    // withoutIndex recusa a última linha e renumera as sobreviventes.
    linhas = withoutIndex(linhas, i);
    talvezSalvar(linhas);
  }
</script>

<div class="filamentos">
  <div class="cabeca">
    <span class="titulo">Filamentos</span>
    <span class="contagem mono">{linhas.length} {linhas.length === 1 ? "cor" : "cores"}</span>
  </div>

  <ul class="linhas">
    {#each linhas as l, i}
      {@const semGramas = toGrams(l.gramasRaw) === null}
      {@const precisaGramas = exigeGramas && semGramas}
      <li class="linha">
        <span class="ordem mono" aria-hidden="true">{i + 1}</span>
        <select
          class="material"
          aria-label={`Material da cor ${i + 1}`}
          value={l.material_id}
          disabled={saving}
          on:change={(e) => trocaMaterial(i, (e.currentTarget as HTMLSelectElement).value)}
        >
          <option value="" disabled>— escolher —</option>
          {#each materials as m}
            <option value={m.id}>
              {m.name} · {m.material_type}{m.color ? ` · ${m.color}` : ""}
            </option>
          {/each}
        </select>
        <span class="gramas">
          <input
            type="number"
            class="campo-gramas"
            class:derivado={semGramas && !precisaGramas}
            class:falta={precisaGramas}
            min="0.01"
            step="0.01"
            inputmode="decimal"
            aria-label={`Gramas por peça da cor ${i + 1}`}
            aria-invalid={precisaGramas}
            placeholder={precisaGramas ? "gramas" : gcodeTotal > 0 ? fmtNum(gcodeTotal, 2) : ""}
            title={precisaGramas
              ? "Com mais de uma cor, cada linha precisa das próprias gramas."
              : semGramas
                ? "Vazio usa o valor do gcode, em cinza. Digitar substitui pelo medido."
                : "Gramas por peça, valor final — purga inclusa."}
            value={l.gramasRaw}
            disabled={saving}
            on:input={(e) => digitaGramas(i, (e.currentTarget as HTMLInputElement).value)}
            on:change={() => talvezSalvar(linhas)}
          />
          <span class="unidade">g/peça</span>
        </span>
        <button
          type="button"
          class="tiny ghost danger remover"
          title={linhas.length === 1
            ? "Um item precisa de pelo menos uma cor"
            : `Remover ${nomeDe(materials, l.material_id)}`}
          aria-label={`Remover cor ${i + 1}`}
          disabled={saving || linhas.length === 1}
          on:click={() => remove(i)}
        >
          ×
        </button>
      </li>
    {/each}
  </ul>

  <div class="acoes">
    <button type="button" class="tiny ghost" disabled={saving} on:click={adiciona}>+ cor</button>
  </div>

  <div class="rodape mono">
    <span class="par">soma <strong>{soma === null ? DASH : `${fmtNum(soma, 2)} g/peça`}</strong></span>
    <span class="sep" aria-hidden="true">·</span>
    <span class="par">gcode <strong>{gcodeTotal > 0 ? `${fmtNum(gcodeTotal, 2)} g` : DASH}</strong></span>
    <span class="sep" aria-hidden="true">·</span>
    <span class="par" class:diverge={diferenca !== null && diferenca !== 0}>
      delta
      <strong>
        {diferenca === null ? DASH : `${diferenca > 0 ? "+" : ""}${fmtNum(diferenca, 2)}`}
      </strong>
    </span>
  </div>

  {#if bloqueio === "material"}
    <p class="aviso">Escolha o material de cada cor para salvar.</p>
  {:else if bloqueio === "gramas"}
    <p class="aviso">
      Com mais de uma cor, cada linha precisa das próprias gramas — o gcode é um número do item
      inteiro e não sabe dividir.
    </p>
  {:else if diferenca !== null && diferenca !== 0}
    <p class="nota">A soma não fecha com o gcode, e está salvo assim: o gcode estima, o digitado mede.</p>
  {/if}
</div>

<style>
  .filamentos {
    display: grid;
    gap: 0.4rem;
    min-width: 20rem;
    text-align: left;
  }
  .cabeca {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
  }
  .titulo {
    font-size: 0.78rem;
    letter-spacing: 0.02em;
  }
  .contagem {
    font-size: 0.68rem;
    color: var(--muted);
  }
  .linhas {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0.3rem;
  }
  /* A numeração carrega informação real: position 1 é a linha que define o
     material do item, então o número fica visível — não é ornamento. */
  .linha {
    display: grid;
    grid-template-columns: 1.1rem minmax(6rem, 1fr) auto 1.7rem;
    align-items: center;
    gap: 0.4rem;
  }
  .ordem {
    font-size: 0.7rem;
    color: var(--muted);
    text-align: right;
  }
  /* O visual compacto de célula de tabela é o mesmo de `input.inline` da
     página de orçamento, replicado aqui porque CSS de componente é escopado
     e aquelas regras não atravessam. */
  .material,
  .campo-gramas {
    font: inherit;
    font-size: 0.8rem;
    padding: 0.2rem 0.4rem;
    border: 1px solid var(--line);
    background: var(--paper);
    box-sizing: border-box;
    height: 1.85rem;
    line-height: 1.2;
  }
  .material:focus,
  .campo-gramas:focus {
    outline: 1px solid var(--brand);
    outline-offset: 1px;
  }
  .material:disabled,
  .campo-gramas:disabled {
    opacity: 0.55;
  }
  .material {
    min-width: 0;
    width: 100%;
  }
  .gramas {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  .campo-gramas {
    width: 5.4rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  /* O derivado do gcode aparece como fantasma: é um número real, mas não é
     o da pessoa — digitar por cima é o que o preenche de verdade. */
  .campo-gramas.derivado::placeholder {
    color: var(--muted);
    opacity: 1;
  }
  .campo-gramas.falta {
    border-color: var(--danger);
  }
  .unidade {
    font-size: 0.66rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .remover {
    justify-self: end;
    line-height: 1;
  }
  .remover:disabled {
    opacity: 0.35;
  }
  .acoes {
    display: flex;
  }
  .rodape {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.35rem;
    padding-top: 0.35rem;
    border-top: 1px solid var(--line);
    font-size: 0.7rem;
    color: var(--muted);
  }
  .rodape strong {
    font-weight: 500;
    color: var(--fg);
  }
  .rodape .par.diverge strong {
    color: var(--danger);
  }
  .sep {
    color: var(--line-strong);
    opacity: 0.35;
  }
  .aviso,
  .nota {
    margin: 0;
    font-size: 0.68rem;
    line-height: 1.45;
    max-width: 30rem;
  }
  .aviso {
    color: var(--danger);
  }
  .nota {
    color: var(--muted);
  }
</style>
