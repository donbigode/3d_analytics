/** Lógica pura do modal de produzir — uma baixa de bobina por linha de cor.
 *
 *  Vive fora do `.svelte` pelo mesmo motivo de `filament-lines.ts`: o Vitest
 *  deste projeto roda com `environment: "node"` e sem jsdom, então nada dentro
 *  de um componente tem cobertura. Toda decisão que dá pra tomar aqui é tomada
 *  aqui, e o componente fica sendo só a montagem da tela.
 *
 *  O contrato com o servidor (`apply_production`, backend/api/routes/quotes/
 *  transitions.py) é o que dita a forma:
 *
 *  - cada baixa nomeia a LINHA (`quote_item_filament_id`). Sem isso, um item
 *    de N cores é **409**, de propósito: o fallback calcularia as gramas do
 *    item INTEIRO para cada linha e debitaria N× o estoque;
 *  - as gramas de cada linha o servidor deriva sozinho (`grams_unit ×
 *    quantity`, ou o gcode quando `grams_unit` é NULL). `grams` aqui é
 *    override, não cálculo — a tela só o manda quando a pessoa digitou;
 *  - `filament_m` é campo do ITEM e o servidor o persiste no `gcode_meta`, o
 *    que num item multicor não representa cor nenhuma. Então só viaja para
 *    item de uma cor.
 */

import { gcodeGrams, toGrams } from "$lib/filament-lines";

/** Uma linha de cor do item, na forma que a API devolve (`QuoteItemFilamentOut`).
 *  `material_id` é o `material_version_id` do produto orçado naquela cor. */
export type LinhaProduzir = {
  id: string;
  material_id: string;
};

/** Uma bobina física, na forma do `SpoolOut`.
 *
 *  `material_version_id` é IDENTIDADE: diz qual produto está no rolo. Não é
 *  preço — o custo da baixa continua saindo do `purchased_price /
 *  initial_grams` da própria bobina, nunca do `price_per_kg_ref` do material. */
export type BobinaProduzir = {
  id: string;
  status: string;
  material_type: string;
  material_version_id: string | null;
  remaining_grams: number | string;
};

export type ItemProduzir = {
  id: string;
  quantity: number;
  filaments?: readonly LinhaProduzir[];
};

/** O que o `POST /transitions/produce` aceita em cada item de `consumption`. */
export type Baixa = {
  quote_item_id: string;
  spool_id: string;
  quote_item_filament_id: string;
  grams?: string;
  filament_m?: number;
};

export type Overrides = {
  /** Gramas TOTAIS a debitar, por id de linha — o que a pessoa digitou. */
  gramasPorLinha?: Record<string, string>;
  /** Metragem por peça, por id de item. Só se aplica a item de uma cor. */
  metrosPorItem?: Record<string, string>;
};

function restantes(sp: BobinaProduzir): number {
  const n = Number(sp.remaining_grams);
  return Number.isFinite(n) ? n : 0;
}

function aberta(sp: BobinaProduzir): boolean {
  return sp.status === "open";
}

/** As bobinas oferecidas no `<select>` de uma linha.
 *
 *  Duas regras, e a segunda existe para não esconder justamente a bobina
 *  certa: entra a bobina aberta cujo `material_type` casa com o tipo da linha
 *  **ou** a que está vinculada ao material da linha — o vínculo é exato e vale
 *  mais que o texto do tipo, que pode estar escrito "PLA+" de um lado e "PLA"
 *  do outro. Sem essa segunda regra, a pré-seleção poderia escolher uma
 *  bobina ausente das `<option>` e o select apareceria vazio com um valor
 *  escondido embaixo.
 *
 *  `materialType` nulo (material não encontrado na lista local) oferece todas
 *  as abertas: filtrar por um tipo que não se conhece deixaria a pessoa sem
 *  como produzir.
 *
 *  Bobina zerada continua na lista: não é pré-selecionada, mas quem decide se
 *  dá pra debitar é o servidor, e esconder a bobina esconderia o motivo.
 *
 *  A ordem de entrada é preservada — a API devolve por compra mais recente. */
export function spoolsForLine<T extends BobinaProduzir>(
  spools: readonly T[],
  line: LinhaProduzir,
  materialType: string | null,
): T[] {
  return spools.filter(
    (sp) =>
      aberta(sp) &&
      (sp.material_version_id === line.material_id ||
        materialType === null ||
        sp.material_type === materialType),
  );
}

/** Bobina sugerida para cada linha, chaveada pelo **id da linha**.
 *
 *  Chave por linha, não por item e não por chave composta: o id da linha é
 *  UUID, único no banco inteiro, e todo item produzível tem pelo menos uma
 *  linha (`_assert_materials_resolved` barra item sem linha antes de
 *  produzir). Assim item de uma cor e de N cores usam o mesmo caminho.
 *
 *  Casa **só** por `material_version_id`. Nunca por `material_type`: é o
 *  casamento frouxo que a migração 0035 recusou a fazer, e uma bobina
 *  adivinhada errado debita o filamento errado. Linha sem candidata sai da
 *  saída (chave ausente) em vez de sair com `""`, para o `fillMissing`
 *  distinguir "nunca sugerido" de "a pessoa limpou".
 *
 *  Determinística: ordena antes de escolher, numa CÓPIA — a lista recebida é
 *  a do store de refs, compartilhada com o resto da tela. Critério: mais
 *  filamento restante primeiro (a bobina com folga é a que tem mais chance de
 *  cobrir a baixa sem o 409 de "insufficient grams"), desempatando pelo id
 *  para o resultado não depender da ordem da API. */
export function preselectSpools(
  lines: readonly LinhaProduzir[],
  spools: readonly BobinaProduzir[],
): Record<string, string> {
  const candidatas = spools
    .filter((sp) => aberta(sp) && sp.material_version_id !== null && restantes(sp) > 0)
    .slice()
    .sort((a, b) => restantes(b) - restantes(a) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  const out: Record<string, string> = {};
  for (const l of lines) {
    const escolhida = candidatas.find((sp) => sp.material_version_id === l.material_id);
    if (escolhida) out[l.id] = escolhida.id;
  }
  return out;
}

/** Assinatura por VALOR do que alimenta a pré-seleção.
 *
 *  Existe pelo mesmo motivo do `linesSignature` de `filament-lines.ts`: num
 *  componente Svelte legado, `safe_not_equal` devolve `true` para QUALQUER
 *  objeto ou array, com identidade igual ou não. Um `$:` que dependa de
 *  `quote.items` ou de `spools` re-roda a cada invalidação do orçamento, e um
 *  `$:` que re-roda e escreve em `produceAssignments` apaga a escolha da
 *  pessoa. Comparar identidade de array não resolve; comparar uma STRING
 *  resolve, porque aí a comparação é de verdade.
 *
 *  Entra o que muda a sugestão: a identidade e o material de cada linha, e a
 *  identidade, o vínculo, o status e o saldo de cada bobina. */
export function preselectSignature(
  lines: readonly LinhaProduzir[],
  spools: readonly BobinaProduzir[],
): string {
  return JSON.stringify([
    lines.map((l) => [l.id, l.material_id]),
    spools.map((sp) => [sp.id, sp.material_version_id, sp.status, String(sp.remaining_grams)]),
  ]);
}

/** Aplica a sugestão **só** nas chaves que ainda não existem.
 *
 *  É a garantia estrutural contra o segundo modo de falha da reatividade: um
 *  `$:` que re-roda e sobrescreve a bobina que a pessoa escolheu a mão. Aqui
 *  nem o `$:` mais promíscuo consegue estragar a escolha — inclusive a
 *  escolha de VOLTAR para "—", que é uma chave presente com valor `""`.
 *
 *  Não muta: devolve objeto novo, para a atribuição invalidar o componente. */
export function fillMissing(
  atuais: Readonly<Record<string, string>>,
  preSelecao: Readonly<Record<string, string>>,
): Record<string, string> {
  const out: Record<string, string> = { ...atuais };
  for (const [linha, spool] of Object.entries(preSelecao)) {
    if (!(linha in out)) out[linha] = spool;
  }
  return out;
}

/** Todas as linhas dos itens, achatadas na ordem de item e position. */
function linhas(items: readonly ItemProduzir[]): { item: ItemProduzir; linha: LinhaProduzir }[] {
  return items.flatMap((item) => (item.filaments ?? []).map((linha) => ({ item, linha })));
}

/** O corpo de `consumption` do POST: **uma entrada por linha de cor**.
 *
 *  Nunca uma por item — era essa a forma antiga, e é ela que o servidor
 *  recusa com 409 num item multicor. `quote_item_filament_id` vai preenchido
 *  sempre, inclusive no item de uma cor: omitir "funcionaria" lá (o servidor
 *  cai em `linhas[0]`), mas mandar sempre é o que mantém um caminho só.
 *
 *  Item sem linha nenhuma não emite baixa: é item de material pendente, que o
 *  servidor barra antes de produzir, e uma baixa sem cor seria um 409 obscuro. */
export function toConsumption(
  items: readonly ItemProduzir[],
  assignments: Readonly<Record<string, string>>,
  overrides: Overrides = {},
): Baixa[] {
  const { gramasPorLinha = {}, metrosPorItem = {} } = overrides;
  return linhas(items).map(({ item, linha }) => {
    const baixa: Baixa = {
      quote_item_id: item.id,
      spool_id: assignments[linha.id] ?? "",
      quote_item_filament_id: linha.id,
    };
    const g = toGrams(gramasPorLinha[linha.id]);
    if (g !== null) {
      // Gramas têm precedência: é o total exato a debitar naquela cor.
      baixa.grams = String(g);
      return baixa;
    }
    // Metros é campo do ITEM (o servidor grava no gcode_meta) — num item de
    // mais de uma cor não representa cor nenhuma, então não viaja.
    if ((item.filaments ?? []).length === 1) {
      const m = toGrams(metrosPorItem[item.id]);
      if (m !== null) baixa.filament_m = m;
    }
    return baixa;
  });
}

/** Ids das linhas que ainda não têm bobina — não um booleano.
 *
 *  A tela precisa apontar QUAL cor falta; "falta alguma coisa" manda a pessoa
 *  procurar. Vazio (`""`) conta como falta: é o valor do "—". */
export function missingAssignments(
  items: readonly ItemProduzir[],
  assignments: Readonly<Record<string, string>>,
): string[] {
  return linhas(items)
    .filter(({ linha }) => !assignments[linha.id])
    .map(({ linha }) => linha.id);
}

/** Gramas que o servidor vai debitar nesta linha, ou `null` se não há de onde
 *  derivar (e aí a pessoa tem de informar metros ou gramas).
 *
 *  Espelha `apply_production` + `grams_for_item`: gramas da linha × quantidade
 *  do item; sem gramas na linha, o número do gcode × quantidade, sem refugo.
 *  Serve de placeholder do campo de override — mostrar o que VAI acontecer é
 *  mais honesto que pré-preencher o campo com um número que a pessoa não
 *  digitou (e que, antes desta task, era o `filament_g` POR PEÇA mandado como
 *  total, debitando 1/quantity numa peça repetida). */
export function debitGrams(
  item: { quantity: number; gcode_meta?: Record<string, unknown> | null },
  line: { grams_unit?: string | number | null },
  densidade: number,
): number | null {
  const q = Number(item.quantity);
  const quantidade = Number.isFinite(q) && q > 0 ? q : 1;
  const daLinha = toGrams(line.grams_unit);
  const porPeca = daLinha !== null ? daLinha : gcodeGrams(item.gcode_meta ?? {}, densidade);
  if (porPeca <= 0) return null;
  return Math.round(porPeca * quantidade * 100) / 100;
}
