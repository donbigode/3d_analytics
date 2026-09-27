<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import {
    delta,
    discardsOnLeave,
    enterMultiColor,
    filamentCostPerPiece,
    gcodeGrams,
    isMultiColor,
    leaveMultiColor,
    lineCost,
    linesSignature,
    shouldUntickAfterRemove,
    sumGrams,
    toGrams,
    toPayload,
    whyNotSendable,
    withoutIndex,
  } from "$lib/filament-lines";
  import type { DraftLine, FilamentPayload } from "$lib/filament-lines";
  import { money as fmtMoney, num as fmtNum, DASH } from "$lib/format";
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
  /** `is_multi_color` do item, como o servidor gravou. */
  export let multiColor = false;
  /** PATCH do flag em voo — trava só o checkbox. */
  export let savingFlag = false;
  /** SAÍDA (para `bind:`): quantas cores o item tem quando está em modo
   *  multicor, 0 fora dele. A página usa na célula de tempo ("vale para as N
   *  cores") — e precisa ser o número do RASCUNHO, porque a 2ª linha criada
   *  ao marcar multicolor ainda não existe no servidor. */
  export let nCores = 0;

  /** `multicolor`: a pessoa marcou/desmarcou. `filaments` vem junto só quando
   *  desmarcar precisa apagar cores já salvas — flag e lista num PUT só. */
  const dispatch = createEventDispatcher<{
    save: { filaments: FilamentPayload[] };
    multicolor: { next: boolean; filaments?: FilamentPayload[] };
  }>();

  /** O rascunho guarda as gramas como o TEXTO do campo, não como número: o
   *  que a pessoa digitou é o que fica no input, sem reformatar embaixo do
   *  cursor. `toGrams` faz a leitura ("" e 0 são ausência, não zero grama). */
  type Rascunho = DraftLine;
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

  // Ressincroniza o rascunho quando o servidor responde — e SÓ então.
  //
  // `$: linhas = doServidor(filaments)` sozinho não serve, e o motivo não é
  // óbvio: o pai passa a prop dentro de um `derived_safe_equal`, e
  // `safe_not_equal` devolve `true` para qualquer array, com identidade igual
  // ou não. Ou seja, a prop "muda" a cada invalidação do item — a cada
  // `quoteRes.set()`, isto é, a cada toggle de multicolor, edição de
  // quantidade, tempo, metros, serviço — e o efeito apagava o rascunho:
  // a cor recém-acrescentada com "+ cor", as gramas recém-digitadas.
  //
  // A comparação tem de ser por VALOR, e numa string, onde `safe_not_equal`
  // é uma comparação de verdade. `filaments` continua textualmente presente
  // nos dois statements, então a varredura de dependências do Svelte vê tudo.
  let linhas: Rascunho[] = doServidor(filaments);
  let ultimaAssinatura: string = linesSignature(filaments);

  $: assinatura = linesSignature(filaments);
  $: if (assinatura !== ultimaAssinatura) {
    ultimaAssinatura = assinatura;
    linhas = doServidor(filaments);
  }

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

  // Modo multicor: flag do servidor OU mais de uma linha no rascunho. Nenhum
  // destes três escreve em `linhas` — só leem. Quem escreve em `linhas` fora
  // de handler é apenas o resync acima, guardado pela assinatura.
  $: modoMulti = isMultiColor(linhas, multiColor);
  $: custoPeca = filamentCostPerPiece(normalizadas, materials);
  $: nCores = modoMulti ? linhas.length : 0;

  // O `checked={modoMulti}` do template só é reaplicado quando `modoMulti`
  // MUDA. Se o PATCH do flag falhar, `modoMulti` não muda e o DOM fica com o
  // clique da pessoa (desmarcado num item que continua multicor). Quando
  // nenhum salvamento está em voo, o DOM volta a espelhar o estado real.
  // Só escreve no DOM do checkbox — não toca em `linhas`. A escrita fica numa
  // função de propósito: `caixa.checked = …` direto no `$:` compila para
  // `$.mutate(caixa, …)`, que invalida `caixa` — dependência do próprio bloco.
  let caixa: HTMLInputElement | undefined;
  function espelha(el: HTMLInputElement, marcado: boolean) {
    el.checked = marcado;
  }
  $: if (caixa && !savingFlag && !saving) espelha(caixa, modoMulti);

  // Colunas travadas: PUT da lista OU PATCH do flag em voo. Com o flag em voo,
  // uma cor salva nesse meio-tempo teria a resposta do flag chegando depois,
  // com a lista antiga — o resync a trocaria e o próximo save apagaria a cor.
  $: travado = saving || savingFlag;

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
    // `toPayload` é quem garante a forma do corpo (sem `position`, gramas
    // ausentes como chave omitida, gramas como string) — e tem teste.
    dispatch("save", { filaments: toPayload(norm) });
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
    // Flag e linhas andam juntos: a 2ª cor pelo "+ cor" também marca multicolor.
    if (!multiColor) dispatch("multicolor", { next: true });
  }

  /** Marcar abre a 2ª cor na hora, em branco e só no rascunho — ela salva
   *  quando a lista ficar válida, como qualquer cor nova. Desmarcar nunca
   *  descarta cor preenchida sem confirmação. */
  function trocaMulticor(el: HTMLInputElement) {
    if (el.checked) {
      linhas = enterMultiColor(linhas);
      if (!multiColor) dispatch("multicolor", { next: true });
      return;
    }

    if (discardsOnLeave(linhas)) {
      const outras = linhas.length - 1;
      const pergunta =
        outras === 1
          ? "Manter só a cor 1 e descartar a outra?"
          : `Manter só a cor 1 e descartar as outras ${outras}?`;
      if (!confirm(pergunta)) {
        // Cancelou: nada muda. O `checked={modoMulti}` não reaplica um valor
        // que não mudou, então o DOM é recolocado à mão.
        el.checked = true;
        return;
      }
    }

    const mantidas = leaveMultiColor(linhas);
    if (filaments.length > 1) {
      // Há cores SALVAS a apagar: flag e lista vão juntos, e o rascunho não é
      // tocado aqui — o resync aplica a lista de uma cor quando o servidor
      // responder. Se o PUT falhar, as cores continuam na tela e no servidor,
      // em vez de sumirem só da tela. Até lá o checkbox fica marcado.
      const norm = normaliza(mantidas);
      el.checked = true;
      if (whyNotSendable(norm) !== null) return;
      dispatch("multicolor", { next: false, filaments: toPayload(norm) });
      return;
    }
    // As cores descartadas eram só rascunho: some localmente, e o flag desmarca.
    linhas = mantidas;
    if (multiColor) dispatch("multicolor", { next: false });
  }

  function remove(i: number) {
    // withoutIndex recusa a última linha e renumera as sobreviventes.
    const restantes = withoutIndex(linhas, i);
    if (shouldUntickAfterRemove(restantes, multiColor)) {
      const norm = normaliza(restantes);
      if (whyNotSendable(norm) === null) {
        // Sobrou uma cor com gramas: remoção e desmarcar no MESMO PUT. Dois
        // requests (save + PATCH do flag) podem responder fora de ordem.
        linhas = restantes;
        dispatch("multicolor", { next: false, filaments: toPayload(norm) });
        return;
      }
    }
    linhas = restantes;
    talvezSalvar(linhas);
  }
</script>

<div class="filamentos">
  <div class="cabeca">
    <span class="titulo">Filamentos</span>
    <span class="contagem mono">{linhas.length} {linhas.length === 1 ? "cor" : "cores"}</span>
  </div>

  <ul class="linhas" class:multi={modoMulti}>
    {#each linhas as l, i}
      {@const semGramas = toGrams(l.gramasRaw) === null}
      {@const precisaGramas = exigeGramas && semGramas}
      {@const custo = lineCost({ material_id: l.material_id, grams_unit: toGrams(l.gramasRaw) }, materials)}
      <li class="linha" class:sub={modoMulti && i > 0}>
        {#if modoMulti && i > 0}
          <span class="conector mono" aria-hidden="true">└ cor {i + 1}</span>
        {:else if !modoMulti}
          <span class="ordem mono" aria-hidden="true">{i + 1}</span>
        {/if}
        <select
          class="material"
          aria-label={`Material da cor ${i + 1}`}
          value={l.material_id}
          disabled={travado}
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
            disabled={travado}
            on:input={(e) => digitaGramas(i, (e.currentTarget as HTMLInputElement).value)}
            on:change={() => talvezSalvar(linhas)}
          />
          <span class="unidade">g/peça</span>
        </span>
        {#if modoMulti}
          <span
            class="custo mono"
            title={custo === null
              ? "Sem gramas ou sem preço do material — não dá para custear esta cor."
              : "Filamento desta cor por peça: gramas × preço/kg do material."}
          >
            {custo === null ? DASH : fmtMoney(custo)}
          </span>
        {/if}
        <button
          type="button"
          class="tiny ghost danger remover"
          title={linhas.length === 1
            ? "Um item precisa de pelo menos uma cor"
            : i === 0
              ? "A cor 1 é a principal da peça. Para voltar a uma cor, desmarque multicolor."
              : `Remover ${nomeDe(materials, l.material_id)}`}
          aria-label={`Remover cor ${i + 1}`}
          disabled={travado || linhas.length === 1 || (modoMulti && i === 0)}
          on:click={() => remove(i)}
        >
          ×
        </button>
      </li>
    {/each}
  </ul>

  <div class="acoes" class:multi={modoMulti}>
    <button type="button" class="tiny ghost" disabled={travado} on:click={adiciona}>+ cor</button>
    {#if modoMulti}
      <span
        class="total mono"
        title="Soma do filamento das cores, por peça. Tempo, energia e depreciação contam uma vez por peça e ficam de fora."
      >
        filamento/peça <strong>{custoPeca === null ? DASH : fmtMoney(custoPeca)}</strong>
      </span>
    {/if}
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

  <label
    class="mc-toggle"
    title={modoMulti
      ? "Desmarcar volta a uma cor: fica só a cor 1."
      : "Marque quando a peça usa mais de uma cor — abre uma linha para cada cor. Cor sem gramas digitadas passa a usar o refugo de purga maior do material."}
  >
    <input
      bind:this={caixa}
      type="checkbox"
      checked={modoMulti}
      disabled={travado}
      on:change={(e) => trocaMulticor(e.currentTarget as HTMLInputElement)}
    />
    <span>multicolor</span>
  </label>
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
    align-items: baseline;
  }
  /* Modo multicor: a lista vira um bloco — cor 1 na linha do item, cores
     2..N penduradas nela por um fio, sem repetir peça, quantidade ou tempo.
     Cor 1 ocupa as duas primeiras colunas; as sub-linhas deixam a primeira
     para o conector, e é esse deslocamento que as recua. */
  .linhas.multi .linha {
    grid-template-columns: 3.4rem minmax(6rem, 1fr) auto 4.6rem 1.7rem;
  }
  .linhas.multi .linha:not(.sub) .material {
    grid-column: 1 / 3;
  }
  .conector {
    font-size: 0.68rem;
    color: var(--muted);
    white-space: nowrap;
    padding-left: 0.35rem;
  }
  .custo {
    font-size: 0.72rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .acoes.multi {
    justify-content: space-between;
    padding-left: 3.8rem;
  }
  .total {
    font-size: 0.7rem;
    color: var(--muted);
    white-space: nowrap;
    padding-right: 2.1rem;
  }
  .total strong {
    font-weight: 500;
    color: var(--fg);
  }
  .mc-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    color: var(--muted);
    font-size: 0.72rem;
    cursor: pointer;
    user-select: none;
    justify-self: start;
  }
  .mc-toggle input {
    margin: 0;
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
