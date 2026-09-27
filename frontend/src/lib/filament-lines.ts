/** Lógica pura das linhas de filamento de um item (uma linha por cor).
 *
 *  Vive fora do .svelte de propósito: o Vitest deste projeto roda com
 *  `environment: "node"` e sem jsdom, então nada dentro de um componente é
 *  testável. O que der para calcular aqui, calcula-se aqui.
 *
 *  Espelha o backend em dois pontos que não podem divergir:
 *  - `gcodeGrams` reproduz `effective_grams_per_unit` + `grams_from_meters`
 *    (backend/core/quote_service.py, backend/core/pricing/cost.py): gramas
 *    preenchidas e > 0 ganham dos metros, e sem refugo (spec 3.3).
 *  - `toGrams` reproduz a guarda `gt=0` de `QuoteItemFilamentIn.grams_unit`:
 *    campo vazio é `null` ("derive do gcode"), nunca `0`. */

/** Diâmetro nominal do filamento, em mm — o mesmo default do backend. */
export const DIAMETRO_MM = 1.75;

/** Gramas se exibem e se digitam com duas casas; arredondar aqui evita que
 *  12,34 + 5,66 apareça como 18,000000000000004 no rodapé. */
function casas2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** Converte o que veio da API (Decimal serializado em string) ou do input
 *  para gramas utilizáveis. `null` significa "não informado". */
export function toGrams(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

/** Soma as gramas por peça das linhas.
 *
 *  `null` quando a lista está vazia ou quando alguma linha não tem gramas:
 *  não há soma parcial honesta. Mostrar 12,34 num item de duas cores em que
 *  só a primeira foi preenchida afirma que o item pesa 12,34 g. */
export function sumGrams(lines: readonly { grams_unit?: number | null }[]): number | null {
  if (lines.length === 0) return null;
  let total = 0;
  for (const l of lines) {
    if (l.grams_unit === null || l.grams_unit === undefined) return null;
    total += l.grams_unit;
  }
  return casas2(total);
}

/** Gramas por peça derivadas do gcode — o valor cinza que a tela mostra numa
 *  linha sem gramas digitadas. Sem refugo: é o número do fatiador, não o
 *  número de custo. */
export function gcodeGrams(gcodeMeta: Record<string, unknown>, density: number): number {
  const gramas = Number(gcodeMeta.filament_g);
  if (Number.isFinite(gramas) && gramas > 0) return gramas;
  const metros = Number(gcodeMeta.filament_m);
  if (!Number.isFinite(metros) || metros <= 0) return 0;
  const areaMm2 = Math.PI * (DIAMETRO_MM / 2) ** 2;
  return casas2(metros * areaMm2 * density);
}

/** Diferença entre a soma digitada e o número do gcode. Informativo: o gcode
 *  é estimativa, o digitado é medição, e a spec (3.5) manda não bloquear. */
export function delta(soma: number | null, gcode: number): number | null {
  if (soma === null) return null;
  return casas2(soma - gcode);
}

/** Assinatura por VALOR da lista vinda do servidor.
 *
 *  Existe por causa de um bug real: `$: linhas = doServidor(filaments)` num
 *  componente Svelte 5 legado compila para um `legacy_pre_effect` cuja
 *  dependência é a prop `filaments`, e a prop, sendo um ARRAY, é envolvida no
 *  pai por `derived_safe_equal`. `safe_not_equal` devolve `true` para
 *  QUALQUER objeto ou array, com identidade igual ou não — então o efeito
 *  re-rodava a cada invalidação do item, e sobrescrevia o rascunho local
 *  (a cor recém-acrescentada, as gramas recém-digitadas) em cada `set()` do
 *  orçamento. Comparar identidade de array não resolve, e não é isso que o
 *  runtime faz; comparar uma STRING resolve, porque aí `safe_not_equal` é uma
 *  comparação de verdade.
 *
 *  Entra o que o rascunho deriva do servidor — identidade, material e gramas
 *  de cada linha, NA ORDEM. `position` não entra: a ordem já é a posição. */
export function linesSignature(
  lines: readonly { id: string; material_id: string; grams_unit: string | null }[],
): string {
  return JSON.stringify(lines.map((f) => [f.id, f.material_id, f.grams_unit]));
}

/** Monta o corpo de `filaments` do PUT.
 *
 *  Três coisas que o servidor cobra e que precisam estar exatas:
 *  - **sem `position`**: a ORDEM DA LISTA é a posição (`enumerate(..., start=1)`
 *    do lado de lá). Mandar `position` não é aceito pelo schema;
 *  - **gramas ausentes = chave omitida**, nunca `0`: `QuoteItemFilamentIn`
 *    exige `gt=0`, então `0` é 422, enquanto omitir mantém `NULL` e o
 *    servidor segue derivando do gcode (spec 3.4);
 *  - **gramas como string**, porque do outro lado é `Decimal`.
 *
 *  `material_id` também não pode viajar como chave de item — é o `material_id`
 *  de TOPO do payload que é 400 junto de `filaments`, e quem monta o corpo do
 *  PUT é o chamador; aqui cada linha leva o seu, que é o que a rota espera. */
export type FilamentPayload = { material_id: string; grams_unit?: string };

export function toPayload(
  lines: readonly { material_id: string; grams_unit: number | null }[],
): FilamentPayload[] {
  return lines.map((l) => {
    // Passa por toGrams de novo de propósito: um `0` que chegue aqui por
    // qualquer caminho vira ausência, em vez de virar a string "0" e 422.
    const g = toGrams(l.grams_unit);
    return g === null
      ? { material_id: l.material_id }
      : { material_id: l.material_id, grams_unit: String(g) };
  });
}

/** Por que a lista ainda não pode ir para o servidor, ou `null` se pode.
 *
 *  Espelha as três rejeições 400 da rota (Task 7) para que a tela marque o
 *  campo em vez de descobrir pelo erro do servidor:
 *  - `"vazio"`: item sem linha nenhuma;
 *  - `"material"`: alguma linha sem material escolhido;
 *  - `"gramas"`: item de mais de uma cor com alguma linha sem gramas
 *    (invariante 3 — o gcode é um número do item inteiro e não sabe dividir).
 *
 *  Um item de UMA cor sem gramas é válido: `grams_unit` NULL significa
 *  "derive do gcode" (spec 3.4). */
export type Bloqueio = "vazio" | "material" | "gramas" | null;

export function whyNotSendable(
  lines: readonly { material_id: string; grams_unit: number | null }[],
): Bloqueio {
  if (lines.length === 0) return "vazio";
  if (lines.some((l) => l.material_id === "")) return "material";
  if (lines.length > 1 && lines.some((l) => l.grams_unit === null)) return "gramas";
  return null;
}

/** Remove a linha `i` e renumera as sobreviventes a partir de 1.
 *
 *  Recusa-se a remover a última linha (invariante 1: item sem linha nenhuma é
 *  400 no servidor) e um índice que não existe — nos dois casos devolve a
 *  lista recebida, sem mutá-la. O renumerar não é cosmético: `position` 1 é a
 *  linha que manda no `material_version_id` do item. */
export function withoutIndex<T extends { position: number }>(lines: readonly T[], i: number): T[] {
  if (lines.length <= 1) return [...lines];
  if (i < 0 || i >= lines.length) return [...lines];
  return lines
    .filter((_, idx) => idx !== i)
    .map((l, idx) => ({ ...l, position: idx + 1 }));
}

/** Linha do rascunho do editor: gramas guardadas como o TEXTO do campo, para
 *  não reformatar embaixo do cursor. `toGrams` faz a leitura. */
export type DraftLine = { material_id: string; gramasRaw: string; position: number };

function linhaEmBranco(position: number): DraftLine {
  return { material_id: "", gramasRaw: "", position };
}

/** Modo multicor: flag marcado OU mais de uma linha. As duas coisas andam
 *  juntas na tela — uma segunda cor sem o flag ainda é um item de N cores. */
export function isMultiColor(lines: readonly unknown[], flag: boolean): boolean {
  return flag || lines.length > 1;
}

/** Entrar em multicor: garante pelo menos duas linhas, acrescentando linhas em
 *  branco (material a escolher, gramas vazias). Idempotente — com 2+ linhas
 *  devolve uma cópia sem mudança, então marcar duas vezes não cria duas cores
 *  vazias. A linha nova é rascunho: sem gramas ela é 400 no servidor
 *  (invariante 3), e o editor só salva quando a lista fica válida. */
export function enterMultiColor(lines: readonly DraftLine[]): DraftLine[] {
  const r = [...lines];
  while (r.length < 2) r.push(linhaEmBranco(r.length + 1));
  return r;
}

/** Sair de multicor: fica só a cor 1, com o material e as gramas dela. */
export function leaveMultiColor(lines: readonly DraftLine[]): DraftLine[] {
  return lines.slice(0, 1).map((l) => ({ ...l, position: 1 }));
}

/** Sair de multicor descarta alguma coisa que a pessoa preencheu?
 *
 *  Decide se a tela pede confirmação. Uma linha além da 1 conta como "cor"
 *  se tem material OU gramas; a linha totalmente em branco que o próprio
 *  multicolor acabou de criar não é cor nenhuma, e desmarcar logo em seguida
 *  não precisa perguntar nada. */
export function discardsOnLeave(lines: readonly DraftLine[]): boolean {
  return lines
    .slice(1)
    .some((l) => l.material_id !== "" || toGrams(l.gramasRaw) !== null);
}

type ComPreco = { id: string; price_per_kg_ref: number | string };

/** Custo de filamento de UMA cor, por peça: gramas × preço/kg do material da
 *  linha / 1000 — o mesmo `filament_cost` do backend, sem refugo (gramas
 *  digitadas não levam refugo) e sem falha (que se aplica ao item todo).
 *
 *  `null` sem gramas, sem material, ou com preço ausente/inválido: não existe
 *  custo parcial honesto. Preço 0 é preço — vale 0. */
export function lineCost(
  line: { material_id: string; grams_unit: number | null },
  materials: readonly ComPreco[],
): number | null {
  const g = toGrams(line.grams_unit);
  if (g === null) return null;
  const m = materials.find((x) => x.id === line.material_id);
  if (!m || m.price_per_kg_ref === "" || m.price_per_kg_ref === null) return null;
  const preco = Number(m.price_per_kg_ref);
  if (!Number.isFinite(preco) || preco < 0) return null;
  return (g * preco) / 1000;
}

/** Soma do custo de filamento das cores, por peça. `null` se a lista é vazia
 *  ou se alguma cor não tem custo — mesmo motivo de `sumGrams`. */
export function filamentCostPerPiece(
  lines: readonly { material_id: string; grams_unit: number | null }[],
  materials: readonly ComPreco[],
): number | null {
  if (lines.length === 0) return null;
  let total = 0;
  for (const l of lines) {
    const c = lineCost(l, materials);
    if (c === null) return null;
    total += c;
  }
  return total;
}
